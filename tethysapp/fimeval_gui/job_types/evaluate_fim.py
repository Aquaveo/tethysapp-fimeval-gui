import contextlib
import io
import json
import os
import tempfile

import boto3
from dask import delayed

from tethysapp.fimeval_gui.job_types.registry import JobType

# CONUS Albers. Passed to fimeval so it reprojects all inputs to a common CRS
# instead of bailing ("Mixed or non-CONUS CRS detected") when the benchmark and
# candidate are in different CRSs. Without a target CRS fimeval only
# auto-reprojects when every input passes its is_within_conus() check.
# Overridable per deployment (e.g. a non-CONUS region) via env var.
TARGET_CRS = os.environ.get('FIMEVAL_TARGET_CRS', 'EPSG:5070')


def _extract_failure_reason(captured_output: str) -> str:
    """Pull the meaningful failure line(s) out of fimeval's captured stdout.

    fimeval prints ``Error evaluating <name>: <msg>`` / ``Error processing ...``
    when it swallows an exception and returns without metrics. Prefer those
    lines; otherwise fall back to the tail of the output. Bounded so the
    ``_FAILED`` marker body stays small.
    """
    lines = [ln for ln in captured_output.splitlines() if ln.strip()]
    err_lines = [
        ln for ln in lines if 'Error evaluating' in ln or 'Error processing' in ln
    ]
    reason = '\n'.join(err_lines or lines[-5:]).strip()
    return reason[-2000:]


class _NoOverlapError(Exception):
    """A candidate raster does not spatially overlap the benchmark."""


def _clip_candidate_to_bounds(candidate_path, bounds, name):
    """Clip ``candidate_path`` in place to ``bounds`` (in the candidate's CRS)."""
    import rasterio
    from rasterio.windows import from_bounds

    left, bottom, right, top = bounds
    with rasterio.open(candidate_path) as src:
        cl, cb, cr, ct = src.bounds
        ileft, ibottom = max(left, cl), max(bottom, cb)
        iright, itop = min(right, cr), min(top, ct)
        if ileft >= iright or ibottom >= itop:
            raise _NoOverlapError(
                f"Benchmark and candidate '{name}' do not spatially overlap — "
                f"check the inputs' coordinates and CRS."
            )
        window = from_bounds(ileft, ibottom, iright, itop, src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(window=window)
        profile = src.profile.copy()
        profile.update(
            height=int(window.height),
            width=int(window.width),
            transform=src.window_transform(window),
        )
        # profile carries dtype/CRS/nodata/count; also preserve band tags and any
        # colormap so the clip is equivalent to the source in all but extent.
        src_tags = src.tags()
        try:
            src_colormap = src.colormap(1)
        except (ValueError, IndexError):
            src_colormap = None
    with rasterio.open(candidate_path, 'w', **profile) as dst:
        dst.write(data)
        if src_tags:
            dst.update_tags(**src_tags)
        if src_colormap:
            try:
                dst.write_colormap(1, src_colormap)
            except (ValueError, TypeError):
                pass


def _clip_candidates_to_benchmark(case_dir, buffer_frac=0.05):
    """Shrink each candidate raster to the benchmark's extent (+ a buffer) so
    fimeval doesn't load and reproject the *full* candidate — a large candidate
    otherwise blows the worker memory budget (FIMEVAL-BE31). Metric-safe: the
    evaluation only ever covers benchmark ∩ candidate.

    A candidate that doesn't intersect the benchmark is dropped (its file is
    removed) and the run continues on the remaining candidates. Raises
    ``_NoOverlapError`` only when NO candidate overlaps the benchmark (nothing
    left to evaluate). Any other read/clip problem is skipped (the job falls
    back to the full candidate).
    """
    import rasterio
    from rasterio.warp import transform_bounds

    bench_path = os.path.join(case_dir, 'benchmark.tif')
    try:
        with rasterio.open(bench_path) as bench:
            bench_bounds, bench_crs = bench.bounds, bench.crs
    except Exception:
        return  # unreadable benchmark — leave the inputs for fimeval to handle
    if bench_crs is None:
        return

    candidates = [
        f for f in sorted(os.listdir(case_dir))
        if f != 'benchmark.tif' and f.lower().endswith('.tif')
    ]
    for fname in candidates:
        cpath = os.path.join(case_dir, fname)
        try:
            with rasterio.open(cpath) as cand:
                cand_crs = cand.crs
            if cand_crs is None:
                continue
            left, bottom, right, top = transform_bounds(
                bench_crs, cand_crs, *bench_bounds
            )
            bw, bh = (right - left) * buffer_frac, (top - bottom) * buffer_frac
            _clip_candidate_to_bounds(
                cpath, (left - bw, bottom - bh, right + bw, top + bh), fname
            )
        except _NoOverlapError:
            # One non-overlapping candidate must not fail the whole job — drop it
            # and keep evaluating the valid candidates.
            os.remove(cpath)
            print(f'BE31: dropped non-overlapping candidate {fname}')
        except Exception as exc:  # non-fatal: fall back to the full candidate
            print(f'BE31: skipped pre-clip of {fname}: {exc}')

    remaining = [
        f for f in os.listdir(case_dir)
        if f != 'benchmark.tif' and f.lower().endswith('.tif')
    ]
    if candidates and not remaining:
        raise _NoOverlapError(
            "The benchmark and candidate(s) do not spatially overlap — "
            "check their coordinates and CRS."
        )


def _read_raster_crs_res(path):
    """Return ``{'resolution': [x, y], 'crs': 'EPSG:...'}`` for a raster, or
    ``None`` values if it can't be read."""
    import rasterio

    try:
        with rasterio.open(path) as ds:
            return {
                'resolution': [ds.res[0], ds.res[1]],
                'crs': str(ds.crs) if ds.crs else None,
            }
    except Exception:
        return {'resolution': None, 'crs': None}


def _read_vector_crs(shp_path):
    """Return a shapefile's CRS as ``'EPSG:...'`` (from its ``.prj``), or None."""
    try:
        prj = os.path.splitext(shp_path)[0] + '.prj'
        if os.path.exists(prj):
            from pyproj import CRS

            crs = CRS.from_wkt(open(prj).read())
            epsg = crs.to_epsg()
            return f'EPSG:{epsg}' if epsg else crs.to_string()
    except Exception:
        pass
    return None


def run_evaluate_fim_task(upload_id: str, user_id: str, method: str, s3_config: dict,
                          target_resolution=None):
    """Dask worker task: run one FIMeval evaluation end-to-end.

    Downloads the job's inputs from ``uploads/<user_id>/<upload_id>/`` (rasters
    into a case-study dir; any AOI shapefile into a separate dir), runs
    ``fimeval.EvaluateFIM`` for ``method`` — reprojecting to ``TARGET_CRS``, with
    ``sub_method='random'`` for bootstrap and ``shapefile_dir`` for AOI — uploads
    all outputs to ``outputs/<user_id>/<upload_id>/``, then writes a terminal
    ``_SUCCESS`` / ``_FAILED`` marker as its final action.

    Raises ``RuntimeError`` if no ``EvaluationMetrics.csv`` was produced, so the
    Dask future errors and the job is reported failed rather than hanging.

    Args:
        upload_id: UUID identifying this job's input/output prefix.
        user_id: owning user's id (part of the S3 key namespace).
        method: a fimeval extent method (``smallest_extent``, ``convex_hull``,
            ``intersected_extent``, ``bootstrap``, ``AOI``).
        s3_config: ``endpoint_url`` / ``access_key`` / ``secret_key`` / ``bucket``.
    """
    import fimeval

    client = boto3.client(
        's3',
        endpoint_url=s3_config.get('endpoint_url') or None,
        aws_access_key_id=s3_config['access_key'],
        aws_secret_access_key=s3_config['secret_key'],
    )
    bucket = s3_config['bucket']
    input_prefix = f'uploads/{user_id}/{upload_id}/'
    output_prefix = f'outputs/{user_id}/{upload_id}/'

    # Signal that a worker has actually picked this job up (vs. queued at the
    # scheduler): the status endpoint reads this to report 'running' instead of
    # 'queued'. Best-effort — a failed put must never block the evaluation.
    try:
        client.put_object(Bucket=bucket, Key=output_prefix + '_RUNNING', Body=b'')
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as tmpdir:
        # FIMeval expects: main_dir/<case_study_name>/<raster files>
        case_dir = os.path.join(tmpdir, 'case_study')
        os.makedirs(case_dir)

        # Download inputs. Rasters go into case_dir; an AOI shapefile bundle
        # (stored under <prefix>boundary/) goes into a separate dir so it isn't
        # mixed in with the rasters fimeval evaluates. Track the .shp path.
        boundary_dir = os.path.join(tmpdir, 'boundary')
        shapefile_path = None
        paginator = client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=input_prefix):
            for obj in page.get('Contents', []):
                rel = obj['Key'][len(input_prefix):]
                if not rel:  # skip S3 directory marker objects
                    continue
                if rel.startswith('boundary/'):
                    os.makedirs(boundary_dir, exist_ok=True)
                    dest = os.path.join(boundary_dir, os.path.basename(rel))
                    if rel.endswith('.shp'):
                        shapefile_path = dest
                else:
                    dest = os.path.join(case_dir, os.path.basename(rel))
                client.download_file(bucket, obj['Key'], dest)

        # Publish input metadata (FE14): map the renamed files back to their
        # original names (from the presign manifest) and read res/CRS from the
        # local downloads, so the UI can show which files a run is evaluating.
        # Written before the (long) evaluation so it's available while running.
        # Best-effort — never fatal to the run.
        try:
            names = json.loads(
                client.get_object(Bucket=bucket, Key=input_prefix + 'manifest.json')[
                    'Body'
                ].read()
            ).get('names', {})
        except Exception:
            names = {}

        def _labelled(fname, path):
            meta = _read_raster_crs_res(path)
            meta['name'] = names.get(fname, fname)
            return meta

        inputs_meta = {
            'benchmark': _labelled(
                'benchmark.tif', os.path.join(case_dir, 'benchmark.tif')
            ),
            'candidates': [
                _labelled(f, os.path.join(case_dir, f))
                for f in sorted(os.listdir(case_dir))
                if f != 'benchmark.tif' and f.lower().endswith('.tif')
            ],
        }
        if shapefile_path:
            shp_name = os.path.basename(shapefile_path)
            inputs_meta['boundary'] = {
                'name': names.get(shp_name, shp_name),
                'crs': _read_vector_crs(shapefile_path),
            }
        try:
            client.put_object(
                Bucket=bucket,
                Key=output_prefix + 'inputs.json',
                Body=json.dumps(inputs_meta).encode('utf-8'),
            )
        except Exception:
            pass

        # Pre-clip each candidate to the benchmark extent so fimeval doesn't load
        # and reproject the full (possibly 300+ Mpx) candidate (FIMEVAL-BE31).
        # Non-overlapping inputs can't be evaluated — fail fast with a reason in
        # the _FAILED marker (surfaced to the UI by BE27) instead of letting
        # fimeval churn and bail with a generic message.
        try:
            _clip_candidates_to_benchmark(case_dir)
        except _NoOverlapError as exc:
            client.put_object(
                Bucket=bucket,
                Key=output_prefix + '_FAILED',
                Body=str(exc).encode('utf-8'),
            )
            raise RuntimeError(str(exc)) from exc

        # Run FIMeval — tmpdir is main_dir (contains case_study subdir)
        output_dir = os.path.join(tmpdir, 'outputs')
        os.makedirs(output_dir)
        # EvaluateFIM's sub_method defaults to None and forwards it into
        # run_bootstrap, which calls sub_method.lower() and crashes. Pass the
        # library's own documented default ('random') so bootstrap runs; the
        # other methods ignore sub_method. n_iterations/n_points stay at fimeval
        # defaults (100/500).
        extra = {'sub_method': 'random'} if method == 'bootstrap' else {}
        # AOI evaluates against a user-supplied boundary shapefile.
        if method == 'AOI' and shapefile_path:
            extra['shapefile_dir'] = shapefile_path
        # When the user accepted a downsample at submit (job too large at full
        # resolution), fimeval resamples every input to this resolution (meters)
        # so the working set actually fits. None = use the coarsest input res.
        if target_resolution:
            extra['target_resolution'] = target_resolution
        # fimeval swallows its own exceptions and only PRINTS them, returning
        # with no EvaluationMetrics.csv. Capture its output so the real cause is
        # preserved (in the _FAILED marker) instead of a generic message.
        fimeval_output = io.StringIO()
        with contextlib.redirect_stdout(fimeval_output), \
                contextlib.redirect_stderr(fimeval_output):
            fimeval.EvaluateFIM(
                tmpdir, method, output_dir, target_crs=TARGET_CRS, **extra
            )
        captured = fimeval_output.getvalue()
        if captured:  # keep fimeval's output in the worker log too
            print(captured, end='')

        # Upload everything FIMeval wrote to S3
        produced = set()
        for root, _, files in os.walk(output_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, output_dir)
                s3_key = output_prefix + rel_path.replace(os.sep, '/')
                client.upload_file(full_path, bucket, s3_key)
                produced.add(fname)

        # Write a terminal marker LAST, so the status endpoint only reports a
        # terminal state once the full output set is present (no race with
        # /metrics or /bootstrap). EvaluationMetrics.csv is written only on a
        # successful evaluation; its absence means fimeval bailed (e.g. a CRS or
        # footprint-intersection issue) and produced no usable results — the
        # _FAILED marker then carries the captured reason so the UI can show it.
        succeeded = 'EvaluationMetrics.csv' in produced
        if succeeded:
            client.put_object(Bucket=bucket, Key=output_prefix + '_SUCCESS', Body=b'')
        else:
            reason = _extract_failure_reason(captured)
            client.put_object(
                Bucket=bucket,
                Key=output_prefix + '_FAILED',
                Body=reason.encode('utf-8'),
            )
            raise RuntimeError(
                f'fimeval produced no EvaluationMetrics.csv; evaluation failed '
                f'(method={method}, upload_id={upload_id})'
            )


class EvaluateFIMJobType(JobType):
    name = 'evaluate_fim'

    def build_delayed(self, **params):
        return delayed(run_evaluate_fim_task)(
            params['upload_id'],
            params['user_id'],
            params['method'],
            params['s3_config'],
            target_resolution=params.get('target_resolution'),
        )
