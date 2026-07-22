from tethys_sdk.base import TethysAppBase
from tethys_sdk.app_settings import CustomSetting, SchedulerSetting


class App(TethysAppBase):
    """FIMeval GUI Tethys App."""

    name = 'FIMeval GUI'
    package = 'fimeval_gui'
    root_url = 'fimeval-gui'
    index = 'home'
    catch_all = 'home'
    
    icon = f'{package}/images/android-chrome-512x512.png'
    description = 'Webapp GUI for the FIMeval flood inundation map evaluation framework'
    color = '#007bff'
    tags = 'FIM, Flood Mapping, Flood Inundation Mapping, Hydrology, Evaluation, GIS'
    enable_feedback = False
    feedback_emails = []

    def custom_settings(self):
        return (
            CustomSetting(
                name='minio_endpoint_url',
                type=CustomSetting.TYPE_STRING,
                description='MinIO/S3 endpoint URL (e.g. http://127.0.0.1:9000). Leave blank for real AWS.',
                required=False,
            ),
            CustomSetting(
                name='minio_public_endpoint_url',
                type=CustomSetting.TYPE_STRING,
                description=(
                    'Browser-facing MinIO/S3 URL used for presigned upload/download URLs. '
                    'Leave blank to reuse minio_endpoint_url (correct for local dev).'
                ),
                required=False,
            ),
            CustomSetting(
                name='minio_access_key',
                type=CustomSetting.TYPE_STRING,
                description='MinIO/S3 access key',
                required=True,
            ),
            CustomSetting(
                name='minio_secret_key',
                type=CustomSetting.TYPE_STRING,
                description='MinIO/S3 secret key',
                required=True,
            ),
            CustomSetting(
                name='s3_bucket',
                type=CustomSetting.TYPE_STRING,
                description='S3/MinIO bucket name (e.g. fimeval)',
                required=True,
            ),
        )

    def scheduler_settings(self):
        return (
            SchedulerSetting(
                name='dask_primary',
                description='Primary Dask scheduler for async FIMeval jobs',
                engine=SchedulerSetting.DASK,
                required=False,
            ),
        )
