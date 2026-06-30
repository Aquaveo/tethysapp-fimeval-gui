import os
import tempfile

import boto3
from dask import delayed

from tethysapp.fimeval_gui.job_types.registry import JobType

# CONUS Albers. Passed to fimeval so it reprojects all inputs to a common CRS
# instead of bailing ("Mixed or non-CONUS CRS detected") when the benchmark and
# candidate are in different CRSs. Without a target CRS fimeval only
# auto-reprojects when every input passes its is_within_conus() check.
TARGET_CRS = 'EPSG:5070'


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
    input_prefix = f'uploads/{user_id}/{upload_id}/'
    output_prefix = f'outputs/{user_id}/{upload_id}/'

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
        fimeval.EvaluateFIM(tmpdir, method, output_dir, target_crs=TARGET_CRS, **extra)

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
        # footprint-intersection issue) and produced no usable results.
        succeeded = 'EvaluationMetrics.csv' in produced
        client.put_object(
            Bucket=bucket,
            Key=output_prefix + ('_SUCCESS' if succeeded else '_FAILED'),
            Body=b'',
        )
        if not succeeded:
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
        )
