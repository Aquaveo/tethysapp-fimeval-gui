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


def _emit_success_outputs(output_dir):
    """Mock helper: simulate a successful fimeval run by writing the metrics CSV
    the worker keys its _SUCCESS marker off of (otherwise the worker treats the
    run as failed, writes _FAILED, and raises)."""
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, 'EvaluationMetrics.csv'), 'w') as f:
        f.write('Metrics,candidate_0\nCSI_values,0.5\n')


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
            _emit_success_outputs(output_dir)
            with open(os.path.join(output_dir, 'EvaluationMetrics.csv'), 'w') as f:
                f.write('metric,value\nCSI,0.85\n')

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        mock_eval.assert_called_once()
        self.assertEqual(mock_eval.call_args.args[1], 'smallest_extent')
        # A target CRS is passed so fimeval reprojects mixed/non-CONUS inputs
        # instead of bailing with no outputs.
        self.assertEqual(mock_eval.call_args.kwargs.get('target_crs'), 'EPSG:5070')

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
        # Terminal success marker written so status reports complete only once
        # the full output set is present.
        self.assertTrue(
            any(k.endswith('/_SUCCESS') for k in output_keys),
            f'Expected _SUCCESS marker. Got: {output_keys}',
        )

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_no_metrics_writes_failed_marker_and_raises(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            # fimeval bailed (e.g. CRS/footprint issue): no EvaluationMetrics.csv.
            os.makedirs(output_dir, exist_ok=True)

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        with self.assertRaises(RuntimeError):
            run_evaluate_fim_task('abc', '1', 'bootstrap', S3_CONFIG)

        keys = [
            obj['Key']
            for page in s3.get_paginator('list_objects_v2').paginate(
                Bucket=BUCKET, Prefix='outputs/1/abc/'
            )
            for obj in page.get('Contents', [])
        ]
        self.assertTrue(any(k.endswith('/_FAILED') for k in keys), keys)
        self.assertFalse(any(k.endswith('/_SUCCESS') for k in keys), keys)

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_failed_marker_captures_fimeval_error_output(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            # fimeval swallows its own exceptions and only PRINTS them, then
            # returns without an EvaluationMetrics.csv. The worker must capture
            # that output so the real cause isn't lost.
            os.makedirs(output_dir, exist_ok=True)
            print(
                'Error processing folder case_study: Too many points '
                '(1296 out of 1296) failed to transform, unable to compute '
                'output bounds.'
            )

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        with self.assertRaises(RuntimeError):
            run_evaluate_fim_task('abc', '1', 'intersected_extent', S3_CONFIG)

        body = (
            s3.get_object(Bucket=BUCKET, Key='outputs/1/abc/_FAILED')['Body']
            .read()
            .decode('utf-8', 'replace')
        )
        self.assertIn('Too many points', body)
        self.assertIn('failed to transform', body)

    def _put_geotiff(self, s3, key, width, height, west, north, res=10, crs='EPSG:5070'):
        """Create a tiny in-memory GeoTIFF and upload it to the mock bucket."""
        import numpy as np
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin
        with MemoryFile() as mem:
            with mem.open(
                driver='GTiff', height=height, width=width, count=1, dtype='uint8',
                crs=crs, transform=from_origin(west, north, res, res),
            ) as ds:
                ds.write(np.ones((height, width), dtype='uint8'), 1)
            s3.put_object(Bucket=BUCKET, Key=key, Body=mem.read())

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_candidate_clipped_to_benchmark_extent(self, mock_eval):
        import rasterio
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        # Small benchmark (200 m box) inside a much larger candidate (2 km box).
        self._put_geotiff(s3, 'uploads/1/abc/benchmark.tif', 20, 20, west=1000, north=2000)
        self._put_geotiff(s3, 'uploads/1/abc/candidate_0.tif', 200, 200, west=0, north=2000)

        captured = {}

        def fake_eval(main_dir, method, output_dir, **kwargs):
            _emit_success_outputs(output_dir)
            with rasterio.open(os.path.join(main_dir, 'case_study', 'candidate_0.tif')) as ds:
                captured['px'] = ds.width * ds.height
                captured['bounds'] = ds.bounds

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        # Candidate started at 200x200 = 40000 px; clipping to the benchmark
        # extent (+buffer) must make it far smaller...
        self.assertLess(captured['px'], 40000 // 4)
        # ...while still covering the benchmark extent [1000,1200]x[1800,2000].
        b = captured['bounds']
        self.assertLessEqual(b.left, 1000)
        self.assertGreaterEqual(b.right, 1200)
        self.assertLessEqual(b.bottom, 1800)
        self.assertGreaterEqual(b.top, 2000)

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_no_overlap_fails_fast_with_reason(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        # Same CRS, disjoint extents — no spatial overlap.
        self._put_geotiff(s3, 'uploads/1/abc/benchmark.tif', 20, 20, west=0, north=100)
        self._put_geotiff(
            s3, 'uploads/1/abc/candidate_0.tif', 20, 20, west=100000, north=100000
        )

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        with self.assertRaises(RuntimeError):
            run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        # fimeval must not run on non-overlapping inputs; the job fails fast with
        # a reason in the _FAILED marker (surfaced to the UI by BE27).
        mock_eval.assert_not_called()
        body = (
            s3.get_object(Bucket=BUCKET, Key='outputs/1/abc/_FAILED')['Body']
            .read()
            .decode('utf-8', 'replace')
        )
        self.assertIn('do not spatially overlap', body)

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_one_bad_candidate_does_not_fail_the_job(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        self._put_geotiff(s3, 'uploads/1/abc/benchmark.tif', 20, 20, west=1000, north=2000)
        # candidate_0 overlaps the benchmark; candidate_1 is disjoint.
        self._put_geotiff(s3, 'uploads/1/abc/candidate_0.tif', 40, 40, west=1000, north=2000)
        self._put_geotiff(
            s3, 'uploads/1/abc/candidate_1.tif', 20, 20, west=500000, north=500000
        )

        captured = {}

        def fake_eval(main_dir, method, output_dir, **kwargs):
            _emit_success_outputs(output_dir)
            captured['case_tifs'] = sorted(
                f for f in os.listdir(os.path.join(main_dir, 'case_study'))
                if f.endswith('.tif')
            )

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        # The job runs: the disjoint candidate is dropped, the valid one kept.
        mock_eval.assert_called_once()
        self.assertIn('candidate_0.tif', captured['case_tifs'])
        self.assertNotIn('candidate_1.tif', captured['case_tifs'])

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_method_convex_hull_passed_to_fimeval(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            _emit_success_outputs(output_dir)

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'convex_hull', S3_CONFIG)

        self.assertEqual(mock_eval.call_args.args[1], 'convex_hull')
        # Only bootstrap needs sub_method; only AOI needs shapefile_dir. Neither
        # should reach EvaluateFIM for other methods.
        self.assertNotIn('sub_method', mock_eval.call_args.kwargs)
        self.assertNotIn('shapefile_dir', mock_eval.call_args.kwargs)

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_aoi_routes_boundary_and_passes_shapefile_dir(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')
        for ext in ('shp', 'shx', 'dbf', 'prj'):
            s3.put_object(Bucket=BUCKET, Key=f'uploads/1/abc/boundary/aoi.{ext}', Body=b'x')

        captured = {}

        def fake_eval(main_dir, method, output_dir, **kwargs):
            _emit_success_outputs(output_dir)
            captured['case_files'] = sorted(os.listdir(os.path.join(main_dir, 'case_study')))
            captured['shapefile_dir'] = kwargs.get('shapefile_dir')
            captured['shp_exists'] = bool(kwargs.get('shapefile_dir')) and os.path.exists(
                kwargs['shapefile_dir']
            )

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'AOI', S3_CONFIG)

        self.assertEqual(mock_eval.call_args.args[1], 'AOI')
        # Rasters only in case_dir — boundary parts must be routed elsewhere.
        self.assertEqual(captured['case_files'], ['benchmark.tif', 'candidate_0.tif'])
        # shapefile_dir points at the downloaded .shp and the file exists.
        self.assertTrue(captured['shapefile_dir'].endswith('aoi.shp'))
        self.assertTrue(captured['shp_exists'])

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_bootstrap_passes_sub_method_random(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            _emit_success_outputs(output_dir)

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'bootstrap', S3_CONFIG)

        self.assertEqual(mock_eval.call_args.args[1], 'bootstrap')
        # EvaluateFIM's sub_method default (None) crashes run_bootstrap; the worker
        # must pass 'random' so bootstrap runs.
        self.assertEqual(mock_eval.call_args.kwargs.get('sub_method'), 'random')

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_benchmark_file_placed_in_case_study_dir(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        captured = {}

        def fake_eval(main_dir, method, output_dir, **kwargs):
            _emit_success_outputs(output_dir)
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

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_running_marker_written_before_compute(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        captured = {}

        def fake_eval(main_dir, method, output_dir, **kwargs):
            # The start marker must already be in S3 while compute runs — it is
            # how the status endpoint distinguishes 'running' from 'queued'.
            keys = [
                obj['Key']
                for page in s3.get_paginator('list_objects_v2').paginate(
                    Bucket=BUCKET, Prefix='outputs/1/abc/'
                )
                for obj in page.get('Contents', [])
            ]
            captured['marker_during_compute'] = any(
                k.endswith('/_RUNNING') for k in keys
            )
            _emit_success_outputs(output_dir)

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

        self.assertTrue(captured.get('marker_during_compute', False))

    @mock_aws
    @patch('fimeval.EvaluateFIM')
    def test_running_marker_coexists_with_terminal_marker_on_failure(self, mock_eval):
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif', Body=b'b')
        s3.put_object(Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif', Body=b'c')

        def fake_eval(main_dir, method, output_dir, **kwargs):
            os.makedirs(output_dir, exist_ok=True)  # no metrics → failure path

        mock_eval.side_effect = fake_eval

        from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
        with self.assertRaises(RuntimeError):
            run_evaluate_fim_task('abc', '1', 'bootstrap', S3_CONFIG)

        keys = [
            obj['Key']
            for page in s3.get_paginator('list_objects_v2').paginate(
                Bucket=BUCKET, Prefix='outputs/1/abc/'
            )
            for obj in page.get('Contents', [])
        ]
        # Both markers present; terminal wins at the status endpoint (Task 3).
        self.assertTrue(any(k.endswith('/_RUNNING') for k in keys), keys)
        self.assertTrue(any(k.endswith('/_FAILED') for k in keys), keys)
