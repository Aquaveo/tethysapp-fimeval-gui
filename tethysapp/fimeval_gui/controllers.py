import json as json_module
import logging
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from django.http import JsonResponse
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


VALID_METHODS = {'smallest_extent', 'convex_hull'}


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

    from tethys_sdk.jobs import DaskJob
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
    job.dask_delayed = REGISTRY['evaluate_fim'].build_delayed(
        upload_id=upload_id, user_id=user_id, method=method, s3_config=s3_config,
    )

    try:
        job.save()
        job.execute()
    except Exception as exc:
        logger.error('Job submission failed for upload_id=%s: %s', upload_id, exc)
        return JsonResponse({'error': 'job submission failed'}, status=503)

    return JsonResponse({'job_id': job.id, 'status': 'submitted'}, status=202)
