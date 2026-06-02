import os
import tempfile

import boto3


def run_evaluate_fim_task(upload_id: str, user_id: str, method: str, s3_config: dict):
    """Dask worker: download inputs from S3, run EvaluateFIM, upload outputs to S3."""
    import fimeval

    client = boto3.client(
        's3',
        endpoint_url=s3_config.get('endpoint_url') or None,
        aws_access_key_id=s3_config['access_key'],
        aws_secret_access_key=s3_config['secret_key'],
    )
    bucket = s3_config['bucket']
    input_prefix = f'fimeval/uploads/{user_id}/{upload_id}/'
    output_prefix = f'fimeval/outputs/{user_id}/{upload_id}/'

    with tempfile.TemporaryDirectory() as tmpdir:
        # FIMeval expects: main_dir/<case_study_name>/<raster files>
        case_dir = os.path.join(tmpdir, 'case_study')
        os.makedirs(case_dir)

        # Download all input files into the case_study directory
        paginator = client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=input_prefix):
            for obj in page.get('Contents', []):
                filename = obj['Key'].split('/')[-1]
                client.download_file(bucket, obj['Key'], os.path.join(case_dir, filename))

        # Run FIMeval — tmpdir is main_dir (contains case_study subdir)
        output_dir = os.path.join(tmpdir, 'outputs')
        os.makedirs(output_dir)
        fimeval.EvaluateFIM(tmpdir, method, output_dir)

        # Upload everything FIMeval wrote to S3
        for root, _, files in os.walk(output_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, output_dir)
                s3_key = output_prefix + rel_path.replace(os.sep, '/')
                client.upload_file(full_path, bucket, s3_key)


from dask import delayed  # noqa: E402
from tethysapp.fimeval_gui.job_types.registry import JobType  # noqa: E402


class EvaluateFIMJobType(JobType):
    name = 'evaluate_fim'

    def build_delayed(self, upload_id, user_id, method, s3_config):
        return delayed(run_evaluate_fim_task)(upload_id, user_id, method, s3_config)
