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
                name='s3_public_endpoint_url',
                type=CustomSetting.TYPE_STRING,
                description=(
                    'Browser-facing object-storage URL used for presigned upload/download '
                    'URLs. Leave blank to reuse the server storage endpoint (correct for '
                    'local dev); set in production when the browser reaches storage at a '
                    'different host than the server does.'
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
            CustomSetting(
                name='basemap_layers',
                type=CustomSetting.TYPE_STRING,
                description=(
                    'Basemaps the contingency-map viewer offers, as a comma-separated '
                    'list of: satellite, street, topographic. Order sets the switcher '
                    'order; leave blank for all three (Satellite default).'
                ),
                required=False,
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
