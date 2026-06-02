import io
import os
import tempfile
import unittest

import boto3
from moto import mock_aws

os.environ.setdefault('AWS_ACCESS_KEY_ID', 'test')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'test')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')

BUCKET = 'fimeval-test'


def _make_storage():
    from tethysapp.fimeval_gui.storage import S3Storage
    return S3Storage(endpoint_url=None, access_key='test', secret_key='test', bucket=BUCKET)


def _make_bucket():
    boto3.client('s3', region_name='us-east-1').create_bucket(Bucket=BUCKET)


class TestUpload(unittest.TestCase):
    @mock_aws
    def test_upload_bytes_returns_key(self):
        _make_bucket()
        storage = _make_storage()
        key = storage.upload_bytes(b'fake tiff', 'uploads/1/abc/benchmark.tif')
        self.assertEqual(key, 'uploads/1/abc/benchmark.tif')

    @mock_aws
    def test_upload_bytes_stores_data(self):
        _make_bucket()
        storage = _make_storage()
        storage.upload_bytes(b'fake tiff', 'uploads/1/abc/benchmark.tif')
        obj = boto3.client('s3', region_name='us-east-1').get_object(
            Bucket=BUCKET, Key='uploads/1/abc/benchmark.tif'
        )
        self.assertEqual(obj['Body'].read(), b'fake tiff')

    @mock_aws
    def test_upload_fileobj(self):
        _make_bucket()
        storage = _make_storage()
        key = storage.upload_fileobj(io.BytesIO(b'tiff data'), 'uploads/1/abc/candidate_0.tif')
        self.assertEqual(key, 'uploads/1/abc/candidate_0.tif')
        obj = boto3.client('s3', region_name='us-east-1').get_object(
            Bucket=BUCKET, Key='uploads/1/abc/candidate_0.tif'
        )
        self.assertEqual(obj['Body'].read(), b'tiff data')


class TestList(unittest.TestCase):
    @mock_aws
    def test_list_prefix_returns_matching_keys(self):
        _make_bucket()
        storage = _make_storage()
        storage.upload_bytes(b'a', 'uploads/1/abc/benchmark.tif')
        storage.upload_bytes(b'b', 'uploads/1/abc/candidate_0.tif')
        storage.upload_bytes(b'c', 'uploads/2/xyz/benchmark.tif')

        keys = storage.list_prefix('uploads/1/abc/')
        self.assertCountEqual(keys, [
            'uploads/1/abc/benchmark.tif',
            'uploads/1/abc/candidate_0.tif',
        ])

    @mock_aws
    def test_list_prefix_empty(self):
        _make_bucket()
        self.assertEqual(_make_storage().list_prefix('uploads/99/nope/'), [])


class TestKeyExists(unittest.TestCase):
    @mock_aws
    def test_existing_key_returns_true(self):
        _make_bucket()
        storage = _make_storage()
        storage.upload_bytes(b'data', 'uploads/1/abc/benchmark.tif')
        self.assertTrue(storage.key_exists('uploads/1/abc/benchmark.tif'))

    @mock_aws
    def test_missing_key_returns_false(self):
        _make_bucket()
        self.assertFalse(_make_storage().key_exists('uploads/1/abc/nope.tif'))


class TestDownload(unittest.TestCase):
    @mock_aws
    def test_download_to_path(self):
        _make_bucket()
        storage = _make_storage()
        storage.upload_bytes(b'hello', 'uploads/1/abc/benchmark.tif')

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, 'benchmark.tif')
            storage.download_to_path('uploads/1/abc/benchmark.tif', dest)
            with open(dest, 'rb') as f:
                self.assertEqual(f.read(), b'hello')


class TestPresignedUrl(unittest.TestCase):
    @mock_aws
    def test_presigned_url_is_string_containing_key(self):
        _make_bucket()
        storage = _make_storage()
        storage.upload_bytes(b'data', 'outputs/1/abc/EvaluationMetrics.csv')
        url = storage.presigned_url('outputs/1/abc/EvaluationMetrics.csv')
        self.assertIsInstance(url, str)
        self.assertIn('EvaluationMetrics.csv', url)
