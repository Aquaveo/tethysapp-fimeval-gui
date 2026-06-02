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
            Bucket=BUCKET, Key=f'fimeval/uploads/{user_id}/{upload_id}/benchmark.tif'
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
            Bucket=BUCKET, Key=f'fimeval/uploads/{user_id}/{upload_id}/candidate_0.tif'
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
                Bucket=BUCKET, Key=f'fimeval/uploads/{user_id}/{upload_id}/candidate_{i}.tif'
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
