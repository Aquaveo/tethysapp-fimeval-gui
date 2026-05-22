# FIMeval GUI — Backend Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MinIO/S3 upload, async job execution (Tethys DaskJob), and REST API for the FIMeval MVP — `EvaluateFIM` with `smallest_extent` / `convex_hull`, single case study, no frontend.

**Architecture:** Five REST endpoints under `/apps/fimeval-gui/api/` cover the full job lifecycle (upload inputs → submit job → poll status → list outputs → download file). Inputs and outputs live in MinIO (dev) / S3 (prod) under `fimeval/uploads/<user_id>/<upload_id>/` and `fimeval/outputs/<user_id>/<upload_id>/`. Jobs run on a local Dask cluster via Tethys `DaskJob`, which persists state in Django's DB. A pluggable `JobType` registry means adding future FIMeval modules (v2–v7 in the roadmap) does not touch the submit/poll/download plumbing.

**Tech Stack:** Tethys 4 / Django, `dask[distributed]`, `boto3`, `moto` (tests), `fimeval`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `install.yml` | Modify | Add `boto3`, `moto`, `dask-distributed` to pip deps |
| `tethysapp/fimeval_gui/app.py` | Modify | Add four S3 `CustomSetting`s + one `SchedulerSetting` for Dask |
| `tethysapp/fimeval_gui/storage.py` | Create | `S3Storage`: `upload_fileobj`, `upload_bytes`, `list_prefix`, `key_exists`, `download_to_path`, `presigned_url` |
| `tethysapp/fimeval_gui/job_types/__init__.py` | Create | Exports `REGISTRY` dict |
| `tethysapp/fimeval_gui/job_types/registry.py` | Create | `JobType` abstract base class |
| `tethysapp/fimeval_gui/job_types/evaluate_fim.py` | Create | `run_evaluate_fim_task` (Dask worker fn) + `EvaluateFIMJobType` |
| `tethysapp/fimeval_gui/controllers.py` | Modify | Add five API endpoint controllers; `home` unchanged |
| `tethysapp/fimeval_gui/tests/test_storage.py` | Create | `S3Storage` unit tests (moto) |
| `tethysapp/fimeval_gui/tests/test_job_types.py` | Create | Job type unit tests (mock `fimeval` + moto) |
| `tethysapp/fimeval_gui/tests/test_api.py` | Create | API endpoint integration tests (moto + mocked DaskJob) |

### S3 Key Convention

```
fimeval/
  uploads/<user_id>/<upload_id>/
    benchmark.tif        ← always this name (FIMeval requires "benchmark" in filename)
    candidate_0.tif
    candidate_1.tif      ← enumerated if multiple candidates uploaded
  outputs/<user_id>/<upload_id>/
    EvaluationMetrics.csv
    <anything else FIMeval writes to its output_dir>
```

---

## Task 0: Dev Infrastructure — MinIO + Local Dask

No code, no tests. Get both services running and wired into Tethys before writing any app code. Complete this task before Task 1.

- [ ] **Step 1: Start MinIO via Docker**

  ```bash
  docker run -d --name minio \
    -p 9000:9000 -p 9001:9001 \
    -e MINIO_ROOT_USER=minioadmin \
    -e MINIO_ROOT_PASSWORD=minioadmin \
    quay.io/minio/minio server /data --console-address ":9001"
  ```

  Open `http://127.0.0.1:9001`, log in (`minioadmin` / `minioadmin`), create a bucket named **`fimeval`**.

- [ ] **Step 2: Start a local Dask cluster (keep these terminals open)**

  Terminal A:
  ```bash
  conda activate tethys
  dask scheduler
  ```
  Expected output includes: `Scheduler at: tcp://127.0.0.1:8786`

  Terminal B:
  ```bash
  conda activate tethys
  dask worker tcp://127.0.0.1:8786
  ```
  Expected output includes: `Registered to: tcp://127.0.0.1:8786`

- [ ] **Step 3: Register the Dask scheduler in Tethys admin**

  Visit `http://127.0.0.1:8000/admin/` → **Tethys Compute → Dask Schedulers → Add Dask Scheduler**
  - Name: `local`
  - Scheduler Endpoint: `tcp://127.0.0.1:8786`
  - Save.

  *(Return here after Task 1 to fill in the S3 settings for the app.)*

---

## Task 1: Add Custom Settings to `app.py`

**Files:**
- Modify: `tethysapp/fimeval_gui/app.py`
- Modify: `install.yml`

- [ ] **Step 1: Add pip dependencies to `install.yml`**

  Replace the empty `pip:` block with:

  ```yaml
    pip:
      - boto3
      - "moto[s3]"
      - "dask[distributed]"
  ```

- [ ] **Step 2: Update `app.py` with S3 and scheduler settings**

  Replace the full contents of `tethysapp/fimeval_gui/app.py`:

  ```python
  from tethys_sdk.base import TethysAppBase
  from tethys_sdk.app_settings import CustomSetting, SchedulerSetting


  class App(TethysAppBase):
      """FIMeval GUI Tethys App."""

      name = 'FIMeval GUI'
      package = 'fimeval_gui'
      root_url = 'fimeval-gui'
      index = 'home'
      catch_all = 'home'

      description = 'Webapp GUI for the FIMeval flood inundation map evaluation framework'
      color = '#007bff'
      tags = 'FIM, Flood Mapping, Flood Inundation Mapping, Hydrology, Evaluation, GIS'
      enable_feedback = False
      feedback_emails = []

      custom_settings = (
          CustomSetting(
              name='minio_endpoint_url',
              type=CustomSetting.TYPE_STRING,
              description='MinIO/S3 endpoint URL (e.g. http://127.0.0.1:9000). Leave blank for real AWS.',
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
      )

      scheduler_settings = (
          SchedulerSetting(
              name='dask_primary',
              description='Primary Dask scheduler for async FIMeval jobs',
              scheduler_service='dask',
              required=True,
          ),
      )
  ```

- [ ] **Step 3: Reinstall the app so Tethys picks up the new settings**

  ```bash
  tethys install -d
  ```
  Expected: completes without errors.

- [ ] **Step 4: Configure settings in Tethys admin**

  Visit `http://127.0.0.1:8000/admin/` → **Tethys Apps → FIMeval GUI → Edit**. Fill in:
  - `minio_endpoint_url`: `http://127.0.0.1:9000`
  - `minio_access_key`: `minioadmin`
  - `minio_secret_key`: `minioadmin`
  - `s3_bucket`: `fimeval`

  Also link the Dask scheduler: on the same form, set **Dask Primary Scheduler** to `local`.

- [ ] **Step 5: Commit**

  ```bash
  git add .
  git commit -m "feat: add S3 and Dask scheduler settings to app.py"
  ```

---

## Task 2: Storage Layer

**Files:**
- Create: `tethysapp/fimeval_gui/storage.py`
- Create: `tethysapp/fimeval_gui/tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

  Create `tethysapp/fimeval_gui/tests/test_storage.py`:

  ```python
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
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_storage.py -v 2
  ```
  Expected: `ImportError: cannot import name 'S3Storage'`

- [ ] **Step 3: Implement `storage.py`**

  Create `tethysapp/fimeval_gui/storage.py`:

  ```python
  import io

  import boto3
  from botocore.exceptions import ClientError


  class S3Storage:
      def __init__(self, endpoint_url, access_key, secret_key, bucket):
          self._bucket = bucket
          self._client = boto3.client(
              's3',
              endpoint_url=endpoint_url or None,
              aws_access_key_id=access_key,
              aws_secret_access_key=secret_key,
          )

      def upload_bytes(self, data: bytes, key: str) -> str:
          self._client.upload_fileobj(io.BytesIO(data), self._bucket, key)
          return key

      def upload_fileobj(self, fileobj, key: str) -> str:
          self._client.upload_fileobj(fileobj, self._bucket, key)
          return key

      def list_prefix(self, prefix: str) -> list[str]:
          paginator = self._client.get_paginator('list_objects_v2')
          keys = []
          for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
              for obj in page.get('Contents', []):
                  keys.append(obj['Key'])
          return keys

      def key_exists(self, key: str) -> bool:
          try:
              self._client.head_object(Bucket=self._bucket, Key=key)
              return True
          except ClientError as e:
              if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
                  return False
              raise

      def download_to_path(self, key: str, dest_path: str) -> None:
          self._client.download_file(self._bucket, key, dest_path)

      def presigned_url(self, key: str, expiry_seconds: int = 3600) -> str:
          return self._client.generate_presigned_url(
              'get_object',
              Params={'Bucket': self._bucket, 'Key': key},
              ExpiresIn=expiry_seconds,
          )
  ```

- [ ] **Step 4: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_storage.py -v 2
  ```
  Expected: 9 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add .
  git commit -m "feat: add S3Storage with moto tests"
  ```

---

## Task 3: Job Type Registry + EvaluateFIM Job Type

**Files:**
- Create: `tethysapp/fimeval_gui/job_types/__init__.py`
- Create: `tethysapp/fimeval_gui/job_types/registry.py`
- Create: `tethysapp/fimeval_gui/job_types/evaluate_fim.py`
- Create: `tethysapp/fimeval_gui/tests/test_job_types.py`

- [ ] **Step 1: Write the failing tests**

  Create `tethysapp/fimeval_gui/tests/test_job_types.py`:

  ```python
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
          from dask import delayed as dask_delayed
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
                        Key='fimeval/uploads/1/abc/benchmark.tif', Body=b'bench')
          s3.put_object(Bucket=BUCKET,
                        Key='fimeval/uploads/1/abc/candidate_0.tif', Body=b'cand')

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
                  Bucket=BUCKET, Prefix='fimeval/outputs/1/abc/'
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
          s3.put_object(Bucket=BUCKET, Key='fimeval/uploads/1/abc/benchmark.tif', Body=b'b')
          s3.put_object(Bucket=BUCKET, Key='fimeval/uploads/1/abc/candidate_0.tif', Body=b'c')

          def fake_eval(main_dir, method, output_dir, **kwargs):
              os.makedirs(output_dir, exist_ok=True)

          mock_eval.side_effect = fake_eval

          from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
          run_evaluate_fim_task('abc', '1', 'convex_hull', S3_CONFIG)

          self.assertEqual(mock_eval.call_args.args[1], 'convex_hull')

      @mock_aws
      @patch('fimeval.EvaluateFIM')
      def test_benchmark_file_placed_in_case_study_dir(self, mock_eval):
          """FIMeval must receive a main_dir that contains a subdir with a file
          named 'benchmark.tif' so it can identify the benchmark raster."""
          s3 = boto3.client('s3', region_name='us-east-1')
          s3.create_bucket(Bucket=BUCKET)
          s3.put_object(Bucket=BUCKET, Key='fimeval/uploads/1/abc/benchmark.tif', Body=b'b')
          s3.put_object(Bucket=BUCKET, Key='fimeval/uploads/1/abc/candidate_0.tif', Body=b'c')

          captured = {}

          def fake_eval(main_dir, method, output_dir, **kwargs):
              os.makedirs(output_dir, exist_ok=True)
              captured['main_dir'] = main_dir

          mock_eval.side_effect = fake_eval

          from tethysapp.fimeval_gui.job_types.evaluate_fim import run_evaluate_fim_task
          run_evaluate_fim_task('abc', '1', 'smallest_extent', S3_CONFIG)

          case_dir = os.path.join(captured['main_dir'], 'case_study')
          self.assertTrue(
              os.path.exists(os.path.join(case_dir, 'benchmark.tif')),
              'benchmark.tif must exist inside case_study subdir of main_dir',
          )
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_job_types.py -v 2
  ```
  Expected: `ImportError: No module named 'tethysapp.fimeval_gui.job_types'`

- [ ] **Step 3: Create `job_types/registry.py`**

  ```python
  class JobType:
      name: str

      def build_delayed(self, **params):
          raise NotImplementedError
  ```

- [ ] **Step 4: Create `job_types/evaluate_fim.py`**

  ```python
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
  ```

- [ ] **Step 5: Create `job_types/__init__.py`**

  ```python
  from tethysapp.fimeval_gui.job_types.evaluate_fim import EvaluateFIMJobType

  REGISTRY = {
      'evaluate_fim': EvaluateFIMJobType(),
  }
  ```

- [ ] **Step 6: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_job_types.py -v 2
  ```
  Expected: 6 tests PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add .
  git commit -m "feat: add pluggable job type registry and EvaluateFIM job type"
  ```

---

## Task 4: Upload Endpoint

`POST /apps/fimeval-gui/api/upload/`

Accepts `benchmark` (single file) and `candidates` (one or more files). Uploads to S3 with standardised names (`benchmark.tif`, `candidate_0.tif`, …). Returns `upload_id` for use in the submit endpoint.

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Create: `tethysapp/fimeval_gui/tests/test_api.py` (first test class only)

- [ ] **Step 1: Write the failing tests**

  Create `tethysapp/fimeval_gui/tests/test_api.py`:

  ```python
  import json
  import os
  from unittest.mock import MagicMock, patch

  import boto3
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
          self.assertIn('benchmark_key', body)
          self.assertIn('candidate_keys', body)
          self.assertEqual(len(body['candidate_keys']), 1)
          self.assertIn('benchmark.tif', body['benchmark_key'])

      def test_upload_stores_files_in_s3(self):
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
          bench_obj = s3.get_object(
              Bucket=BUCKET, Key=f'fimeval/uploads/{user_id}/{upload_id}/benchmark.tif'
          )
          self.assertEqual(bench_obj['Body'].read(), b'bench data')

      def test_upload_requires_login(self):
          client = self.get_test_client()  # not logged in
          response = client.post('/apps/fimeval-gui/api/upload/', {})
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

      def test_wrong_method_returns_405(self):
          response = self.client.get('/apps/fimeval-gui/api/upload/')
          self.assertEqual(response.status_code, 405)
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestUploadEndpoint -v 2
  ```
  Expected: 404 errors (endpoint not registered yet).

- [ ] **Step 3: Implement the upload endpoint in `controllers.py`**

  Replace the full contents of `tethysapp/fimeval_gui/controllers.py`:

  ```python
  import uuid

  from django.http import JsonResponse
  from tethys_sdk.routing import controller


  def _get_storage():
      from tethysapp.fimeval_gui.app import App
      from tethysapp.fimeval_gui.storage import S3Storage
      return S3Storage(
          endpoint_url=App.get_custom_setting('minio_endpoint_url'),
          access_key=App.get_custom_setting('minio_access_key'),
          secret_key=App.get_custom_setting('minio_secret_key'),
          bucket=App.get_custom_setting('s3_bucket'),
      )


  @controller(login_required=False)
  def home(request):
      """Controller for the app home page (SPA catch-all)."""
      from tethysapp.fimeval_gui.app import App
      return App.render(request, 'index.html')


  @controller(url='api/upload', login_required=True, name='api_upload')
  def api_upload(request):
      if request.method != 'POST':
          return JsonResponse({'error': 'Method not allowed'}, status=405)

      benchmark_file = request.FILES.get('benchmark')
      candidate_files = request.FILES.getlist('candidates')

      if not benchmark_file:
          return JsonResponse({'error': 'benchmark file is required'}, status=400)
      if not candidate_files:
          return JsonResponse({'error': 'at least one candidate file is required'}, status=400)

      upload_id = str(uuid.uuid4())
      user_id = str(request.user.id)
      storage = _get_storage()

      benchmark_key = f'fimeval/uploads/{user_id}/{upload_id}/benchmark.tif'
      storage.upload_fileobj(benchmark_file, benchmark_key)

      candidate_keys = []
      for i, cfile in enumerate(candidate_files):
          key = f'fimeval/uploads/{user_id}/{upload_id}/candidate_{i}.tif'
          storage.upload_fileobj(cfile, key)
          candidate_keys.append(key)

      return JsonResponse({
          'upload_id': upload_id,
          'benchmark_key': benchmark_key,
          'candidate_keys': candidate_keys,
      })
  ```

- [ ] **Step 4: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestUploadEndpoint -v 2
  ```
  Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add .
  git commit -m "feat: add upload endpoint POST /api/upload/"
  ```

---

## Task 5: Submit Endpoint

`POST /apps/fimeval-gui/api/jobs/`

Request body (JSON): `{"upload_id": "...", "method": "smallest_extent"}`.
Valid methods: `smallest_extent`, `convex_hull`.
Creates a `DaskJob`, sets the delayed computation, executes, returns `job_id`.

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Modify: `tethysapp/fimeval_gui/tests/test_api.py` (add `TestSubmitEndpoint`)

- [ ] **Step 1: Write the failing tests**

  Append to `tethysapp/fimeval_gui/tests/test_api.py`:

  ```python
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
              Key=f'fimeval/uploads/{user_id}/{upload_id}/benchmark.tif',
              Body=b'b',
          )

      def test_submit_returns_job_id_and_status(self):
          self._put_upload('u1')
          response = self.client.post(
              '/apps/fimeval-gui/api/jobs/',
              data=json.dumps({'upload_id': 'u1', 'method': 'smallest_extent'}),
              content_type='application/json',
          )
          self.assertEqual(response.status_code, 200)
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
          self._put_upload('u3')
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
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestSubmitEndpoint -v 2
  ```
  Expected: 404 errors (endpoint not registered).

- [ ] **Step 3: Add the submit endpoint to `controllers.py`**

  Add after the `api_upload` function (do not remove anything already there):

  ```python
  VALID_METHODS = {'smallest_extent', 'convex_hull'}


  @controller(url='api/jobs', login_required=True, name='api_jobs_submit')
  def api_jobs_submit(request):
      if request.method != 'POST':
          return JsonResponse({'error': 'Method not allowed'}, status=405)

      try:
          body = __import__('json').loads(request.body)
      except Exception:
          return JsonResponse({'error': 'Invalid JSON body'}, status=400)

      upload_id = body.get('upload_id')
      method = body.get('method')

      if not upload_id:
          return JsonResponse({'error': 'upload_id is required'}, status=400)
      if method not in VALID_METHODS:
          return JsonResponse(
              {'error': f'method must be one of {sorted(VALID_METHODS)}'}, status=400
          )

      user_id = str(request.user.id)
      storage = _get_storage()
      if not storage.list_prefix(f'fimeval/uploads/{user_id}/{upload_id}/'):
          return JsonResponse({'error': 'upload_id not found'}, status=404)

      from tethysapp.fimeval_gui.app import App
      from tethys_sdk.jobs import DaskJob
      from tethysapp.fimeval_gui.job_types import REGISTRY

      s3_config = {
          'endpoint_url': App.get_custom_setting('minio_endpoint_url'),
          'access_key': App.get_custom_setting('minio_access_key'),
          'secret_key': App.get_custom_setting('minio_secret_key'),
          'bucket': App.get_custom_setting('s3_bucket'),
      }

      job_manager = App.get_job_manager()
      job = job_manager.create_job(
          name=f'evaluate_fim_{upload_id}',
          user=request.user,
          job_type=DaskJob,
          scheduler=App.get_scheduler('dask_primary'),
      )
      job.extended_properties = {
          'upload_id': upload_id,
          'user_id': user_id,
          'method': method,
      }
      job.dask_delayed = REGISTRY['evaluate_fim'].build_delayed(
          upload_id=upload_id, user_id=user_id, method=method, s3_config=s3_config,
      )
      job.save()
      job.execute()

      return JsonResponse({'job_id': job.id, 'status': 'submitted'})
  ```

- [ ] **Step 4: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestSubmitEndpoint -v 2
  ```
  Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add .
  git commit -m "feat: add submit endpoint POST /api/jobs/"
  ```

---

## Task 6: Status Endpoint

`GET /apps/fimeval-gui/api/jobs/{job_id}/`

Returns job status, timestamps, method, and upload_id from the `DaskJob` record.
Tethys job status values: `Pending`, `Submitted`, `Running`, `Complete`, `Error`, `Aborted`.

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Modify: `tethysapp/fimeval_gui/tests/test_api.py` (add `TestStatusEndpoint`)

- [ ] **Step 1: Write the failing tests**

  Append to `tethysapp/fimeval_gui/tests/test_api.py`:

  ```python
  class TestStatusEndpoint(TethysTestCase):
      def setUp(self):
          super().setUp()
          self.user = self.create_test_user(username='carol', password='pw', email='c@b.com')
          self.other = self.create_test_user(username='eve', password='pw', email='e@b.com')
          self.client = self.get_test_client()
          self.client.force_login(self.user)

      def _make_mock_job(self, job_id=7, status='Running', user=None):
          job = MagicMock()
          job.id = job_id
          job.status = status
          job.user = user or self.user
          job.creation_time = None
          job.completion_time = None
          job.extended_properties = {'upload_id': 'abc', 'method': 'smallest_extent'}
          return job

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_status_returns_job_info(self, mock_tj):
          mock_tj.objects.get_subclass.return_value = self._make_mock_job()
          response = self.client.get('/apps/fimeval-gui/api/jobs/7/')
          self.assertEqual(response.status_code, 200)
          body = json.loads(response.content)
          self.assertEqual(body['job_id'], 7)
          self.assertEqual(body['status'], 'Running')
          self.assertEqual(body['method'], 'smallest_extent')

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_status_404_for_unknown_job(self, mock_tj):
          from tethys_sdk.jobs import TethysJob as RealTJ
          mock_tj.objects.get_subclass.side_effect = RealTJ.DoesNotExist
          response = self.client.get('/apps/fimeval-gui/api/jobs/999/')
          self.assertEqual(response.status_code, 404)

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_status_403_for_other_users_job(self, mock_tj):
          mock_tj.objects.get_subclass.return_value = self._make_mock_job(user=self.other)
          response = self.client.get('/apps/fimeval-gui/api/jobs/7/')
          self.assertEqual(response.status_code, 403)
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestStatusEndpoint -v 2
  ```
  Expected: 404 errors (endpoint not registered).

- [ ] **Step 3: Add the status endpoint to `controllers.py`**

  Add these imports near the top of `controllers.py` (after the existing imports):

  ```python
  from tethys_sdk.jobs import TethysJob
  ```

  Add the controller function:

  ```python
  @controller(url='api/jobs/{job_id}', login_required=True, name='api_job_status')
  def api_job_status(request, job_id):
      if request.method != 'GET':
          return JsonResponse({'error': 'Method not allowed'}, status=405)

      try:
          job = TethysJob.objects.get_subclass(id=job_id)
      except TethysJob.DoesNotExist:
          return JsonResponse({'error': 'Job not found'}, status=404)

      if job.user != request.user:
          return JsonResponse({'error': 'Forbidden'}, status=403)

      return JsonResponse({
          'job_id': job.id,
          'status': job.status,
          'created': job.creation_time.isoformat() if job.creation_time else None,
          'completed': job.completion_time.isoformat() if job.completion_time else None,
          'method': job.extended_properties.get('method'),
          'upload_id': job.extended_properties.get('upload_id'),
      })
  ```

- [ ] **Step 4: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestStatusEndpoint -v 2
  ```
  Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add .
  git commit -m "feat: add status endpoint GET /api/jobs/{job_id}/"
  ```

---

## Task 7: List Outputs Endpoint

`GET /apps/fimeval-gui/api/jobs/{job_id}/outputs/`

Lists files in S3 at `fimeval/outputs/<user_id>/<upload_id>/`. Only available when job status is `Complete`.

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Modify: `tethysapp/fimeval_gui/tests/test_api.py` (add `TestOutputsEndpoint`)

- [ ] **Step 1: Write the failing tests**

  Append to `tethysapp/fimeval_gui/tests/test_api.py`:

  ```python
  class TestOutputsEndpoint(TethysTestCase):
      def setUp(self):
          super().setUp()
          self.mock_s3 = mock_aws()
          self.mock_s3.start()
          boto3.client('s3', region_name='us-east-1').create_bucket(Bucket=BUCKET)

          self.app_patcher = patch('tethysapp.fimeval_gui.controllers.App')
          self.mock_app = self.app_patcher.start()
          self.mock_app.get_custom_setting.side_effect = _app_settings_side_effect

          self.user = self.create_test_user(username='dan', password='pw', email='d@b.com')
          self.client = self.get_test_client()
          self.client.force_login(self.user)

      def tearDown(self):
          self.app_patcher.stop()
          self.mock_s3.stop()
          super().tearDown()

      def _make_mock_job(self, status='Complete', user=None):
          job = MagicMock()
          job.id = 5
          job.status = status
          job.user = user or self.user
          job.extended_properties = {'upload_id': 'abc123', 'user_id': str(self.user.id)}
          return job

      def _put_outputs(self, user_id, upload_id):
          s3 = boto3.client('s3', region_name='us-east-1')
          s3.put_object(Bucket=BUCKET,
                        Key=f'fimeval/outputs/{user_id}/{upload_id}/EvaluationMetrics.csv',
                        Body=b'csv data')
          s3.put_object(Bucket=BUCKET,
                        Key=f'fimeval/outputs/{user_id}/{upload_id}/contingency.tif',
                        Body=b'tif data')

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_outputs_lists_files(self, mock_tj):
          self._put_outputs(str(self.user.id), 'abc123')
          mock_tj.objects.get_subclass.return_value = self._make_mock_job()

          response = self.client.get('/apps/fimeval-gui/api/jobs/5/outputs/')
          self.assertEqual(response.status_code, 200)
          body = json.loads(response.content)
          names = [f['name'] for f in body['files']]
          self.assertCountEqual(names, ['EvaluationMetrics.csv', 'contingency.tif'])

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_outputs_400_if_job_not_complete(self, mock_tj):
          mock_tj.objects.get_subclass.return_value = self._make_mock_job(status='Running')
          response = self.client.get('/apps/fimeval-gui/api/jobs/5/outputs/')
          self.assertEqual(response.status_code, 400)

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_outputs_403_for_other_users_job(self, mock_tj):
          other = self.create_test_user(username='eve2', password='pw', email='e2@b.com')
          mock_tj.objects.get_subclass.return_value = self._make_mock_job(user=other)
          response = self.client.get('/apps/fimeval-gui/api/jobs/5/outputs/')
          self.assertEqual(response.status_code, 403)
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestOutputsEndpoint -v 2
  ```
  Expected: 404 errors.

- [ ] **Step 3: Add the outputs endpoint to `controllers.py`**

  ```python
  @controller(url='api/jobs/{job_id}/outputs', login_required=True, name='api_job_outputs')
  def api_job_outputs(request, job_id):
      if request.method != 'GET':
          return JsonResponse({'error': 'Method not allowed'}, status=405)

      try:
          job = TethysJob.objects.get_subclass(id=job_id)
      except TethysJob.DoesNotExist:
          return JsonResponse({'error': 'Job not found'}, status=404)

      if job.user != request.user:
          return JsonResponse({'error': 'Forbidden'}, status=403)

      if job.status != 'Complete':
          return JsonResponse({'error': f'Job is not complete (status: {job.status})'}, status=400)

      storage = _get_storage()
      user_id = job.extended_properties['user_id']
      upload_id = job.extended_properties['upload_id']
      prefix = f'fimeval/outputs/{user_id}/{upload_id}/'

      keys = storage.list_prefix(prefix)
      files = [{'name': k.split('/')[-1], 'key': k} for k in keys]
      return JsonResponse({'files': files})
  ```

- [ ] **Step 4: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestOutputsEndpoint -v 2
  ```
  Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add .
  git commit -m "feat: add outputs list endpoint GET /api/jobs/{job_id}/outputs/"
  ```

---

## Task 8: Download Endpoint

`GET /apps/fimeval-gui/api/jobs/{job_id}/download/?file=<filename>`

Generates a presigned S3 URL for the requested output file and redirects (303) to it.
Only available when job status is `Complete`.

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Modify: `tethysapp/fimeval_gui/tests/test_api.py` (add `TestDownloadEndpoint`)

- [ ] **Step 1: Write the failing tests**

  Append to `tethysapp/fimeval_gui/tests/test_api.py`:

  ```python
  class TestDownloadEndpoint(TethysTestCase):
      def setUp(self):
          super().setUp()
          self.mock_s3 = mock_aws()
          self.mock_s3.start()
          boto3.client('s3', region_name='us-east-1').create_bucket(Bucket=BUCKET)

          self.app_patcher = patch('tethysapp.fimeval_gui.controllers.App')
          self.mock_app = self.app_patcher.start()
          self.mock_app.get_custom_setting.side_effect = _app_settings_side_effect

          self.user = self.create_test_user(username='frank', password='pw', email='f@b.com')
          self.client = self.get_test_client()
          self.client.force_login(self.user)

      def tearDown(self):
          self.app_patcher.stop()
          self.mock_s3.stop()
          super().tearDown()

      def _make_mock_job(self, status='Complete', user=None):
          job = MagicMock()
          job.id = 3
          job.status = status
          job.user = user or self.user
          job.extended_properties = {'upload_id': 'xyz', 'user_id': str(self.user.id)}
          return job

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_download_redirects_to_presigned_url(self, mock_tj):
          s3 = boto3.client('s3', region_name='us-east-1')
          user_id = str(self.user.id)
          s3.put_object(Bucket=BUCKET,
                        Key=f'fimeval/outputs/{user_id}/xyz/EvaluationMetrics.csv',
                        Body=b'csv')
          mock_tj.objects.get_subclass.return_value = self._make_mock_job()

          response = self.client.get(
              '/apps/fimeval-gui/api/jobs/3/download/?file=EvaluationMetrics.csv',
              follow=False,
          )
          self.assertIn(response.status_code, [301, 302, 303])

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_download_400_if_job_not_complete(self, mock_tj):
          mock_tj.objects.get_subclass.return_value = self._make_mock_job(status='Running')
          response = self.client.get(
              '/apps/fimeval-gui/api/jobs/3/download/?file=EvaluationMetrics.csv'
          )
          self.assertEqual(response.status_code, 400)

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_download_400_if_file_param_missing(self, mock_tj):
          mock_tj.objects.get_subclass.return_value = self._make_mock_job()
          response = self.client.get('/apps/fimeval-gui/api/jobs/3/download/')
          self.assertEqual(response.status_code, 400)

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_download_404_for_nonexistent_file(self, mock_tj):
          mock_tj.objects.get_subclass.return_value = self._make_mock_job()
          response = self.client.get(
              '/apps/fimeval-gui/api/jobs/3/download/?file=ghost.tif'
          )
          self.assertEqual(response.status_code, 404)

      @patch('tethysapp.fimeval_gui.controllers.TethysJob')
      def test_download_403_for_other_users_job(self, mock_tj):
          other = self.create_test_user(username='grace', password='pw', email='g@b.com')
          mock_tj.objects.get_subclass.return_value = self._make_mock_job(user=other)
          response = self.client.get(
              '/apps/fimeval-gui/api/jobs/3/download/?file=EvaluationMetrics.csv'
          )
          self.assertEqual(response.status_code, 403)
  ```

- [ ] **Step 2: Run to verify they fail**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestDownloadEndpoint -v 2
  ```
  Expected: 404 errors.

- [ ] **Step 3: Add the download endpoint to `controllers.py`**

  ```python
  @controller(url='api/jobs/{job_id}/download', login_required=True, name='api_job_download')
  def api_job_download(request, job_id):
      from django.http import HttpResponseRedirect

      if request.method != 'GET':
          return JsonResponse({'error': 'Method not allowed'}, status=405)

      filename = request.GET.get('file')
      if not filename:
          return JsonResponse({'error': 'file query parameter is required'}, status=400)

      try:
          job = TethysJob.objects.get_subclass(id=job_id)
      except TethysJob.DoesNotExist:
          return JsonResponse({'error': 'Job not found'}, status=404)

      if job.user != request.user:
          return JsonResponse({'error': 'Forbidden'}, status=403)

      if job.status != 'Complete':
          return JsonResponse({'error': f'Job is not complete (status: {job.status})'}, status=400)

      storage = _get_storage()
      user_id = job.extended_properties['user_id']
      upload_id = job.extended_properties['upload_id']
      key = f'fimeval/outputs/{user_id}/{upload_id}/{filename}'

      if not storage.key_exists(key):
          return JsonResponse({'error': f'{filename} not found in job outputs'}, status=404)

      return HttpResponseRedirect(storage.presigned_url(key))
  ```

- [ ] **Step 4: Run to verify tests pass**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests/test_api.py::TestDownloadEndpoint -v 2
  ```
  Expected: 5 tests PASS.

- [ ] **Step 5: Run the full test suite to confirm nothing is broken**

  ```bash
  tethys manage test tethysapp/fimeval_gui/tests -v 2
  ```
  Expected: all tests in `tests.py`, `test_storage.py`, `test_job_types.py`, `test_api.py` PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add .
  git commit -m "feat: add download endpoint GET /api/jobs/{job_id}/download/"
  ```

---

## Smoke Test: End-to-End via curl

With the Tethys dev server, MinIO, and Dask all running, manually verify the full flow:

```bash
# 1. Get a session cookie (replace with your dev credentials)
curl -c cookies.txt -b cookies.txt -X POST http://127.0.0.1:8000/accounts/login/ \
  -d "username=admin&password=admin&csrfmiddlewaretoken=$(curl -c cookies.txt -s http://127.0.0.1:8000/accounts/login/ | grep csrfmiddlewaretoken | sed 's/.*value="\([^"]*\)".*/\1/')"

# 2. Upload benchmark + candidate
curl -b cookies.txt -X POST http://127.0.0.1:8000/apps/fimeval-gui/api/upload/ \
  -F "benchmark=@/path/to/benchmark_flood.tif" \
  -F "candidates=@/path/to/candidate.tif"
# → {"upload_id": "...", "benchmark_key": "...", "candidate_keys": [...]}

# 3. Submit job (replace UPLOAD_ID)
curl -b cookies.txt -X POST http://127.0.0.1:8000/apps/fimeval-gui/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"upload_id": "UPLOAD_ID", "method": "smallest_extent"}'
# → {"job_id": 1, "status": "submitted"}

# 4. Poll status (replace JOB_ID)
curl -b cookies.txt http://127.0.0.1:8000/apps/fimeval-gui/api/jobs/JOB_ID/
# → {"status": "Running", ...}  then eventually "Complete"

# 5. List outputs
curl -b cookies.txt http://127.0.0.1:8000/apps/fimeval-gui/api/jobs/JOB_ID/outputs/
# → {"files": [{"name": "EvaluationMetrics.csv", ...}]}

# 6. Download a file (follow the redirect)
curl -L -b cookies.txt \
  "http://127.0.0.1:8000/apps/fimeval-gui/api/jobs/JOB_ID/download/?file=EvaluationMetrics.csv" \
  -o EvaluationMetrics.csv
```

---

## API Reference Summary

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| `POST` | `/apps/fimeval-gui/api/upload/` | Required | Upload benchmark + candidates; returns `upload_id` |
| `POST` | `/apps/fimeval-gui/api/jobs/` | Required | Submit job; returns `job_id` |
| `GET`  | `/apps/fimeval-gui/api/jobs/{job_id}/` | Required | Poll status |
| `GET`  | `/apps/fimeval-gui/api/jobs/{job_id}/outputs/` | Required | List output files (job must be Complete) |
| `GET`  | `/apps/fimeval-gui/api/jobs/{job_id}/download/?file=<name>` | Required | Redirect to presigned download URL |

---

## Known Assumptions to Verify

1. **`fimeval` import path**: The plan uses `import fimeval` and `fimeval.EvaluateFIM(...)`. Confirm with `python -c "import fimeval; print(fimeval.__file__)"` in the tethys conda environment.

2. **`SchedulerSetting` import**: The plan uses `from tethys_sdk.app_settings import SchedulerSetting`. If this fails, check `tethys_sdk.__version__` and the Tethys changelog for the correct import location.

3. **`App.get_scheduler` API**: Used as `App.get_scheduler('dask_primary')` in the submit controller. Verify this is the correct call signature in your Tethys version — it may be `App.get_app().get_scheduler(...)`.

4. **`job_manager.create_job` kwargs**: The `scheduler=` kwarg is assumed to be accepted directly. If not, set `job.scheduler` after creation and call `job.save()` before `job.execute()`.

5. **FIMeval output directory structure**: The task function uploads everything under `output_dir`. If FIMeval creates nested subdirectories, those are preserved in the S3 key (using `os.path.relpath`). The outputs endpoint only returns the filename of the leaf node (`key.split('/')[-1]`); adjust if you need subdirectory-aware paths.
