import csv
import io
import json as json_module
import logging
import math
import statistics
import tempfile
import uuid
import zipfile

from botocore.exceptions import BotoCoreError, ClientError
from distributed import Client, Future
from django.http import FileResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from tethys_sdk.jobs import DaskJob
from tethys_sdk.routing import controller

from tethysapp.fimeval_gui.app import App

logger = logging.getLogger(__name__)


def _get_storage():
    from tethysapp.fimeval_gui.storage import S3Storage
    return S3Storage(
        endpoint_url=App.get_custom_setting('minio_endpoint_url'),
        access_key=App.get_custom_setting('minio_access_key'),
        secret_key=App.get_custom_setting('minio_secret_key'),
        bucket=App.get_custom_setting('s3_bucket'),
    )


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


@controller(url='api/upload', login_required=True, name='api_upload')
def api_upload(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    benchmark_file = request.FILES.get('benchmark')
    candidate_files = request.FILES.getlist('candidates')

    if not benchmark_file:
        return JsonResponse({'error': 'benchmark file is required'}, status=400)
    if not candidate_files:
        return JsonResponse({'error': 'at least one candidate file is required'}, status=400)

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
    except (ClientError, BotoCoreError) as exc:
        # Partial uploads under this upload_id may remain; a scheduled sweep of
        # uploads/ keys with no corresponding job record handles cleanup.
        logger.error('S3 upload failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    return JsonResponse({
        'upload_id': upload_id,
        'benchmark_key': benchmark_key,
        'candidate_keys': candidate_keys,
    })


VALID_METHODS = {'smallest_extent', 'convex_hull', 'bootstrap'}


@controller(url='api/jobs', login_required=True, name='api_jobs_submit')
def api_jobs_submit(request):
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
        if not storage.list_prefix(f'uploads/{user_id}/{upload_id}/'):
            return JsonResponse({'error': 'upload_id not found'}, status=404)
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 check failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

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
    }
    delayed = REGISTRY['evaluate_fim'].build_delayed(
        upload_id=upload_id, user_id=user_id, method=method, s3_config=s3_config,
    )

    try:
        job.save()
        job.execute(delayed)
    except Exception as exc:
        logger.error('Job submission failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'job submission failed'}, status=503)

    return JsonResponse({'job_id': job.id, 'status': 'submitted'}, status=202)


_DASK_TO_STATUS = {
    'pending':   'running',
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


@controller(url='api/jobs/{job_id}', login_required=True, name='api_job_status')
def api_job_status(request, job_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

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

    # Dask future records are ephemeral: once the scheduler forgets a completed
    # future, Future(key) comes back as 'pending'. Cross-check against S3 —
    # if outputs already landed, the job completed successfully.
    if status == 'running':
        upload_id = props.get('upload_id')
        user_id = props.get('user_id')
        if upload_id and user_id:
            try:
                if _get_storage().list_prefix(f'outputs/{user_id}/{upload_id}/'):
                    status = 'complete'
            except (ClientError, BotoCoreError) as exc:
                logger.warning('S3 output check failed for job %s: %s', job_id, exc)

    return JsonResponse({
        'job_id': job.id,
        'status': status,
        'created': job.creation_time.isoformat() if job.creation_time else None,
        'completed': job.completion_time.isoformat() if job.completion_time else None,
        'method': props.get('method'),
        'upload_id': props.get('upload_id'),
    })


@controller(url='api/jobs/{job_id}/outputs', login_required=True, name='api_job_outputs')
def api_job_outputs(request, job_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

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

    files = [{'name': k.split('/')[-1], 'key': k} for k in keys]
    return JsonResponse({'job_id': job.id, 'files': files})


@controller(url='api/jobs/{job_id}/download', login_required=True, name='api_job_download')
def api_job_download(request, job_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    file_key = request.GET.get('file')
    if not file_key:
        return JsonResponse({'error': 'file parameter is required'}, status=400)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

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
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

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
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

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
        keys = [k for k in storage.list_prefix(prefix) if not k.endswith('/')]
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
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

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
