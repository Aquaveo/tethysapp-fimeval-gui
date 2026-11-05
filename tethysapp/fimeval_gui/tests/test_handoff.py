"""FIMEVAL-BE52: the "Run in FIMeval" handoff from FIMbench.

FIMbench opens ``/handoff/fimeval-gui/run-evaluation/?benchmark_url=…&benchmark_name=…``.
Tethys routes that to our ``run-evaluation`` handoff handler, which copies the
benchmark from the (public) SDML bucket into our own object store under a fresh
``upload_id`` and redirects into the SPA. Storage is moto; the download is faked.
"""
import io
import json
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws
from tethys_sdk.testing import TethysTestCase

from tethysapp.fimeval_gui.tests.test_api import BUCKET, _app_settings_side_effect

HANDOFF_URL = '/handoff/fimeval-gui/run-evaluation/'
SDML = 'https://sdmlab.s3.amazonaws.com/FIMbench/site_42/benchmark_BM.tif'
TIFF = b'II*\x00' + b'\x00' * 60  # little-endian TIFF magic + padding


def _fake_response(body=TIFF, status=200, content_length=None):
    r = MagicMock()
    r.status_code = status
    r.headers = {'Content-Length': str(len(body) if content_length is None else content_length)}
    r.iter_content = lambda chunk_size=1 << 16: iter([body[i:i + chunk_size] for i in range(0, len(body), chunk_size)])
    r.raise_for_status = MagicMock()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


class TestRunEvaluationHandoff(TethysTestCase):
    def setUp(self):
        super().setUp()
        self.mock_s3 = mock_aws()
        self.mock_s3.start()
        self.s3 = boto3.client('s3', region_name='us-east-1')
        self.s3.create_bucket(Bucket=BUCKET)
        self.app_patcher = patch('tethysapp.fimeval_gui.controllers.App')
        self.mock_app = self.app_patcher.start()
        self.mock_app.get_custom_setting.side_effect = lambda n: (
            None if n == 'handoff_allowed_hosts' else _app_settings_side_effect(n))
        # handoff.py reads the allow-list setting through its own App import.
        self.handoff_app_patcher = patch('tethysapp.fimeval_gui.handoff.App', self.mock_app)
        self.handoff_app_patcher.start()
        self.user = self.create_test_user(username='bench', password='pw', email='b@b.com')
        self.client = self.get_test_client()
        self.client.force_login(self.user)

    def tearDown(self):
        self.handoff_app_patcher.stop()
        self.app_patcher.stop()
        self.mock_s3.stop()
        super().tearDown()

    def _keys(self):
        resp = self.s3.list_objects_v2(Bucket=BUCKET)
        return sorted(o['Key'] for o in resp.get('Contents', []))

    def test_handler_is_registered(self):
        from tethysapp.fimeval_gui.app import App
        names = [h.name for h in App().handoff_handlers()]
        self.assertIn('run-evaluation', names)

    def test_anonymous_is_sent_to_login(self):
        c = self.get_test_client()
        r = c.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r['Location'])

    def test_stages_benchmark_and_redirects_into_spa(self):
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=_fake_response()) as get:
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML, 'benchmark_name': '2048397'})
        self.assertEqual(r.status_code, 302)
        loc = r['Location']
        self.assertTrue(loc.startswith('/apps/fimeval-gui/'), loc)
        self.assertIn('from=fimbench', loc)
        self.assertIn('upload_id=', loc)
        self.assertIn('benchmark_name=benchmark_BM.tif', loc)
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], SDML)
        upload_id = loc.split('upload_id=')[1].split('&')[0]
        prefix = f'uploads/{self.user.id}/{upload_id}/'
        self.assertEqual(self._keys(), [prefix + 'benchmark.tif', prefix + 'manifest.json'])
        body = self.s3.get_object(Bucket=BUCKET, Key=prefix + 'benchmark.tif')['Body'].read()
        self.assertEqual(body, TIFF)
        manifest = json.loads(self.s3.get_object(Bucket=BUCKET, Key=prefix + 'manifest.json')['Body'].read())
        # Named from the .tif in the URL, never from FIMbench's site ID, so the
        # BE37 "BM" check sees the real *_BM.tif name.
        self.assertEqual(manifest['names']['benchmark.tif'], 'benchmark_BM.tif')
        self.assertEqual(manifest['source'], 'fimbench')

    def test_name_defaults_to_source_filename(self):
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=_fake_response()):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        upload_id = r['Location'].split('upload_id=')[1].split('&')[0]
        key = f'uploads/{self.user.id}/{upload_id}/manifest.json'
        manifest = json.loads(self.s3.get_object(Bucket=BUCKET, Key=key)['Body'].read())
        self.assertEqual(manifest['names']['benchmark.tif'], 'benchmark_BM.tif')

    def test_name_is_url_decoded(self):
        url = 'https://sdmlab.s3.amazonaws.com/FIM_Database/Tier_1/My%20Site/My%20Site_BM.tif'
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=_fake_response()):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': url, 'benchmark_name': 'My Site'})
        upload_id = r['Location'].split('upload_id=')[1].split('&')[0]
        key = f'uploads/{self.user.id}/{upload_id}/manifest.json'
        manifest = json.loads(self.s3.get_object(Bucket=BUCKET, Key=key)['Body'].read())
        self.assertEqual(manifest['names']['benchmark.tif'], 'My Site_BM.tif')

    def test_rejects_host_outside_allow_list(self):
        with patch('tethysapp.fimeval_gui.handoff.requests.get') as get:
            r = self.client.get(HANDOFF_URL, {'benchmark_url': 'https://evil.example.com/x.tif'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('from=fimbench', r['Location'])
        self.assertIn('error=not_allowed_host', r['Location'])
        self.assertNotIn('upload_id=', r['Location'])
        get.assert_not_called()
        self.assertEqual(self._keys(), [])

    def test_allow_list_setting_overrides_default(self):
        self.mock_app.get_custom_setting.side_effect = lambda n: (
            'mirror.example.org, other.example.org' if n == 'handoff_allowed_hosts'
            else _app_settings_side_effect(n))
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=_fake_response()):
            ok = self.client.get(HANDOFF_URL, {'benchmark_url': 'https://mirror.example.org/a_BM.tif'})
            no = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertIn('upload_id=', ok['Location'])
        self.assertIn('error=not_allowed_host', no['Location'])

    def test_rejects_non_tif_key(self):
        with patch('tethysapp.fimeval_gui.handoff.requests.get') as get:
            r = self.client.get(HANDOFF_URL, {'benchmark_url': 'https://sdmlab.s3.amazonaws.com/x/notes.txt'})
        self.assertIn('error=bad_url', r['Location'])
        get.assert_not_called()

    def test_rejects_oversized_by_content_length(self):
        big = _fake_response(content_length=3 * 1024 ** 3)
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=big):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertIn('error=too_large', r['Location'])
        self.assertEqual(self._keys(), [])

    def test_rejects_oversized_while_streaming(self):
        # No/false Content-Length: the byte count still stops at the cap.
        body = b'II*\x00' + b'\x00' * 200
        resp = _fake_response(body=body)
        resp.headers = {}
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=resp), \
                patch('tethysapp.fimeval_gui.handoff.MAX_UPLOAD_BYTES', 100):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertIn('error=too_large', r['Location'])
        self.assertEqual(self._keys(), [])

    def test_rejects_body_that_is_not_a_tiff(self):
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=_fake_response(body=b'<html>nope</html>')):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertIn('error=not_a_tiff', r['Location'])
        self.assertEqual(self._keys(), [])

    def test_unreachable_source_redirects_with_error(self):
        import requests
        with patch('tethysapp.fimeval_gui.handoff.requests.get', side_effect=requests.ConnectionError('down')):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertEqual(r.status_code, 302)
        self.assertIn('error=unreachable', r['Location'])

    def test_http_error_from_source_redirects_with_error(self):
        import requests
        resp = _fake_response(status=404)
        resp.raise_for_status.side_effect = requests.HTTPError('404')
        with patch('tethysapp.fimeval_gui.handoff.requests.get', return_value=resp):
            r = self.client.get(HANDOFF_URL, {'benchmark_url': SDML})
        self.assertIn('error=unreachable', r['Location'])

    def test_missing_benchmark_url_is_bad_request(self):
        r = self.client.get(HANDOFF_URL)
        self.assertEqual(r.status_code, 400)
