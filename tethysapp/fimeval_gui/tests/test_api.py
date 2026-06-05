import json
import os
import uuid
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
            data=json.dumps({'upload_id': 'u3', 'method': 'bootstrap'}),
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
        job.scheduler = mock_scheduler
        job.extended_properties = extended_properties or {}
        return job

    def _get(self, job_id):
        return self.client.get(f'/apps/fimeval-gui/api/jobs/{job_id}/')

    def test_status_returns_200_with_dask_running(self):
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
        self.assertEqual(body['status'], 'running')

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

    def test_status_returns_complete_when_outputs_exist_in_s3(self):
        props = {'upload_id': 'uid1', 'user_id': '1'}
        job = self._make_job(self.user, extended_properties=props)
        mock_future = MagicMock()
        mock_future.status = 'pending'
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = ['outputs/1/uid1/result.csv']
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers.Client') as MockClient, \
             patch('tethysapp.fimeval_gui.controllers.Future', return_value=mock_future), \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            MockClient.return_value.close = MagicMock()
            response = self._get(42)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['status'], 'complete')

    def test_status_returns_running_when_no_outputs_in_s3(self):
        props = {'upload_id': 'uid2', 'user_id': '1'}
        job = self._make_job(self.user, extended_properties=props)
        mock_future = MagicMock()
        mock_future.status = 'pending'
        mock_storage = MagicMock()
        mock_storage.list_prefix.return_value = []
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ, \
             patch('tethysapp.fimeval_gui.controllers.Client') as MockClient, \
             patch('tethysapp.fimeval_gui.controllers.Future', return_value=mock_future), \
             patch('tethysapp.fimeval_gui.controllers._get_storage', return_value=mock_storage):
            MockDJ.objects.get.return_value = job
            MockClient.return_value.close = MagicMock()
            response = self._get(42)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['status'], 'running')

    def test_status_returns_404_for_unknown_job(self):
        from tethys_sdk.jobs import DaskJob
        with patch('tethysapp.fimeval_gui.controllers.DaskJob') as MockDJ:
            MockDJ.DoesNotExist = DaskJob.DoesNotExist
            MockDJ.objects.get.side_effect = DaskJob.DoesNotExist
            response = self._get(999)
        self.assertEqual(response.status_code, 404)

    def test_status_wrong_method_returns_405(self):
        response = self.client.post('/apps/fimeval-gui/api/jobs/42/')
        self.assertEqual(response.status_code, 405)

    def test_status_requires_login(self):
        client = self.get_test_client()
        response = client.get('/apps/fimeval-gui/api/jobs/42/')
        self.assertIn(response.status_code, [302, 403])
