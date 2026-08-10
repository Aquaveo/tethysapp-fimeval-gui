import csv
import io
import json as json_module
import logging
import math
import os
import statistics
import tempfile
import uuid
import zipfile

from botocore.exceptions import BotoCoreError, ClientError
from distributed import Client, Future
from django.http import FileResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from tethys_sdk.jobs import DaskJob
from tethys_sdk.routing import controller

from tethysapp.fimeval_gui.app import App

logger = logging.getLogger(__name__)


def _get_storage():
    """Build an S3Storage client from the app's MinIO/S3 custom settings."""
    from tethysapp.fimeval_gui.storage import S3Storage
    return S3Storage(
        endpoint_url=App.get_custom_setting('minio_endpoint_url'),
        access_key=App.get_custom_setting('minio_access_key'),
        secret_key=App.get_custom_setting('minio_secret_key'),
        bucket=App.get_custom_setting('s3_bucket'),
        public_endpoint_url=App.get_custom_setting('s3_public_endpoint_url'),
    )


def _get_owned_job(request, job_id):
    """Look up a DaskJob by id and confirm the requester owns it.

    Returns ``(job, None)`` on success, or ``(None, response)`` where *response*
    is the ``JsonResponse`` to return: 404 if no such job exists, 403 if it
    belongs to another user.
    """
    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return None, JsonResponse({'error': 'job not found'}, status=404)
    if job.user != request.user:
        return None, JsonResponse({'error': 'access denied'}, status=403)
    return job, None


@controller(login_required=False)
def home(request):
    """Controller for the app home page (SPA catch-all)."""
    return App.render(request, 'index.html')


@controller(url='api/csrf', login_required=False, name='api_csrf')
@ensure_csrf_cookie
def api_csrf(request):
    """Set the csrftoken cookie so the SPA can send X-CSRFToken on POSTs."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return JsonResponse({'detail': 'CSRF cookie set'})


# Components of an ESRI shapefile bundle (only used by the AOI method).
ALLOWED_BOUNDARY_EXT = {'.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.qpj'}

def _env_int(name, default):
    """Read a positive int from the environment, falling back to *default* when
    unset or unparseable. Lets operators tune limits per deployment without a
    code change (boss review: these were hardcoded)."""
    try:
        val = int(os.environ[name])
        return val if val > 0 else default
    except (KeyError, ValueError):
        return default


# Upload acceptance limits. Each is overridable via an env var so a deployment
# can size them to its worker pool / storage without editing code.
RASTER_EXT = {'.tif', '.tiff'}
MAX_CANDIDATES = _env_int('FIMEVAL_MAX_CANDIDATES', 10)
MAX_UPLOAD_BYTES = _env_int('FIMEVAL_MAX_UPLOAD_BYTES', 1024 * 1024 * 1024)  # 1 GB/file

# The worker clips candidates to the benchmark extent (BE31), so the benchmark's
# own pixel count bounds the working memory. A benchmark above this budget would
# OOM the worker even clipped. ~200 Mpx ≈ a heavy job that still fits two-up in
# the default 6 GB-per-worker pool (a 304 Mpx run measured ~4.6 GB).
MAX_EVAL_PIXELS = _env_int('FIMEVAL_MAX_EVAL_PIXELS', 200_000_000)


def _read_raster_geo(storage, key):
    """Header-only geo of the raster at *key*: ``{bounds, crs, width, height}``,
    or ``None`` if it can't be read. Streams the object to a temp file and reads
    only the header (a range read isn't portable across the MinIO/S3 mocks;
    ``/vsis3`` is a future optimization). Never raises — the guard must not block
    on an I/O hiccup."""
    import rasterio
    try:
        with tempfile.NamedTemporaryFile(suffix='.tif') as tmp:
            storage.download_to_path(key, tmp.name)
            with rasterio.open(tmp.name) as ds:
                return {
                    'bounds': tuple(ds.bounds),
                    'crs': ds.crs,
                    'width': ds.width,
                    'height': ds.height,
                }
    except Exception:
        return None


# Aim a downsample at this fraction of the ceiling so the resampled job lands
# comfortably under it rather than right at the edge.
_DOWNSAMPLE_TARGET_FRACTION = 0.9


def _estimate_working_pixels(storage, prefix, candidate_names):
    """Estimate the pixel count fimeval will actually process.

    fimeval's ``MakeFIMsUniform`` resamples every input to the *coarsest* input
    resolution before evaluating, and (post-BE31) each candidate is clipped to
    the benchmark extent. So the working set per candidate is roughly the
    benchmark∩candidate overlap area divided by the coarsest pixel size squared —
    NOT the benchmark's raw pixel count, which over-rejects fine-resolution
    rasters that fimeval would coarsen anyway (the "Tier_1 rejected" bug).

    Returns ``{'pixels': float, 'fit_resolution_m': float}`` for the
    largest-working-set candidate (``fit_resolution_m`` is the resolution that
    would bring it under the budget), or ``None`` if any header can't be read
    (guard skipped) or nothing overlaps.
    """
    import math
    from rasterio.warp import transform_bounds

    METRIC_CRS = 'EPSG:5070'  # meters; matches the worker's TARGET_CRS
    bench = _read_raster_geo(storage, f'{prefix}benchmark.tif')
    if not bench or bench['crs'] is None:
        return None

    def geo_metric(geo):
        """(bounds, coarsest-side resolution) for a raster, projected to meters."""
        left, bottom, right, top = transform_bounds(geo['crs'], METRIC_CRS, *geo['bounds'])
        res = max((right - left) / geo['width'], (top - bottom) / geo['height'])
        return (left, bottom, right, top), res

    b_bounds, b_res = geo_metric(bench)
    best = None
    for name in candidate_names:
        cand = _read_raster_geo(storage, f'{prefix}{name}')
        if not cand or cand['crs'] is None:
            return None
        c_bounds, c_res = geo_metric(cand)
        coarsest = max(b_res, c_res)
        ol_left = max(b_bounds[0], c_bounds[0])
        ol_bottom = max(b_bounds[1], c_bounds[1])
        ol_right = min(b_bounds[2], c_bounds[2])
        ol_top = min(b_bounds[3], c_bounds[3])
        if ol_right <= ol_left or ol_top <= ol_bottom:
            continue  # no overlap — the worker drops this candidate (BE31)
        area = (ol_right - ol_left) * (ol_top - ol_bottom)
        pixels = area / (coarsest ** 2)
        if best is None or pixels > best['pixels']:
            fit = math.sqrt(area / (MAX_EVAL_PIXELS * _DOWNSAMPLE_TARGET_FRACTION))
            best = {'pixels': pixels, 'fit_resolution_m': max(fit, coarsest)}
    return best


def _validate_upload(f, allowed_exts):
    """Return an error message if uploaded file *f* is unacceptable, else None.

    Rejects a disallowed extension, an empty (0-byte) file, or one over the
    per-file size limit. (Lightweight checks only — no deep raster/GeoTIFF
    inspection; that's a possible future addition.)
    """
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in allowed_exts:
        return f"'{f.name}': unsupported file type (allowed: {', '.join(sorted(allowed_exts))})"
    if not f.size:
        return f"'{f.name}': file is empty"
    if f.size > MAX_UPLOAD_BYTES:
        return f"'{f.name}': exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB per-file limit"
    return None


def _validate_filename(name, allowed_exts):
    """Return an error message if *name* has a disallowed extension, else None.

    Extension-only check for the presigned-upload path, where the bytes go
    straight to storage and the server never sees the file object.
    """
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed_exts:
        return f"'{name}': unsupported file type (allowed: {', '.join(sorted(allowed_exts))})"
    return None


@controller(url='api/upload', login_required=True, name='api_upload')
def api_upload(request):
    """POST: store the benchmark, candidate(s), and optional AOI shapefile bundle
    in object storage under a fresh ``upload_id``; returns the id + S3 keys.

    Multipart fields: ``benchmark`` (one file), ``candidates`` (one or more),
    ``boundary`` (optional shapefile parts, AOI only). 400 on missing benchmark/
    candidates or an invalid boundary bundle; 503 if storage is unavailable.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    benchmark_file = request.FILES.get('benchmark')
    candidate_files = request.FILES.getlist('candidates')
    boundary_files = request.FILES.getlist('boundary')

    if not benchmark_file:
        return JsonResponse({'error': 'benchmark file is required'}, status=400)
    if not candidate_files:
        return JsonResponse({'error': 'at least one candidate file is required'}, status=400)
    if len(candidate_files) > MAX_CANDIDATES:
        return JsonResponse(
            {'error': f'too many candidates (max {MAX_CANDIDATES})'}, status=400,
        )

    # Validate every file (type / non-empty / size) before uploading anything.
    for f in [benchmark_file, *candidate_files]:
        err = _validate_upload(f, RASTER_EXT)
        if err:
            return JsonResponse({'error': err}, status=400)
    if boundary_files:
        for f in boundary_files:
            err = _validate_upload(f, ALLOWED_BOUNDARY_EXT)
            if err:
                return JsonResponse({'error': err}, status=400)
        if not any(os.path.splitext(f.name)[1].lower() == '.shp' for f in boundary_files):
            return JsonResponse(
                {'error': 'shapefile bundle must include a .shp file'}, status=400,
            )

    upload_id = str(uuid.uuid4())
    user_id = str(request.user.id)
    storage = _get_storage()

    try:
        benchmark_key = f'uploads/{user_id}/{upload_id}/benchmark.tif'
        storage.upload_fileobj(benchmark_file, benchmark_key)

        candidate_keys = []
        for i, cfile in enumerate(candidate_files):
            key = f'uploads/{user_id}/{upload_id}/candidate_{i}.tif'
            storage.upload_fileobj(cfile, key)
            candidate_keys.append(key)

        # Boundary components keep their original basenames so the shapefile
        # stem stays consistent across .shp/.shx/.dbf/.prj.
        boundary_keys = []
        for bfile in boundary_files:
            name = os.path.basename(bfile.name)
            key = f'uploads/{user_id}/{upload_id}/boundary/{name}'
            storage.upload_fileobj(bfile, key)
            boundary_keys.append(key)
    except (ClientError, BotoCoreError) as exc:
        # Partial uploads under this upload_id may remain; a scheduled sweep of
        # uploads/ keys with no corresponding job record handles cleanup.
        logger.error('S3 upload failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    return JsonResponse({
        'upload_id': upload_id,
        'benchmark_key': benchmark_key,
        'candidate_keys': candidate_keys,
        'boundary_keys': boundary_keys,
    })


@controller(url='api/upload/presign', login_required=True, name='api_upload_presign')
def api_upload_presign(request):
    """POST ``{benchmark, candidates[], boundary[]}`` (filenames): mint a fresh
    ``upload_id`` and a presigned PUT URL per file so the browser uploads
    directly to MinIO — Django never receives the file bytes.

    Returns ``{upload_id, targets: [{field, filename, key, url}]}`` where
    ``field`` is ``benchmark`` / ``candidate`` / ``boundary``. 400 on a bad
    manifest; 503 if storage is unavailable.

    Note: extension and count are validated here, but a plain presigned PUT
    cannot enforce a per-file size cap server-side (the browser talks straight
    to MinIO), so ``MAX_UPLOAD_BYTES`` is advisory/client-side for this path.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        body = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    benchmark = body.get('benchmark')
    candidates = body.get('candidates') or []
    boundary = body.get('boundary') or []

    if not benchmark:
        return JsonResponse({'error': 'benchmark file is required'}, status=400)
    if not candidates:
        return JsonResponse({'error': 'at least one candidate file is required'}, status=400)
    if len(candidates) > MAX_CANDIDATES:
        return JsonResponse({'error': f'too many candidates (max {MAX_CANDIDATES})'}, status=400)

    for name in [benchmark, *candidates]:
        err = _validate_filename(name, RASTER_EXT)
        if err:
            return JsonResponse({'error': err}, status=400)
    if boundary:
        for name in boundary:
            err = _validate_filename(name, ALLOWED_BOUNDARY_EXT)
            if err:
                return JsonResponse({'error': err}, status=400)
        if not any(os.path.splitext(n)[1].lower() == '.shp' for n in boundary):
            return JsonResponse(
                {'error': 'shapefile bundle must include a .shp file'}, status=400,
            )

    upload_id = str(uuid.uuid4())
    user_id = str(request.user.id)
    prefix = f'uploads/{user_id}/{upload_id}/'
    storage = _get_storage()

    try:
        targets = [{
            'field': 'benchmark',
            'filename': benchmark,
            'key': f'{prefix}benchmark.tif',
            'url': storage.presigned_put_url(f'{prefix}benchmark.tif'),
        }]
        for i, name in enumerate(candidates):
            key = f'{prefix}candidate_{i}.tif'
            targets.append({
                'field': 'candidate', 'filename': name, 'key': key,
                'url': storage.presigned_put_url(key),
            })
        # Boundary components keep their original basenames so the shapefile
        # stem stays consistent across .shp/.shx/.dbf/.prj.
        for name in boundary:
            key = f'{prefix}boundary/{os.path.basename(name)}'
            targets.append({
                'field': 'boundary', 'filename': name, 'key': key,
                'url': storage.presigned_put_url(key),
            })
    except (ClientError, BotoCoreError) as exc:
        logger.error('Presign failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    # Persist the original filenames so the worker can label its input metadata
    # with them (the stored keys are renamed benchmark.tif / candidate_i.tif).
    # Control-plane metadata only — no uploaded file bytes pass through Django.
    try:
        names = {os.path.basename(t['key']): t['filename'] for t in targets}
        storage.upload_bytes(
            json_module.dumps({'names': names}).encode('utf-8'),
            f'{prefix}manifest.json',
        )
    except (ClientError, BotoCoreError) as exc:
        logger.warning('Manifest write failed for upload_id=%s: %s', upload_id, exc)

    return JsonResponse({'upload_id': upload_id, 'targets': targets})


VALID_METHODS = {'smallest_extent', 'convex_hull', 'bootstrap', 'intersected_extent', 'AOI'}

# Control-plane objects the worker writes to the output prefix (terminal markers
# + the input-metadata file); not user-facing output files.
JOB_MARKERS = {'_SUCCESS', '_FAILED', '_RUNNING', 'inputs.json'}


@controller(url='api/jobs', login_required=True, name='api_jobs_submit')
def api_jobs_submit(request):
    """POST ``{upload_id, method}``: submit a FIMeval evaluation as a Dask job.

    Validates the method and that the upload exists (and, for AOI, that a ``.shp``
    is present), then creates and executes a DaskJob. Returns ``{job_id, status}``
    (202). 400 on bad input, 404 unknown upload, 503 if storage/scheduler is down.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        body = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    upload_id = body.get('upload_id')
    method = body.get('method')

    if not upload_id:
        return JsonResponse({'error': 'upload_id is required'}, status=400)
    if method not in VALID_METHODS:
        return JsonResponse({'error': f'method must be one of {sorted(VALID_METHODS)}'}, status=400)

    user_id = str(request.user.id)
    storage = _get_storage()

    try:
        sizes = dict(storage.list_prefix_with_sizes(f'uploads/{user_id}/{upload_id}/'))
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 check failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    if not sizes:
        return JsonResponse({'error': 'upload_id not found'}, status=404)

    # Integrity check. With presigned uploads the bytes bypass Django, so this
    # is the only server-side proof the files actually landed: confirm the
    # benchmark and at least one candidate exist and are non-empty (a silently
    # failed/expired PUT would otherwise submit a job that dies on the worker).
    prefix = f'uploads/{user_id}/{upload_id}/'

    def _basename(key):
        return key.rsplit('/', 1)[-1]

    has_benchmark = sizes.get(f'{prefix}benchmark.tif', 0) > 0
    has_candidate = any(
        _basename(k).startswith('candidate_') and k.endswith('.tif') and size > 0
        for k, size in sizes.items()
    )
    if not has_benchmark or not has_candidate:
        return JsonResponse(
            {'error': 'upload incomplete — please re-upload'}, status=400,
        )
    if method == 'AOI':
        has_shp = any(
            f'{prefix}boundary/' in k and k.endswith('.shp') and size > 0
            for k, size in sizes.items()
        )
        if not has_shp:
            return JsonResponse(
                {'error': 'AOI requires a shapefile (.shp + sidecars)'}, status=400,
            )

    # Guard against a job too large for the worker to process, and offer a
    # downsample path when it is. The working set is estimated post-uniformization
    # (benchmark∩candidate at the coarsest input resolution) rather than from the
    # benchmark's raw pixel count — fimeval downsamples inputs to the coarsest
    # resolution anyway, so raw pixels wrongly reject coarsenable rasters. If the
    # user accepts a downsample (``downsample: true``), we thread the fit
    # resolution to the worker so it actually coarsens instead of OOMing again.
    candidate_names = sorted(
        _basename(k) for k, size in sizes.items()
        if _basename(k).startswith('candidate_') and k.endswith('.tif') and size > 0
    )
    downsample = bool(body.get('downsample'))
    target_resolution = None
    est = _estimate_working_pixels(_get_storage(), prefix, candidate_names)
    if est and est['pixels'] > MAX_EVAL_PIXELS:
        if not downsample:
            return JsonResponse({
                'error': (
                    'This evaluation is too large to run at full resolution '
                    f'(about {est["pixels"] / 1e6:.0f} megapixels of overlapping '
                    'area). You can run it at a coarser resolution instead.'
                ),
                'too_large': True,
                'estimated_mpixels': round(est['pixels'] / 1e6),
                'limit_mpixels': MAX_EVAL_PIXELS // 1_000_000,
            }, status=400)
        target_resolution = est['fit_resolution_m']

    s3_config = {
        'endpoint_url': App.get_custom_setting('minio_endpoint_url'),
        'access_key': App.get_custom_setting('minio_access_key'),
        'secret_key': App.get_custom_setting('minio_secret_key'),
        'bucket': App.get_custom_setting('s3_bucket'),
    }

    try:
        scheduler = App.get_scheduler('dask_primary')
    except Exception:
        return JsonResponse({'error': 'Dask scheduler not configured'}, status=503)

    from tethysapp.fimeval_gui.job_types import REGISTRY

    job_manager = App.get_job_manager()
    job = job_manager.create_job(
        name=f'evaluate_fim_{upload_id}',
        user=request.user,
        job_type=DaskJob,
        scheduler=scheduler,
    )
    job.extended_properties = {
        'upload_id': upload_id,
        'user_id': user_id,
        'method': method,
        'target_resolution': target_resolution,
    }
    delayed = REGISTRY['evaluate_fim'].build_delayed(
        upload_id=upload_id, user_id=user_id, method=method, s3_config=s3_config,
        target_resolution=target_resolution,
    )

    try:
        job.save()
        job.execute(delayed)
    except Exception as exc:
        logger.error('Job submission failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'job submission failed'}, status=503)

    return JsonResponse({'job_id': job.id, 'status': 'submitted'}, status=202)


_DASK_TO_STATUS = {
    'pending':   'queued',
    'processing': 'running',
    'finished':  'complete',
    'error':     'error',
    'cancelled': 'error',
    'lost':      'error',
}

_TETHYS_TO_STATUS = {
    'SUB': 'submitted',
    'RUN': 'running',
    'COM': 'complete',
    'ERR': 'error',
    'ABT': 'error',
    'VAR': 'running',
}

# A running job that never reaches a terminal state — e.g. a worker OOM-killed
# mid-task that never wrote a _FAILED marker, or one stuck in a restart loop —
# would otherwise poll as 'running' forever. Past this wall-clock age it is
# reported as a terminal error so the UI stops polling. Overridable per
# deployment (long-running pools may want a higher ceiling).
_JOB_TIMEOUT_SECONDS = _env_int('FIMEVAL_JOB_TIMEOUT_SECONDS', 30 * 60)


@controller(url='api/jobs/{job_id}', login_required=True, name='api_job_status')
def api_job_status(request, job_id):
    """GET: the job's current status (submitted / queued / running / complete / error).

    Prefers the live Dask future; for the ephemeral-future case it falls back to
    the worker's terminal ``_SUCCESS`` / ``_FAILED`` marker in object storage.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    job, err = _get_owned_job(request, job_id)
    if err:
        return err

    # Try to get live status from the Dask scheduler via the stored future key.
    status = None
    if job.key:
        try:
            client = Client(job.scheduler.host, timeout='5s')
            try:
                dask_status = Future(job.key, client=client).status
                status = _DASK_TO_STATUS.get(dask_status, 'running')
            finally:
                client.close()
        except Exception as exc:
            logger.warning('Dask status check failed for job %s: %s', job_id, exc)

    # Fall back to Tethys stored status if Dask is unreachable or key missing.
    if status is None:
        status = _TETHYS_TO_STATUS.get(job._status, 'submitted')

    props = job.extended_properties or {}

    # Dask futures are ephemeral: once the scheduler forgets a finished/errored
    # future, Future(key) comes back 'pending' → 'queued'. And a live 'pending'
    # is ambiguous — queued at the scheduler OR executing on a worker. Both
    # cases resolve via the markers the worker writes: _RUNNING as its first
    # action, _SUCCESS/_FAILED as its last. _SUCCESS guarantees the full output
    # set is present (so /metrics and /bootstrap won't race), and _FAILED makes
    # a no-output run terminal instead of polling forever. (Live Dask
    # 'finished'/'error' are trusted directly — the worker returns only on
    # success and raises on failure.)
    if status in ('running', 'submitted', 'queued'):
        upload_id = props.get('upload_id')
        user_id = props.get('user_id')
        if upload_id and user_id:
            try:
                names = {
                    k.rsplit('/', 1)[-1]
                    for k in _get_storage().list_prefix(f'outputs/{user_id}/{upload_id}/')
                }
                if '_FAILED' in names:
                    status = 'error'
                elif '_SUCCESS' in names:
                    status = 'complete'
                elif status == 'queued' and names:
                    # _RUNNING marker — or partial outputs from a pre-marker
                    # worker — means a worker has picked the job up.
                    status = 'running'
            except (ClientError, BotoCoreError) as exc:
                logger.warning('S3 marker check failed for job %s: %s', job_id, exc)

    # Wall-clock safety net: a running job that never reached a terminal state
    # is reported as a terminal error past the timeout so the UI stops polling.
    timed_out = False
    if status == 'running' and job.creation_time:
        age = (timezone.now() - job.creation_time).total_seconds()
        if age > _JOB_TIMEOUT_SECONDS:
            status = 'error'
            timed_out = True

    # On failure, surface the reason the worker wrote into the _FAILED marker
    # (fimeval's captured error) so the UI can show it instead of a generic
    # message. Best-effort — a read failure must not break the status response.
    reason = None
    if status == 'error':
        upload_id = props.get('upload_id')
        user_id = props.get('user_id')
        if upload_id and user_id:
            try:
                reason = (
                    _get_storage()
                    .get_object(f'outputs/{user_id}/{upload_id}/_FAILED')['Body']
                    .read()
                    .decode('utf-8', 'replace')
                    .strip()
                ) or None
            except (ClientError, BotoCoreError, KeyError) as exc:
                logger.warning('Failed to read _FAILED reason for job %s: %s', job_id, exc)
        if reason is None and timed_out:
            reason = (
                'Evaluation did not complete in time — the worker may have run '
                'out of memory or the job is too large.'
            )

    # Input metadata (FE14): the names + resolution/CRS the worker published, so
    # the UI can show which files a run is evaluating. Best-effort.
    inputs = None
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')
    if upload_id and user_id:
        try:
            inputs = json_module.loads(
                _get_storage()
                .get_object(f'outputs/{user_id}/{upload_id}/inputs.json')['Body']
                .read()
            )
        except (ClientError, BotoCoreError, KeyError, ValueError) as exc:
            logger.debug('No inputs.json for job %s: %s', job_id, exc)

    return JsonResponse({
        'job_id': job.id,
        'status': status,
        'created': job.creation_time.isoformat() if job.creation_time else None,
        'completed': job.completion_time.isoformat() if job.completion_time else None,
        'method': props.get('method'),
        'upload_id': props.get('upload_id'),
        'reason': reason,
        'inputs': inputs,
    })


@controller(url='api/jobs/{job_id}/outputs', login_required=True, name='api_job_outputs')
def api_job_outputs(request, job_id):
    """GET: list the job's output files as ``{name, key}`` (internal
    ``_SUCCESS`` / ``_FAILED`` markers excluded). 404 if no outputs exist yet.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    job, err = _get_owned_job(request, job_id)
    if err:
        return err

    props = job.extended_properties or {}
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')

    if not upload_id or not user_id:
        return JsonResponse({'error': 'job has no outputs'}, status=404)

    try:
        keys = _get_storage().list_prefix(f'outputs/{user_id}/{upload_id}/')
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 list failed for job %s: %s', job_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    if not keys:
        return JsonResponse({'error': 'no outputs yet'}, status=404)

    files = [
        {'name': k.split('/')[-1], 'key': k}
        for k in keys if k.rsplit('/', 1)[-1] not in JOB_MARKERS
    ]
    return JsonResponse({'job_id': job.id, 'files': files})


@controller(url='api/jobs/{job_id}/download', login_required=True, name='api_job_download')
def api_job_download(request, job_id):
    """GET ``?file=<key>``: 303-redirect to a presigned URL for one output file.
    The key must fall under the job's own ``outputs/`` prefix, else 403.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    file_key = request.GET.get('file')
    if not file_key:
        return JsonResponse({'error': 'file parameter is required'}, status=400)

    job, err = _get_owned_job(request, job_id)
    if err:
        return err

    props = job.extended_properties or {}
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')
    if not file_key.startswith(f'outputs/{user_id}/{upload_id}/'):
        return JsonResponse({'error': 'access denied'}, status=403)

    storage = _get_storage()
    try:
        exists = storage.key_exists(file_key)
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 check failed for job %s key %s: %s', job_id, file_key, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    if not exists:
        return JsonResponse({'error': 'file not found'}, status=404)

    response = HttpResponseRedirect(storage.presigned_url(file_key))
    response.status_code = 303
    return response


@controller(url='api/jobs/{job_id}/metrics', login_required=True, name='api_job_metrics')
def api_job_metrics(request, job_id):
    """GET: ``EvaluationMetrics.csv`` parsed to JSON — ``{candidates, metrics:
    [{metric, values: {candidate: float|null}}]}``. Non-finite values become null.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    job, err = _get_owned_job(request, job_id)
    if err:
        return err

    props = job.extended_properties or {}
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')
    if not upload_id or not user_id:
        return JsonResponse({'error': 'metrics not available yet'}, status=404)

    storage = _get_storage()
    try:
        keys = storage.list_prefix(f'outputs/{user_id}/{upload_id}/')
        metrics_key = next(
            (k for k in keys if k.split('/')[-1] == 'EvaluationMetrics.csv'), None
        )
        if not metrics_key:
            return JsonResponse({'error': 'metrics not available yet'}, status=404)
        raw = storage.get_object(metrics_key)['Body'].read().decode('utf-8', errors='replace')
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 metrics fetch failed for job %s: %s', job_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    rows = [r for r in csv.reader(io.StringIO(raw)) if r]
    if not rows:
        return JsonResponse({'error': 'metrics not available yet'}, status=404)

    candidates = rows[0][1:]
    metrics = []
    for row in rows[1:]:
        name = row[0]
        if name.endswith('_values'):
            name = name[: -len('_values')]
        values = {}
        for i, cand in enumerate(candidates):
            try:
                v = float(row[i + 1])
                values[cand] = v if math.isfinite(v) else None
            except (ValueError, IndexError):
                values[cand] = None
        metrics.append({'metric': name, 'values': values})

    return JsonResponse({'job_id': job.id, 'candidates': candidates, 'metrics': metrics})


@controller(url='api/jobs/{job_id}/download-all', login_required=True, name='api_job_download_all')
def api_job_download_all(request, job_id):
    """GET: stream all of the job's outputs as a single ZIP (markers excluded)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    job, err = _get_owned_job(request, job_id)
    if err:
        return err

    props = job.extended_properties or {}
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')
    method = props.get('method') or 'results'
    if not upload_id or not user_id:
        return JsonResponse({'error': 'no outputs yet'}, status=404)

    prefix = f'outputs/{user_id}/{upload_id}/'
    storage = _get_storage()

    # Stream every output object into a ZIP backed by a temp file (rolled to
    # disk), so the whole archive is never held in memory. FileResponse closes
    # and removes the temp file once the response has been fully sent.
    tmp = tempfile.TemporaryFile()
    try:
        keys = [
            k for k in storage.list_prefix(prefix)
            if not k.endswith('/') and k.rsplit('/', 1)[-1] not in JOB_MARKERS
        ]
        if not keys:
            tmp.close()
            return JsonResponse({'error': 'no outputs yet'}, status=404)
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for key in keys:
                arcname = key[len(prefix):]
                zf.writestr(arcname, storage.get_object(key)['Body'].read())
    except (ClientError, BotoCoreError) as exc:
        tmp.close()
        logger.error('S3 zip build failed for job %s: %s', job_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    tmp.seek(0)
    return FileResponse(
        tmp, as_attachment=True,
        filename=f'fimeval_results_{method}_{job_id}.zip',
        content_type='application/zip',
    )


# Metrics visualized as bootstrap distributions. These match the column headers
# fimeval writes in Random_Sampling/random_<candidate>.csv.
BOOTSTRAP_METRICS = ['CSI', 'POD', 'FAR', 'F1', 'MCC', 'Kappa', 'Accuracy']


def _box_stats(values):
    """Tukey box-plot summary for a list of floats: quartiles, whiskers (the
    extreme values within 1.5*IQR of the box), and outliers beyond them."""
    data = sorted(values)
    n = len(data)
    if n == 0:
        return None
    if n == 1:
        v = data[0]
        return {'min': v, 'q1': v, 'median': v, 'q3': v, 'max': v, 'outliers': [], 'n': 1}
    q1, q2, q3 = statistics.quantiles(data, n=4, method='inclusive')
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    within = [v for v in data if lo <= v <= hi]
    outliers = [v for v in data if v < lo or v > hi]
    return {
        'min': within[0] if within else data[0],
        'q1': q1,
        'median': q2,
        'q3': q3,
        'max': within[-1] if within else data[-1],
        'outliers': outliers,
        'n': n,
    }


@controller(url='api/jobs/{job_id}/bootstrap', login_required=True, name='api_job_bootstrap')
def api_job_bootstrap(request, job_id):
    """GET: bootstrap distribution as box-plot stats per candidate per metric
    (min/q1/median/q3/max/outliers/n), parsed from the ``Random_Sampling`` CSVs.
    404 for non-bootstrap jobs (which have no such CSVs).
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    job, err = _get_owned_job(request, job_id)
    if err:
        return err

    props = job.extended_properties or {}
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')
    if not upload_id or not user_id:
        return JsonResponse({'error': 'no bootstrap results'}, status=404)

    storage = _get_storage()
    try:
        keys = sorted(
            k for k in storage.list_prefix(f'outputs/{user_id}/{upload_id}/')
            if '/Random_Sampling/' in k
            and k.split('/')[-1].startswith('random_')
            and k.endswith('.csv')
        )
        if not keys:
            return JsonResponse({'error': 'no bootstrap results'}, status=404)

        candidates = []
        stats = {}
        for key in keys:
            name = key.split('/')[-1][len('random_'):-len('.csv')]
            raw = storage.get_object(key)['Body'].read().decode('utf-8', errors='replace')
            series = {m: [] for m in BOOTSTRAP_METRICS}
            for row in csv.DictReader(io.StringIO(raw)):
                for m in BOOTSTRAP_METRICS:
                    try:
                        v = float(row[m])
                    except (TypeError, ValueError, KeyError):
                        continue
                    if math.isfinite(v):
                        series[m].append(v)
            candidates.append(name)
            stats[name] = {m: _box_stats(vals) for m, vals in series.items() if vals}
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 bootstrap fetch failed for job %s: %s', job_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    return JsonResponse({
        'job_id': job.id,
        'candidates': candidates,
        'metrics': BOOTSTRAP_METRICS,
        'stats': stats,
    })
