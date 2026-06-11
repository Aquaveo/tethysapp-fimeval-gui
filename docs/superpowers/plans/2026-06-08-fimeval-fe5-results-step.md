# FIMEVAL-FE5 — Results Step (metrics + downloads) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Results step load and show the job's metrics (headline cards + full table) and output files (download links), with a "Start New Evaluation" reset — backed by a relaxed completion guard and a new same-origin metrics endpoint.

**Architecture:** Two backend changes — drop the `_status=='COM'` guard on outputs/download (use outputs-in-MinIO as the completion signal, consistent with the status endpoint) and add `GET /api/jobs/{id}/metrics/` that parses `EvaluationMetrics.csv` server-side into JSON. Frontend `api.ts` gains `getJobOutputs`/`getJobMetrics`/`downloadUrl`; `ResultsStep` fetches both on mount and renders the payoff screen; `App` passes `jobId`+`onReset` and sheds the now-dead `goBack`/`STEP_ORDER`.

**Tech Stack:** Tethys 4 / Django (backend); React 19, TypeScript (strict, `verbatimModuleSyntax`), Vite, plain CSS (frontend).

---

## Project-Specific Constraints (read before starting)

- Backend `@controller` uses `{param}` URL syntax. `DaskJob.objects.get(id=...)` then explicit `job.user != request.user → 403` (matches the other endpoints).
- Frontend: React 19 + `react-jsx` (no `import React`); `verbatimModuleSyntax` (inline/`import type` for types); component files export only their default component; `api.ts` may export types. `strict`/`noUnusedLocals`/`noUnusedParameters`. `react-hooks/exhaustive-deps` and `react-hooks/set-state-in-effect` are enabled (don't synchronously `setState` at the top of an effect body).
- No frontend component test framework — verify frontend with `npx tsc -b` + `npm run lint` + `npm run build`. Backend has a real suite (`tethys manage test`).
- Brand theme: CSS vars in `styles/theme.css` (`--color-primary` `#25C2DF`, `--color-surface`, `--color-surface-alt`, `--color-border`, `--color-text`, `--color-text-secondary`, `--color-text-muted`, `--color-error`, `--radius-md`, `--radius-lg`, `--shadow-sm`); `.button-primary` (+ the `.button-primary:disabled` rule already in `UploadStep.css`); Alan Sans is global.
- **Coupling:** `App.tsx` + `ResultsStep.tsx` change the prop contract together (`onBack` → `jobId`+`onReset`); land them in one task.

## File Structure

- **Modify `tethysapp/fimeval_gui/controllers.py`** — `import csv`, `import io`; drop the COM guard on `api_job_outputs` + `api_job_download`; add `api_job_metrics`.
- **Modify `tethysapp/fimeval_gui/tests/test_api.py`** — update the two "400 if not complete" tests; add `TestMetricsEndpoint`.
- **Modify `reactapp/src/api.ts`** — output/metrics types + `getJobOutputs`/`getJobMetrics`/`downloadUrl`.
- **Modify `reactapp/src/ResultsStep.tsx`** — full rewrite (fetch + render).
- **Create `reactapp/src/ResultsStep.css`** — centered/contained layout, cards, table, downloads.
- **Modify `reactapp/src/App.tsx`** — pass `jobId`+`onReset`; remove `goBack`/`index`/`STEP_ORDER` import.

## Git / Commit Convention (project-specific)

**Commits require explicit user go-ahead; the user tests manually first.** No per-task commits. Implement all tasks, run the gates, then hand off for manual verification. One commit at the end after the user approves (Task 6).

---

### Task 1: Backend — relax the Complete guard on outputs + download

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Modify: `tethysapp/fimeval_gui/tests/test_api.py`

- [ ] **Step 1: Remove the COM guard from `api_job_outputs`**

In `controllers.py`, delete these two lines from `api_job_outputs` (currently right after the `job.user != request.user` 403 check):

```python
    if job._status != 'COM':
        return JsonResponse({'error': 'job is not complete'}, status=400)
```

The endpoint now relies on the existing `if not keys: return 404 'no outputs yet'` as the not-ready signal — consistent with the status endpoint's "outputs present ⇒ complete" model.

- [ ] **Step 2: Remove the COM guard from `api_job_download`**

In `controllers.py`, delete these two lines from `api_job_download` (right after its `job.user != request.user` 403 check):

```python
    if job._status != 'COM':
        return JsonResponse({'error': 'job is not complete'}, status=400)
```

Download now relies on the prefix-scope 403 + `key_exists` 404 it already has.

- [ ] **Step 3: Update the two "400 if not complete" tests to the new behavior**

In `test_api.py`, replace `TestOutputsEndpoint.test_outputs_returns_400_if_job_not_complete` with a test that a not-yet-COM job whose outputs are present still returns them:

```python
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
```

And replace `TestDownloadEndpoint.test_download_returns_400_if_job_not_complete` with:

```python
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
```

- [ ] **Step 4: Run the backend suite**

Run: `cd /home/rragh/tethysdev/tethysapp-fimeval-gui && tethys manage test tethysapp/fimeval_gui/tests`
Expected: all pass (the two updated tests reflect the relaxed guard; everything else unchanged). Count stays 61 for now.

---

### Task 2: Backend — `GET /api/jobs/{job_id}/metrics/`

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`
- Modify: `tethysapp/fimeval_gui/tests/test_api.py`

- [ ] **Step 1: Add `csv` + `io` imports**

At the top of `controllers.py`, add to the stdlib imports (which currently are `import json as json_module` / `import logging` / `import uuid`):

```python
import csv
import io
```

- [ ] **Step 2: Add the `api_job_metrics` controller**

Append after `api_job_download` in `controllers.py`:

```python
@controller(url='api/jobs/{job_id}/metrics', login_required=True, name='api_job_metrics')
def api_job_metrics(request, job_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        job = DaskJob.objects.get(id=job_id)
    except DaskJob.DoesNotExist:
        return JsonResponse({'error': 'job not found'}, status=404)

    if job.user != request.user:
        return JsonResponse({'error': 'access denied'}, status=403)

    props = job.extended_properties or {}
    upload_id = props.get('upload_id')
    user_id = props.get('user_id')
    if not upload_id or not user_id:
        return JsonResponse({'error': 'metrics not available yet'}, status=404)

    storage = _get_storage()
    try:
        keys = storage.list_prefix(f'outputs/{user_id}/{upload_id}/')
        metrics_key = next(
            (k for k in keys if k.split('/')[-1] == 'EvaluationMetrics.csv'), None
        )
        if not metrics_key:
            return JsonResponse({'error': 'metrics not available yet'}, status=404)
        raw = storage.get_object(metrics_key)['Body'].read().decode('utf-8')
    except (ClientError, BotoCoreError) as exc:
        logger.error('S3 metrics fetch failed for job %s: %s', job_id, exc)
        return JsonResponse({'error': 'storage unavailable'}, status=503)

    rows = [r for r in csv.reader(io.StringIO(raw)) if r]
    if not rows:
        return JsonResponse({'error': 'metrics not available yet'}, status=404)

    candidates = rows[0][1:]  # header: ['Metrics', '<candidate>', ...]
    metrics = []
    for row in rows[1:]:
        name = row[0]
        if name.endswith('_values'):
            name = name[: -len('_values')]
        values = {}
        for i, cand in enumerate(candidates):
            try:
                values[cand] = float(row[i + 1])
            except (ValueError, IndexError):
                values[cand] = None
        metrics.append({'metric': name, 'values': values})

    return JsonResponse({'job_id': job.id, 'candidates': candidates, 'metrics': metrics})
```

- [ ] **Step 3: Add `TestMetricsEndpoint`**

Append to `test_api.py`:

```python
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
```

- [ ] **Step 4: Run the backend suite**

Run: `cd /home/rragh/tethysdev/tethysapp-fimeval-gui && tethys manage test tethysapp/fimeval_gui/tests`
Expected: all pass (66 total: 61 + 5 new metrics tests).

---

### Task 3: Frontend — `api.ts` additions

**Files:**
- Modify: `reactapp/src/api.ts`

- [ ] **Step 1: Append the types + functions**

Add to the end of `reactapp/src/api.ts`:

```ts
export interface OutputFile {
  name: string;
  key: string;
}

export interface JobOutputs {
  job_id: number;
  files: OutputFile[];
}

export interface MetricRow {
  metric: string;
  values: Record<string, number | null>;
}

export interface JobMetrics {
  job_id: number;
  candidates: string[];
  metrics: MetricRow[];
}

export async function getJobOutputs(jobId: number): Promise<JobOutputs> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/outputs/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export async function getJobMetrics(jobId: number): Promise<JobMetrics> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/metrics/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

// Anchor href target. The browser follows the 303 → presigned MinIO URL as a
// navigation/download, so no CORS is involved (unlike reading the body in JS).
export function downloadUrl(jobId: number, key: string): string {
  return `${API_BASE}/jobs/${jobId}/download/?file=${encodeURIComponent(key)}`;
}
```

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS.

---

### Task 4: Frontend — ResultsStep rewrite + App wiring (coupled)

**Files:**
- Modify: `reactapp/src/ResultsStep.tsx` (full replace)
- Modify: `reactapp/src/App.tsx` (full replace)

- [ ] **Step 1: Replace ResultsStep.tsx**

```tsx
// reactapp/src/ResultsStep.tsx
import { useEffect, useState } from 'react';
import { getJobOutputs, getJobMetrics, downloadUrl } from './api';
import type { OutputFile, JobMetrics } from './api';
import './ResultsStep.css';

interface ResultsStepProps {
  jobId: number;
  onReset: () => void;
}

const HEADLINE_METRICS = ['CSI', 'POD', 'FAR'];

function formatValue(v: number | null): string {
  if (v === null) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(4);
}

function ResultsStep({ jobId, onReset }: ResultsStepProps) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [metrics, setMetrics] = useState<JobMetrics | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retried = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const out = await getJobOutputs(jobId);
        if (cancelled) return;
        setOutputs(out.files);
        // Metrics are optional: a run without EvaluationMetrics.csv still lists files.
        try {
          const m = await getJobMetrics(jobId);
          if (!cancelled) setMetrics(m);
        } catch {
          if (!cancelled) setMetrics(null);
        }
        if (!cancelled) setPhase('ready');
      } catch {
        if (cancelled) return;
        // Rare race: the output listing lags right after completion. Retry once.
        if (!retried) {
          retried = true;
          timeout = setTimeout(load, 2000);
        } else {
          setPhase('error');
        }
      }
    };

    load();
    return () => {
      cancelled = true;
      if (timeout !== undefined) clearTimeout(timeout);
    };
  }, [jobId]);

  if (phase === 'loading') {
    return (
      <div className="step-placeholder results-step">
        <div className="results-spinner" aria-hidden="true" />
        <p className="results-loading">Loading results&hellip;</p>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="step-placeholder results-step">
        <h2>Results</h2>
        <p className="results-error">Could not load the evaluation results.</p>
        <div className="results-actions">
          <button type="button" className="button-primary" onClick={onReset}>
            Start Over
          </button>
        </div>
      </div>
    );
  }

  const candidates = metrics?.candidates ?? [];
  const firstCand = candidates[0];
  const metricValue = (name: string): number | null => {
    if (!metrics || !firstCand) return null;
    const row = metrics.metrics.find((m) => m.metric === name);
    return row ? row.values[firstCand] ?? null : null;
  };
  const headline = HEADLINE_METRICS
    .map((name) => ({ name, value: metricValue(name) }))
    .filter((h) => h.value !== null);

  return (
    <div className="step-placeholder results-step">
      <header className="results-header">
        <h2>Evaluation Results</h2>
        <p className="results-subtitle">
          Job #{jobId}
          {candidates.length > 0 && ` · ${candidates.join(', ')}`}
        </p>
      </header>

      {headline.length > 0 && (
        <div className="results-cards">
          {headline.map((h) => (
            <div className="results-card" key={h.name}>
              <div className="results-card-label">{h.name}</div>
              <div className={`results-card-value ${h.name === 'CSI' ? 'is-csi' : ''}`}>
                {formatValue(h.value)}
              </div>
            </div>
          ))}
        </div>
      )}

      {metrics && metrics.metrics.length > 0 && (
        <div className="results-panel">
          <div className="results-panel-title">All metrics</div>
          <table className="results-table">
            <thead>
              <tr>
                <th>Metric</th>
                {candidates.map((c) => (
                  <th key={c} className="num">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.metrics.map((row) => (
                <tr key={row.metric}>
                  <td>{row.metric}</td>
                  {candidates.map((c) => (
                    <td key={c} className="num">{formatValue(row.values[c] ?? null)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="results-panel">
        <div className="results-panel-title">Output files</div>
        <ul className="results-files">
          {outputs.map((f) => (
            <li className="results-file" key={f.key}>
              <span className="results-file-name">{f.name}</span>
              <a
                className="button-primary results-download"
                href={downloadUrl(jobId, f.key)}
                download
              >
                Download
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div className="results-actions">
        <button type="button" className="button-primary" onClick={onReset}>
          Start New Evaluation
        </button>
      </div>
    </div>
  );
}

export default ResultsStep;
```

- [ ] **Step 2: Replace App.tsx**

```tsx
// reactapp/src/App.tsx
import { useCallback, useEffect, useState } from 'react';
import type { Step } from './types';
import { ensureCsrf } from './api';
import Stepper from './Stepper';
import UploadStep from './UploadStep';
import RunningStep from './RunningStep';
import ResultsStep from './ResultsStep';
import './App.css';

function App() {
  const [step, setStep] = useState<Step>('upload');
  const [jobId, setJobId] = useState<number | null>(null);

  useEffect(() => {
    ensureCsrf();
  }, []);

  const onJobCreated = (id: number) => {
    setJobId(id);
    setStep('running');
  };

  const onComplete = useCallback(() => setStep('results'), []);
  const onReset = useCallback(() => {
    setStep('upload');
    setJobId(null);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>FIMeval</h1>
        <p className="app-subtitle">Flood Inundation Map Evaluation</p>
      </header>

      <Stepper current={step} />

      <main className="step-container">
        {step === 'upload' && <UploadStep onJobCreated={onJobCreated} />}
        {step === 'running' && jobId !== null && (
          <RunningStep jobId={jobId} onComplete={onComplete} onReset={onReset} />
        )}
        {step === 'results' && jobId !== null && (
          <ResultsStep jobId={jobId} onReset={onReset} />
        )}
      </main>
    </div>
  );
}

export default App;
```

Notes:
- `goBack`, `index`, and the `STEP_ORDER` import are gone (no longer used; `Stepper` imports `STEP_ORDER` itself). `type Step` stays (used by `useState`).
- `ResultsStep.css` is imported by `ResultsStep` (created in Task 5); CSS imports aren't type-checked so the gate passes before it exists, but implement Task 5 for a clean `npm run dev`/`build`.

- [ ] **Step 3: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS. No unused-var errors (`goBack`/`index`/`STEP_ORDER` removed).

---

### Task 5: Frontend — ResultsStep.css

**Files:**
- Create: `reactapp/src/ResultsStep.css`

- [ ] **Step 1: Create ResultsStep.css**

```css
/* reactapp/src/ResultsStep.css */

/* Centered + contained so the results don't spread across the page. */
.results-step {
  max-width: 75vw;
  margin: 0 auto;
  text-align: left;
}

/* ---- Loading ---- */
.results-spinner {
  width: 2.5rem;
  height: 2.5rem;
  margin: 1.5rem auto 0;
  border: 3px solid var(--color-surface-alt);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: results-spin 0.8s linear infinite;
}
@keyframes results-spin {
  to {
    transform: rotate(360deg);
  }
}
.results-loading {
  text-align: center;
  color: var(--color-text-secondary);
}
.results-error {
  color: var(--color-error);
  font-weight: 500;
}

/* ---- Header ---- */
.results-header {
  text-align: center;
  margin-bottom: 1.25rem;
}
.results-header h2 {
  margin: 0;
  color: var(--color-text);
}
.results-subtitle {
  margin: 0.2rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.82rem;
}

/* ---- Headline metric cards ---- */
.results-cards {
  display: flex;
  gap: 0.6rem;
  margin-bottom: 1.25rem;
}
.results-card {
  flex: 1;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 0.9rem;
  text-align: center;
}
.results-card-label {
  font-size: 0.68rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}
.results-card-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--color-text);
}
.results-card-value.is-csi {
  color: var(--color-primary);
}

/* ---- Panels (table + files) ---- */
.results-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: 1.25rem;
}
.results-panel-title {
  padding: 0.6rem 0.9rem;
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-surface-alt);
}

/* ---- Metrics table ---- */
.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.results-table thead tr {
  background: var(--color-surface-alt);
  color: var(--color-text-secondary);
}
.results-table th,
.results-table td {
  padding: 0.4rem 0.9rem;
  text-align: left;
}
.results-table th.num,
.results-table td.num {
  text-align: right;
}
.results-table tbody tr:nth-child(even) {
  background: #f7fcfd;
}
.results-table td {
  color: var(--color-text);
}

/* ---- Files list ---- */
.results-files {
  list-style: none;
  margin: 0;
  padding: 0;
}
.results-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0.9rem;
  border-bottom: 1px solid var(--color-bg);
  font-size: 0.82rem;
}
.results-file:last-child {
  border-bottom: none;
}
.results-file-name {
  color: var(--color-text);
  word-break: break-all;
}
.results-download {
  text-decoration: none;
  font-size: 0.75rem;
  padding: 0.3rem 0.8rem;
  white-space: nowrap;
}

/* ---- Actions ---- */
.results-actions {
  display: flex;
  justify-content: center;
}
```

- [ ] **Step 2: Type-check, lint, build**

Run: `cd reactapp && npx tsc -b && npm run lint && npm run build`
Expected: all PASS.

---

### Task 6: Verify and commit (await user go-ahead)

**Files:** none (verification + git)

- [ ] **Step 1: Full backend + frontend gates**

Run:
```bash
cd /home/rragh/tethysdev/tethysapp-fimeval-gui && tethys manage test tethysapp/fimeval_gui/tests
cd reactapp && npx tsc -b && npm run lint && npm run build
```
Expected: backend 66 pass; frontend tsc/lint/build clean.

- [ ] **Step 2: Manual browser walkthrough**

Prereq: Tethys (`:8000`), Dask scheduler + worker, MinIO running; logged in. Test on the Tethys-served page (`:8000`) or with the Vite dev origin fix.
Run an evaluation (or reuse a completed job). On auto-advance to Results, confirm:
- Header "Evaluation Results · Job #N · candidate_0".
- Headline cards CSI / POD / FAR with values matching `EvaluationMetrics.csv` (CSI in cyan).
- Full metrics table lists every metric, ratios to 4 decimals, counts as integers.
- Output files list shows every file; clicking **Download** saves the file (303 → presigned MinIO URL).
- **Start New Evaluation** returns to a fresh Upload step (stepper resets to step 1, `jobId` cleared).
- (Dev) Confirm this works even though the job's `_status` is still `SUB` — i.e. the relaxed guard is doing its job.

Report results and **wait for go-ahead before committing.**

- [ ] **Step 3: Commit (only after user approval)**

```bash
git add .
git commit -m "feat: FIMEVAL-FE5 results step with metrics table + downloads

ResultsStep loads job outputs + parsed metrics on mount and renders headline
CSI/POD/FAR cards, a full metrics table, a download list, and Start New
Evaluation. Add api getJobOutputs/getJobMetrics/downloadUrl. Backend: new
api/jobs/{id}/metrics endpoint (parses EvaluationMetrics.csv server-side) and
relax the outputs/download Complete guard to the outputs-in-MinIO signal the
status endpoint already uses (so it works in dev where the job monitor doesn't
tick). App drops the now-unused goBack/STEP_ORDER.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Push (only after user approval)**

```bash
git push
```

---

## Self-Review

**Spec coverage** (against `2026-06-08-fimeval-fe5-results-step-design.md`):
- Relax outputs guard (outputs-present ⇒ complete) + keep 404 no-outputs → Task 1 ✓
- Relax download guard (keep prefix 403 + key_exists 404) → Task 1 ✓
- Update the two "400 if not complete" tests → Task 1 ✓
- New `api/jobs/{id}/metrics/` (GET, 405/404/403/503, parse CSV, strip `_values`, candidates + metrics) → Task 2 ✓
- `TestMetricsEndpoint` (parsed / 404-absent / 403-other-user / 405 / login) → Task 2 ✓
- `api.ts` types + `getJobOutputs`/`getJobMetrics`/`downloadUrl` → Task 3 ✓
- `ResultsStep` props `{jobId,onReset}`, fetch on mount, retry-once race guard, metrics optional, headline cards + table + downloads + Start New Evaluation, loading/error states → Task 4 ✓
- `ResultsStep.css` centered `max-width:75vw`, cards, table, downloads → Task 5 ✓
- `App.tsx` passes `jobId`+`onReset`, removes `goBack`/`index`/`STEP_ORDER` → Task 4 ✓
- Downloads via anchor → 303 → presigned (no CORS) → Task 4 (`downloadUrl` + `<a download>`) ✓
- Verify backend + frontend + manual → Tasks 1,2,5,6 ✓

**Placeholder scan:** No plan-placeholders; every code step is complete.

**Type consistency:** `getJobOutputs`→`JobOutputs.files: OutputFile[]`; `getJobMetrics`→`JobMetrics` with `candidates: string[]` + `metrics: MetricRow[]` (`values: Record<string, number|null>`) — all consumed with matching shapes in `ResultsStep` (`metrics.candidates`, `row.values[c]`, `formatValue(number|null)`). `downloadUrl(jobId, key)` matches the `<a href>` call. `ResultsStep` props `{jobId:number, onReset:()=>void}` match App's render site. Backend `metrics` JSON shape (`candidates`, `metrics:[{metric, values}]`) matches the `JobMetrics`/`MetricRow` TS types. CSS classes used in Task 4 all have rules in Task 5 (`results-step/-spinner/-loading/-error/-header/-subtitle/-cards/-card/-card-label/-card-value(.is-csi)/-panel/-panel-title/-table(.num)/-files/-file/-file-name/-download/-actions`) plus shared `.button-primary`.

**`set-state-in-effect` note:** the effect never calls `setState` synchronously in its body — all `setPhase`/`setOutputs`/`setMetrics` happen inside the async `load()` after an `await` (or in the retry timeout), so the rule isn't tripped (this is why the loading default is set via `useState('loading')`, not reset at effect top).
