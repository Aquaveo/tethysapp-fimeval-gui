import os
import unittest
from unittest.mock import patch

import boto3
from moto import mock_aws

os.environ.setdefault('AWS_ACCESS_KEY_ID', 'test')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'test')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')

BUCKET = 'fimeval-test'
S3_CONFIG = dict(endpoint_url=None, access_key='test', secret_key='test', bucket=BUCKET)


class TestRegistry(unittest.TestCase):
    def test_evaluate_fim_in_registry(self):
        from tethysapp.fimeval_gui.job_types import REGISTRY
        self.assertIn('evaluate_fim', REGISTRY)

    def test_registry_value_is_job_type_instance(self):
        from tethysapp.fimeval_gui.job_types import REGISTRY
        from tethysapp.fimeval_gui.job_types.registry import JobType
        self.assertIsInstance(REGISTRY['evaluate_fim'], JobType)


class TestEvaluateFIMBuildDelayed(unittest.TestCase):
    def test_build_delayed_returns_dask_delayed(self):
        from tethysapp.fimeval_gui.job_types import REGISTRY
        result = REGISTRY['evaluate_fim'].build_delayed(
            upload_id='abc123', user_id='1',
            method='smallest_extent', s3_config=S3_CONFIG,
        )
        self.assertTrue(
            hasattr(result, 'compute'),
            'build_delayed must return a dask.delayed object',
        )


class TestRunEvaluateFIMTask(unittest.TestCase):
    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_downloads_inputs_runs_fimeval_uploads_outputs(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET,
                      Key='uploads/1/abc/benchmark.tif', Body=b'bench')
        s3.put_object(Bucket=BUCKET,
                      Key='uploads/1/abc/candidate_0.tif', Body=b'cand')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, 'EvaluationMetrics.csv'), 'w') as f:
                f.write('metric,value\nCSI,0.85\n')

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        mock_eval.assert_called_once()
        self.assertEqual(mock_eval.call_args.args[1], 'smallest_extent')

        output_keys = [
            obj['Key']
            for page in s3.get_paginator('list_objects_v2').paginate(
                Bucket=BUCKET, Prefix='outputs/1/abc/'
            )
            for obj in page.get('Contents', [])
        ]
        self.assertTrue(
            any('EvaluationMetrics.csv' in k for k in output_keys),
            f'Expected EvaluationMetrics.csv in outputs. Got: {output_keys}',
        )

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_method_convex_hull_passed_to_fimeval(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            os.makedirs(output_dir, exist_ok=True)

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'convex_hull', S3_CONFIG)

        self.assertEqual(mock_eval.call_args.args[1], 'convex_hull')

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_benchmark_file_placed_in_case_study_dir(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        captured = {}

        def fake_eval(main_dir, method, output_dir, **kwargs):
            os.makedirs(output_dir, exist_ok=True)
            # Check file existence while tmpdir is still alive (before context cleanup)
            case_dir = os.path.join(main_dir, 'case_study')
            captured['benchmark_exists'] = os.path.exists(
                os.path.join(case_dir, 'benchmark.tif')
            )

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        self.assertTrue(
            captured.get('benchmark_exists', False),
            'benchmark.tif must exist inside case_study subdir of main_dir',
        )
