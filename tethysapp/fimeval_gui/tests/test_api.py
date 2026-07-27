import io
import json
import os
import uuid
import zipfile
from unittest.mock import MagicMock, patch

import boto3
from botocore.exceptions import ClientError
from django.core.files.uploadedfile import SimpleUploadedFile
from moto import mock_aws
from tethys_sdk.testing import TethysTestCase

os.environ.setdefault('AWS_ACCESS_KEY_ID', 'test')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'test')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')

BUCKET = 'fimeval-test'


def _app_settings_side_effect(name):
    return {
        'minio_endpoint_url': None,
        'minio_access_key': 'test',
        'minio_secret_key': 'test',
        's3_bucket': BUCKET,
    }[name]


class TestUploadEndpoint(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.mock_s3 = mock_aws()
        self.mock_s3.start()
        boto3.client('s3', region_name='us-east-1').create_bucket(Bucket=BUCKET)

        self.app_patcher = patch('tethysapp.fimeval_gui.controllers.App')
        self.mock_app = self.app_patcher.start()
        self.mock_app.get_custom_setting.side_effect = _app_settings_side_effect

        self.user = self.create_test_user(username='alice', password='pw', email='a@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def tearDown(self):
        self.app_patcher.stop()
        self.mock_s3.stop()
        super().tearDown()

    def test_upload_returns_upload_id_and_keys(self):
        benchmark = SimpleUploadedFile('benchmark_2024.tif', b'bench data', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate_A.tif', b'cand data', content_type='image/tiff')

        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate]},
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertIn('upload_id', body)
        uuid.UUID(body['upload_id'])  # raises ValueError if not a valid UUID
        self.assertIn('benchmark_key', body)
        self.assertIn('candidate_keys', body)
        self.assertEqual(len(body['candidate_keys']), 1)
        self.assertIn('benchmark.tif', body['benchmark_key'])

    def test_upload_stores_boundary_bundle(self):
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate.tif', b'c', content_type='image/tiff')
        shp = SimpleUploadedFile('aoi.shp', b'shp', content_type='application/octet-stream')
        shx = SimpleUploadedFile('aoi.shx', b'shx', content_type='application/octet-stream')
        dbf = SimpleUploadedFile('aoi.dbf', b'dbf', content_type='application/octet-stream')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate], 'boundary': [shp, shx, dbf]},
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(len(body['boundary_keys']), 3)
        upload_id = body['upload_id']
        user_id = str(self.user.id)
        s3 = boto3.client('s3', region_name='us-east-1')
        obj = s3.get_object(
            Bucket=BUCKET, Key=f'uploads/{user_id}/{upload_id}/boundary/aoi.shp'
        )
        self.assertEqual(obj['Body'].read(), b'shp')

    def test_upload_no_boundary_returns_empty_list(self):
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate.tif', b'c', content_type='image/tiff')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['boundary_keys'], [])

    def test_upload_boundary_rejects_unsupported_ext(self):
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate.tif', b'c', content_type='image/tiff')
        bad = SimpleUploadedFile('aoi.txt', b'x', content_type='text/plain')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate], 'boundary': [bad]},
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_boundary_requires_shp(self):
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate.tif', b'c', content_type='image/tiff')
        shx = SimpleUploadedFile('aoi.shx', b'x', content_type='application/octet-stream')
        dbf = SimpleUploadedFile('aoi.dbf', b'x', content_type='application/octet-stream')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate], 'boundary': [shx, dbf]},
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_non_raster_benchmark(self):
        benchmark = SimpleUploadedFile('benchmark.png', b'data', content_type='image/png')
        candidate = SimpleUploadedFile('candidate.tif', b'c', content_type='image/tiff')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate]},
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_too_many_candidates(self):
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        candidates = [
            SimpleUploadedFile(f'c{i}.tif', b'c', content_type='image/tiff') for i in range(11)
        ]
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': candidates},
        )
        self.assertEqual(response.status_code, 400)

    def test_validate_upload_rules(self):
        from types import SimpleNamespace
        from tethysapp.fimeval_gui.controllers import (
            _validate_upload, RASTER_EXT, MAX_UPLOAD_BYTES,
        )
        self.assertIsNone(_validate_upload(SimpleNamespace(name='ok.tif', size=100), RASTER_EXT))
        self.assertIsNotNone(_validate_upload(SimpleNamespace(name='x.png', size=100), RASTER_EXT))
        self.assertIsNotNone(_validate_upload(SimpleNamespace(name='empty.tif', size=0), RASTER_EXT))
        self.assertIsNotNone(
            _validate_upload(SimpleNamespace(name='big.tif', size=MAX_UPLOAD_BYTES + 1), RASTER_EXT)
        )

    def test_upload_stores_benchmark_in_s3(self):
        benchmark = SimpleUploadedFile('benchmark_2024.tif', b'bench data', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate_A.tif', b'cand data', content_type='image/tiff')

        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate]},
        )
        body = json.loads(response.content)
        upload_id = body['upload_id']
        user_id = str(self.user.id)

        s3 = boto3.client('s3', region_name='us-east-1')
        obj = s3.get_object(
            Bucket=BUCKET, Key=f'uploads/{user_id}/{upload_id}/benchmark.tif'
        )
        self.assertEqual(obj['Body'].read(), b'bench data')

    def test_upload_stores_candidate_in_s3(self):
        benchmark = SimpleUploadedFile('benchmark_2024.tif', b'bench data', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate_A.tif', b'cand data', content_type='image/tiff')

        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': [candidate]},
        )
        body = json.loads(response.content)
        upload_id = body['upload_id']
        user_id = str(self.user.id)

        s3 = boto3.client('s3', region_name='us-east-1')
        obj = s3.get_object(
            Bucket=BUCKET, Key=f'uploads/{user_id}/{upload_id}/candidate_0.tif'
        )
        self.assertEqual(obj['Body'].read(), b'cand data')

    def test_upload_requires_login(self):
        client = self.get_test_client()  # not logged in
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        response = client.post('/apps/fimeval-gui/api/upload/', {'benchmark': benchmark})
        self.assertIn(response.status_code, [302, 403])

    def test_upload_missing_benchmark_returns_400(self):
        candidate = SimpleUploadedFile('candidate_A.tif', b'c', content_type='image/tiff')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'candidates': [candidate]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_upload_missing_candidates_returns_400(self):
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_wrong_method_returns_405(self):
        response = self.client.get('/apps/fimeval-gui/api/upload/')
        self.assertEqual(response.status_code, 405)

    def test_upload_multiple_candidates(self):
        benchmark = SimpleUploadedFile('benchmark_2024.tif', b'bench data', content_type='image/tiff')
        candidates = [
            SimpleUploadedFile('cand_A.tif', b'cand A', content_type='image/tiff'),
            SimpleUploadedFile('cand_B.tif', b'cand B', content_type='image/tiff'),
            SimpleUploadedFile('cand_C.tif', b'cand C', content_type='image/tiff'),
        ]
        response = self.client.post(
            '/apps/fimeval-gui/api/upload/',
            {'benchmark': benchmark, 'candidates': candidates},
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(len(body['candidate_keys']), 3)

        s3 = boto3.client('s3', region_name='us-east-1')
        user_id = str(self.user.id)
        upload_id = body['upload_id']
        for i, expected in enumerate([b'cand A', b'cand B', b'cand C']):
            obj = s3.get_object(
                Bucket=BUCKET, Key=f'uploads/{user_id}/{upload_id}/candidate_{i}.tif'
            )
            self.assertEqual(obj['Body'].read(), expected)

    def test_s3_failure_returns_503(self):
        mock_storage = MagicMock()
        mock_storage.upload_fileobj.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'Slow Down'}}, 'PutObject'
        )
        benchmark = SimpleUploadedFile('benchmark.tif', b'b', content_type='image/tiff')
        candidate = SimpleUploadedFile('candidate.tif', b'c', content_type='image/tiff')
        with patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            response = self.client.post(
                '/apps/fimeval-gui/api/upload/',
                {'benchmark': benchmark, 'candidates': [candidate]},
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn('error', json.loads(response.content))


class TestSubmitEndpoint(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.mock_s3 = mock_aws()
        self.mock_s3.start()
        boto3.client('s3', region_name='us-east-1').create_bucket(Bucket=BUCKET)

        self.app_patcher = patch('tethysapp.fimeval_gui.controllers.App')
        self.mock_app = self.app_patcher.start()
        self.mock_app.get_custom_setting.side_effect = _app_settings_side_effect

        # Mock job manager to avoid hitting real Tethys DaskJob infrastructure
        self.mock_job = MagicMock()
        self.mock_job.id = 99
        self.mock_app.get_job_manager.return_value.create_job.return_value = self.mock_job

        self.user = self.create_test_user(username='bob', password='pw', email='b@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def tearDown(self):
        self.app_patcher.stop()
        self.mock_s3.stop()
        super().tearDown()

    def _put_upload(self, upload_id):
        user_id = str(self.user.id)
        boto3.client('s3', region_name='us-east-1').put_object(
            Bucket=BUCKET,
            Key=f'uploads/{user_id}/{upload_id}/benchmark.tif',
            Body=b'b',
        )

    def test_submit_returns_job_id_and_status(self):
        self._put_upload('u1')
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u1', 'method': 'smallest_extent'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)
        body = json.loads(response.content)
        self.assertEqual(body['job_id'], 99)
        self.assertEqual(body['status'], 'submitted')

    def test_submit_calls_job_execute(self):
        self._put_upload('u2')
        self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u2', 'method': 'convex_hull'}),
            content_type='application/json',
        )
        self.mock_job.execute.assert_called_once()

    def test_submit_rejects_invalid_method(self):
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u3', 'method': 'not_a_method'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_accepts_bootstrap(self):
        self._put_upload('u_bs')
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u_bs', 'method': 'bootstrap'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)

    def test_submit_accepts_intersected_extent(self):
        self._put_upload('u_int')
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u_int', 'method': 'intersected_extent'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)

    def _put_boundary_shp(self, upload_id):
        user_id = str(self.user.id)
        boto3.client('s3', region_name='us-east-1').put_object(
            Bucket=BUCKET,
            Key=f'uploads/{user_id}/{upload_id}/boundary/aoi.shp',
            Body=b'shp',
        )

    def test_submit_accepts_aoi_with_shapefile(self):
        self._put_upload('u_aoi')
        self._put_boundary_shp('u_aoi')
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u_aoi', 'method': 'AOI'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)

    def test_submit_aoi_without_shapefile_returns_400(self):
        self._put_upload('u_aoi2')
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u_aoi2', 'method': 'AOI'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_rejects_missing_upload_id(self):
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'method': 'smallest_extent'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_returns_404_for_unknown_upload_id(self):
        response = self.client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'nonexistent', 'method': 'smallest_extent'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_submit_wrong_method_returns_405(self):
        response = self.client.get('/apps/fimeval-gui/api/jobs/')
        self.assertEqual(response.status_code, 405)

    def test_submit_requires_login(self):
        client = self.get_test_client()  # not logged in
        response = client.post(
            '/apps/fimeval-gui/api/jobs/',
            data=json.dumps({'upload_id': 'u1', 'method': 'smallest_extent'}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, [302, 403])


class TestStatusEndpoint(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_test_user(username='carol', password='pw', email='c@b.com')
        self.other = self.create_test_user(username='dave', password='pw', email='d@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def _make_job(self, user, key='some-future-key', extended_properties=None):
        from tethys_sdk.jobs import DaskJob
        mock_scheduler = MagicMock()
        mock_scheduler.host = 'tcp://localhost:8786'
        job = MagicMock(spec=DaskJob)
        job.id = 42
        job.key = key
        job._status = 'SUB'
        job.user = user
        job.creation_time = None
        job.completion_time = None
        job.scheduler = mock_scheduler
        job.extended_properties = extended_properties or {}
        return job

    def _get(self, job_id):
        return self.client.get(f'/apps/fimeval-gui/api/jobs/{job_id}/')

    def test_status_returns_queued_for_pending_without_props(self):
        # Dask 'pending' is ambiguous (queued OR executing). With no
        # extended_properties the marker check can't run, so the endpoint
        # reports the un-promoted state: queued.
        job = self._make_job(self.user)
        mock_future = MagicMock()
        mock_future.status = 'pending'
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers.Client') as MockClient, \
             patch('tethysapp.fimeval_gui.controllers.Future', return_value=mock_future):
            MockDJ.objects.get.return_value = job
            MockClient.return_value.__enter__ = lambda s: s
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            MockClient.return_value.close = MagicMock()
            response = self._get(42)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body['job_id'], 42)
        self.assertEqual(body['status'], 'queued')

    def test_status_returns_complete_when_dask_finished(self):
        job = self._make_job(self.user)
        mock_future = MagicMock()
        mock_future.status = 'finished'
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers.Client') as MockClient, \
             patch('tethysapp.fimeval_gui.controllers.Future', return_value=mock_future):
            MockDJ.objects.get.return_value = job
            MockClient.return_value.close = MagicMock()
            response = self._get(42)
        self.assertEqual(json.loads(response.content)['status'], 'complete')

    def test_status_falls_back_to_tethys_when_dask_unreachable(self):
        job = self._make_job(self.user)
        job._status = 'SUB'
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers.Client', side_effect=Exception('unreachable')):
            MockDJ.objects.get.return_value = job
            response = self._get(42)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['status'], 'submitted')

    def _status_with_keys(self, keys, props=None):
        job = self._make_job(self.user, extended_properties=props or {'upload_id': 'uid1', 'user_id': '1'})
        mock_future = MagicMock()
        mock_future.status = 'pending'  # ephemeral -> running -> marker fallback
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = keys
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers.Client') as MockClient, \
             patch('tethysapp.fimeval_gui.controllers.Future', return_value=mock_future), \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            MockClient.return_value.close = MagicMock()
            response = self._get(42)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)['status']

    def test_status_complete_with_success_marker(self):
        status = self._status_with_keys([
            'outputs/1/uid1/case_study/smallest_extent/EvaluationMetrics/EvaluationMetrics.csv',
            'outputs/1/uid1/_SUCCESS',
        ])
        self.assertEqual(status, 'complete')

    def test_status_error_with_failed_marker(self):
        self.assertEqual(self._status_with_keys(['outputs/1/uid1/_FAILED']), 'error')

    def test_status_running_when_outputs_but_no_marker(self):
        # Outputs present but the terminal marker hasn't landed yet — must NOT
        # report complete (this is the race that blanked Results).
        self.assertEqual(
            self._status_with_keys(['outputs/1/uid1/case_study/x/ContingencyMap.tif']),
            'running',
        )

    def test_status_returns_queued_when_no_outputs_in_s3(self):
        # Pending future + empty output prefix = waiting for a worker slot.
        self.assertEqual(self._status_with_keys([]), 'queued')

    def test_status_running_with_running_marker(self):
        self.assertEqual(
            self._status_with_keys(['outputs/1/uid1/_RUNNING']), 'running'
        )

    def test_status_complete_wins_over_running_marker(self):
        self.assertEqual(
            self._status_with_keys([
                'outputs/1/uid1/_RUNNING',
                'outputs/1/uid1/_SUCCESS',
            ]),
            'complete',
        )

    def test_status_returns_404_for_unknown_job(self):
        from tethys_sdk.jobs import DaskJob
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.side_effect = DaskJob.DoesNotExist
            response = self._get(999)
        self.assertEqual(response.status_code, 404)

    def test_status_returns_403_for_other_users_job(self):
        from tethys_sdk.jobs import DaskJob
        job = self._make_job(self.other)
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.return_value = job
            response = self._get(42)
        self.assertEqual(response.status_code, 403)

    def test_status_wrong_method_returns_405(self):
        response = self.client.post('/apps/fimeval-gui/api/jobs/42/')
        self.assertEqual(response.status_code, 405)

    def test_status_requires_login(self):
        client = self.get_test_client()
        response = client.get('/apps/fimeval-gui/api/jobs/42/')
        self.assertIn(response.status_code, [302, 403])


class TestOutputsEndpoint(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_test_user(username='eve', password='pw', email='e@b.com')
        self.other = self.create_test_user(username='oscar', password='pw', email='o@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def _make_job(self, upload_id='uid1', user_id='1', status='COM', user=None):
        from tethys_sdk.jobs import DaskJob
        job = MagicMock(spec=DaskJob)
        job.id = 55
        job._status = status
        job.user = user if user is not None else self.user
        job.extended_properties = {'upload_id': upload_id, 'user_id': user_id}
        return job

    def _get(self, job_id):
        return self.client.get(f'/apps/fimeval-gui/api/jobs/{job_id}/outputs/')

    def test_outputs_returns_file_list(self):
        job = self._make_job()
        key = 'outputs/1/uid1/case_study/smallest_extent/EvaluationMetrics.csv'
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = [key]
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(55)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body['job_id'], 55)
        self.assertEqual(len(body['files']), 1)
        self.assertEqual(body['files'][0]['key'], key)
        self.assertEqual(body['files'][0]['name'], 'EvaluationMetrics.csv')

    def test_outputs_excludes_terminal_markers(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = [
            'outputs/1/uid1/case_study/smallest_extent/EvaluationMetrics.csv',
            'outputs/1/uid1/_SUCCESS',
            'outputs/1/uid1/_RUNNING',
        ]
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(55)
        names = [f['name'] for f in json.loads(response.content)['files']]
        self.assertIn('EvaluationMetrics.csv', names)
        self.assertNotIn('_SUCCESS', names)
        self.assertNotIn('_RUNNING', names)

    def test_outputs_returns_files_even_if_status_not_com(self):
        # Dev job monitor doesn't tick (_status stays SUB/RUN); outputs presence
        # in MinIO is the authoritative completion signal.
        job = self._make_job(status='RUN')
        key = 'outputs/1/uid1/case_study/smallest_extent/EvaluationMetrics.csv'
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = [key]
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(55)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(json.loads(response.content)['files']), 1)

    def test_outputs_returns_403_for_other_users_job(self):
        from tethys_sdk.jobs import DaskJob
        job = self._make_job(user=self.other)
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.return_value = job
            response = self._get(55)
        self.assertEqual(response.status_code, 403)

    def test_outputs_returns_404_when_no_outputs_yet(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = []
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(55)
        self.assertEqual(response.status_code, 404)

    def test_outputs_returns_404_for_unknown_job(self):
        from tethys_sdk.jobs import DaskJob
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.side_effect = DaskJob.DoesNotExist
            response = self._get(999)
        self.assertEqual(response.status_code, 404)

    def test_outputs_returns_503_on_s3_error(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'down'}}, 'ListObjectsV2'
        )
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(55)
        self.assertEqual(response.status_code, 503)

    def test_outputs_wrong_method_returns_405(self):
        response = self.client.post('/apps/fimeval-gui/api/jobs/55/outputs/')
        self.assertEqual(response.status_code, 405)

    def test_outputs_requires_login(self):
        client = self.get_test_client()
        response = client.get('/apps/fimeval-gui/api/jobs/55/outputs/')
        self.assertIn(response.status_code, [302, 403])


class TestDownloadEndpoint(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_test_user(username='frank', password='pw', email='f@b.com')
        self.other = self.create_test_user(username='gina', password='pw', email='g@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def _make_job(self, upload_id='uid1', user_id='1', status='COM', user=None):
        from tethys_sdk.jobs import DaskJob
        job = MagicMock(spec=DaskJob)
        job.id = 77
        job._status = status
        job.user = user if user is not None else self.user
        job.extended_properties = {'upload_id': upload_id, 'user_id': user_id}
        return job

    VALID_KEY = 'outputs/1/uid1/case_study/smallest_extent/EvaluationMetrics.csv'

    def _get(self, job_id, file_key=None):
        url = f'/apps/fimeval-gui/api/jobs/{job_id}/download/'
        if file_key:
            url += f'?file={file_key}'
        return self.client.get(url)

    def test_download_redirects_to_presigned_url(self):
        job = self._make_job()
        presigned = 'http://minio:9000/bucket/key?X-Amz-Signature=abc'
        mock_storage = MagicMock()
        mock_storage.key_exists.return_value = True
        mock_storage.presigned_url.return_value = presigned
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(77, self.VALID_KEY)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response['Location'], presigned)

    def test_download_rejects_key_outside_prefix(self):
        job = self._make_job()
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.objects.get.return_value = job
            response = self._get(77, 'outputs/99/other-uid/secret.csv')
        self.assertEqual(response.status_code, 403)

    def test_download_missing_file_param_returns_400(self):
        job = self._make_job()
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.objects.get.return_value = job
            response = self._get(77)
        self.assertEqual(response.status_code, 400)

    def test_download_redirects_even_if_status_not_com(self):
        job = self._make_job(status='RUN')
        presigned = 'http://minio:9000/bucket/key?X-Amz-Signature=abc'
        mock_storage = MagicMock()
        mock_storage.key_exists.return_value = True
        mock_storage.presigned_url.return_value = presigned
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(77, self.VALID_KEY)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response['Location'], presigned)

    def test_download_returns_403_for_other_users_job(self):
        from tethys_sdk.jobs import DaskJob
        job = self._make_job(user=self.other)
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.return_value = job
            response = self._get(77, self.VALID_KEY)
        self.assertEqual(response.status_code, 403)

    def test_download_unknown_job_returns_404(self):
        from tethys_sdk.jobs import DaskJob
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.side_effect = DaskJob.DoesNotExist
            response = self._get(999, self.VALID_KEY)
        self.assertEqual(response.status_code, 404)

    def test_download_file_not_found_in_s3_returns_404(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.key_exists.return_value = False
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(77, self.VALID_KEY)
        self.assertEqual(response.status_code, 404)

    def test_download_s3_error_returns_503(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.key_exists.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'down'}}, 'HeadObject'
        )
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(77, self.VALID_KEY)
        self.assertEqual(response.status_code, 503)

    def test_download_wrong_method_returns_405(self):
        response = self.client.post(f'/apps/fimeval-gui/api/jobs/77/download/')
        self.assertEqual(response.status_code, 405)

    def test_download_requires_login(self):
        client = self.get_test_client()
        response = client.get(f'/apps/fimeval-gui/api/jobs/77/download/?file={self.VALID_KEY}')
        self.assertIn(response.status_code, [302, 403])


class TestCsrfEndpoint(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.get_test_client()

    def test_csrf_get_sets_cookie(self):
        response = self.client.get('/apps/fimeval-gui/api/csrf/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)

    def test_csrf_post_returns_405(self):
        response = self.client.post('/apps/fimeval-gui/api/csrf/')
        self.assertEqual(response.status_code, 405)


class TestMetricsEndpoint(TethysTestCase):
    CSV = (
        'Metrics,candidate_0\n'
        'CSI_values,0.3656507191183279\n'
        'TP_values,283142.0\n'
        'FAR_values,0.4182017683549446\n'
    )
    KEY = 'outputs/1/uid1/case_study/smallest_extent/EvaluationMetrics/EvaluationMetrics.csv'

    def setUp(self):
        super().setUp()
        self.user = self.create_test_user(username='heidi', password='pw', email='h@b.com')
        self.other = self.create_test_user(username='ivan', password='pw', email='i@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def _make_job(self, upload_id='uid1', user_id='1', user=None):
        from tethys_sdk.jobs import DaskJob
        job = MagicMock(spec=DaskJob)
        job.id = 88
        job.user = user if user is not None else self.user
        job.extended_properties = {'upload_id': upload_id, 'user_id': user_id}
        return job

    def _get(self, job_id):
        return self.client.get(f'/apps/fimeval-gui/api/jobs/{job_id}/metrics/')

    def test_metrics_parsed(self):
        import io as _io
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = [self.KEY]
        mock_storage.get_object.return_value = {'Body': _io.BytesIO(self.CSV.encode('utf-8'))}
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(88)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body['candidates'], ['candidate_0'])
        csi = next(m for m in body['metrics'] if m['metric'] == 'CSI')
        self.assertAlmostEqual(csi['values']['candidate_0'], 0.3656507191183279)
        tp = next(m for m in body['metrics'] if m['metric'] == 'TP')
        self.assertEqual(tp['values']['candidate_0'], 283142.0)

    def test_metrics_404_when_csv_absent(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = [
            'outputs/1/uid1/case_study/smallest_extent/ContingencyMaps/x.tif'
        ]
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(88)
        self.assertEqual(response.status_code, 404)

    def test_metrics_403_for_other_users_job(self):
        from tethys_sdk.jobs import DaskJob
        job = self._make_job(user=self.other)
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.return_value = job
            response = self._get(88)
        self.assertEqual(response.status_code, 403)

    def test_metrics_wrong_method_returns_405(self):
        response = self.client.post('/apps/fimeval-gui/api/jobs/88/metrics/')
        self.assertEqual(response.status_code, 405)

    def test_metrics_requires_login(self):
        client = self.get_test_client()
        response = client.get('/apps/fimeval-gui/api/jobs/88/metrics/')
        self.assertIn(response.status_code, [302, 403])

    def test_metrics_404_for_unknown_job(self):
        from tethys_sdk.jobs import DaskJob
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.side_effect = DaskJob.DoesNotExist
            response = self._get(999)
        self.assertEqual(response.status_code, 404)

    def test_metrics_404_when_no_extended_properties(self):
        job = self._make_job()
        job.extended_properties = {}
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.objects.get.return_value = job
            response = self._get(88)
        self.assertEqual(response.status_code, 404)

    def test_metrics_503_on_s3_error(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'down'}}, 'ListObjectsV2'
        )
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(88)
        self.assertEqual(response.status_code, 503)


class TestDownloadAllEndpoint(TethysTestCase):
    PREFIX = 'outputs/1/uid1/'
    KEYS = [
        'outputs/1/uid1/case_study/bootstrap/EvaluationMetrics/EvaluationMetrics.csv',
        'outputs/1/uid1/case_study/bootstrap/Random_Sampling/random_candidate_0.csv',
        'outputs/1/uid1/case_study/bootstrap/ContingencyMaps/ContingencyMAP_candidate_0.tif',
    ]

    def setUp(self):
        super().setUp()
        self.user = self.create_test_user(username='judy', password='pw', email='j@b.com')
        self.other = self.create_test_user(username='karl', password='pw', email='k@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def _make_job(self, upload_id='uid1', user_id='1', method='bootstrap', user=None):
        from tethys_sdk.jobs import DaskJob
        job = MagicMock(spec=DaskJob)
        job.id = 91
        job.user = user if user is not None else self.user
        job.extended_properties = {
            'upload_id': upload_id, 'user_id': user_id, 'method': method,
        }
        return job

    def _storage(self):
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = list(self.KEYS)
        mock_storage.get_object.side_effect = lambda key: {
            'Body': io.BytesIO(b'data:' + key.encode('utf-8'))
        }
        return mock_storage

    def _get(self, job_id):
        return self.client.get(f'/apps/fimeval-gui/api/jobs/{job_id}/download-all/')

    def test_returns_zip_of_all_outputs(self):
        job = self._make_job()
        mock_storage = self._storage()
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(91)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('fimeval_results_bootstrap_91.zip', response['Content-Disposition'])
        zf = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
        self.assertEqual(
            sorted(zf.namelist()),
            sorted(k[len(self.PREFIX):] for k in self.KEYS),
        )
        first = self.KEYS[0][len(self.PREFIX):]
        self.assertEqual(zf.read(first), b'data:' + self.KEYS[0].encode('utf-8'))

    def test_download_all_excludes_markers(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = self.KEYS + [
            'outputs/1/uid1/_SUCCESS',
            'outputs/1/uid1/_RUNNING',
        ]
        mock_storage.get_object.side_effect = lambda key: {'Body': io.BytesIO(b'x')}
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(91)
        zf = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
        self.assertNotIn('_SUCCESS', zf.namelist())
        self.assertNotIn('_RUNNING', zf.namelist())

    def test_404_when_no_outputs(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = []
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(91)
        self.assertEqual(response.status_code, 404)

    def test_403_for_other_users_job(self):
        from tethys_sdk.jobs import DaskJob
        job = self._make_job(user=self.other)
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.return_value = job
            response = self._get(91)
        self.assertEqual(response.status_code, 403)

    def test_405_on_non_get(self):
        response = self.client.post('/apps/fimeval-gui/api/jobs/91/download-all/')
        self.assertEqual(response.status_code, 405)

    def test_requires_login(self):
        client = self.get_test_client()
        response = client.get('/apps/fimeval-gui/api/jobs/91/download-all/')
        self.assertIn(response.status_code, [302, 403])

    def test_503_on_s3_error(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'down'}}, 'ListObjectsV2'
        )
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(91)
        self.assertEqual(response.status_code, 503)


class TestBootstrapEndpoint(TethysTestCase):
    CSV = (
        'CSI,POD,FAR,F1,MCC,Kappa,Accuracy,iteration\n'
        '0.1,0.5,0.4,0.5,0.4,0.4,0.9,1\n'
        '0.2,0.5,0.4,0.5,0.4,0.4,0.9,2\n'
        '0.3,0.5,0.4,0.5,0.4,0.4,0.9,3\n'
        '0.4,0.5,0.4,0.5,0.4,0.4,0.9,4\n'
        '0.5,0.5,0.4,0.5,0.4,0.4,0.9,5\n'
    )
    KEY = 'outputs/1/uid1/case_study/bootstrap/Random_Sampling/random_candidate_0.csv'
    OTHER_KEY = 'outputs/1/uid1/case_study/bootstrap/EvaluationMetrics/EvaluationMetrics.csv'

    def setUp(self):
        super().setUp()
        self.user = self.create_test_user(username='laura', password='pw', email='l@b.com')
        self.other = self.create_test_user(username='mike', password='pw', email='m@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def _make_job(self, upload_id='uid1', user_id='1', user=None):
        from tethys_sdk.jobs import DaskJob
        job = MagicMock(spec=DaskJob)
        job.id = 92
        job.user = user if user is not None else self.user
        job.extended_properties = {'upload_id': upload_id, 'user_id': user_id, 'method': 'bootstrap'}
        return job

    def _storage(self, csv_text=None, keys=None):
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = keys if keys is not None else [self.OTHER_KEY, self.KEY]
        mock_storage.get_object.side_effect = lambda key: {
            'Body': io.BytesIO((csv_text if csv_text is not None else self.CSV).encode('utf-8'))
        }
        return mock_storage

    def _get(self, job_id):
        return self.client.get(f'/apps/fimeval-gui/api/jobs/{job_id}/bootstrap/')

    def test_returns_box_stats(self):
        job = self._make_job()
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=self._storage()):
            MockDJ.objects.get.return_value = job
            response = self._get(92)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body['candidates'], ['candidate_0'])
        self.assertEqual(body['metrics'], ['CSI', 'POD', 'FAR', 'F1', 'MCC', 'Kappa', 'Accuracy'])
        csi = body['stats']['candidate_0']['CSI']
        self.assertAlmostEqual(csi['median'], 0.3)
        self.assertAlmostEqual(csi['q1'], 0.2)
        self.assertAlmostEqual(csi['q3'], 0.4)
        self.assertAlmostEqual(csi['min'], 0.1)
        self.assertAlmostEqual(csi['max'], 0.5)
        self.assertEqual(csi['outliers'], [])
        self.assertEqual(csi['n'], 5)

    def test_detects_outliers(self):
        csv_text = (
            'CSI,POD,FAR,F1,MCC,Kappa,Accuracy,iteration\n'
            '0.1,0.5,0.4,0.5,0.4,0.4,0.9,1\n'
            '0.2,0.5,0.4,0.5,0.4,0.4,0.9,2\n'
            '0.3,0.5,0.4,0.5,0.4,0.4,0.9,3\n'
            '0.4,0.5,0.4,0.5,0.4,0.4,0.9,4\n'
            '5.0,0.5,0.4,0.5,0.4,0.4,0.9,5\n'
        )
        job = self._make_job()
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=self._storage(csv_text=csv_text)):
            MockDJ.objects.get.return_value = job
            response = self._get(92)
        csi = json.loads(response.content)['stats']['candidate_0']['CSI']
        self.assertIn(5.0, csi['outliers'])
        self.assertAlmostEqual(csi['max'], 0.4)

    def test_404_when_no_random_sampling(self):
        job = self._make_job()
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=self._storage(keys=[self.OTHER_KEY])):
            MockDJ.objects.get.return_value = job
            response = self._get(92)
        self.assertEqual(response.status_code, 404)

    def test_403_for_other_users_job(self):
        from tethys_sdk.jobs import DaskJob
        job = self._make_job(user=self.other)
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.return_value = job
            response = self._get(92)
        self.assertEqual(response.status_code, 403)

    def test_405_on_non_get(self):
        response = self.client.post('/apps/fimeval-gui/api/jobs/92/bootstrap/')
        self.assertEqual(response.status_code, 405)

    def test_requires_login(self):
        client = self.get_test_client()
        response = client.get('/apps/fimeval-gui/api/jobs/92/bootstrap/')
        self.assertIn(response.status_code, [302, 403])

    def test_503_on_s3_error(self):
        job = self._make_job()
        mock_storage = MagicMock()
        mock_storage.list_prefix.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'down'}}, 'ListObjectsV2'
        )
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            response = self._get(92)
        self.assertEqual(response.status_code, 503)
