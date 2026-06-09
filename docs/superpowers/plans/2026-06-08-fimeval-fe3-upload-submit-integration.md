# FIMEVAL-FE3 — Upload + Submit API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Upload form to the backend — seed the CSRF cookie, POST the files then the job, and advance to the Running step carrying the returned `job_id`.

**Architecture:** A small Django `api_csrf` endpoint (`@ensure_csrf_cookie`) guarantees the `csrftoken` cookie. A shared `src/api.ts` centralizes all fetch logic (CSRF read, upload, submit). `UploadStep` chains `uploadFiles` → `submitJob` behind its existing button, with in-flight + error state, and reports the new job id up to `App` via `onJobCreated`, which advances the wizard.

**Tech Stack:** Tethys 4 / Django (backend); React 19, TypeScript (strict, `verbatimModuleSyntax`), Vite, plain CSS (frontend).

---

## Project-Specific Constraints (read before starting)

- **Backend:** `@controller` uses `{param}` URL syntax. Decorator order for the CSRF view: `@controller(...)` on top, `@ensure_csrf_cookie` directly above the function (Tethys registers the outer, Django's decorator wraps the view so it sets the cookie when the view runs).
- **Frontend `verbatimModuleSyntax: true`** — type-only imports need the `type` modifier. `api.ts` may export types freely (not a component file). Component files (`App.tsx`, `UploadStep.tsx`, `RunningStep.tsx`) export ONLY their default component (`react-refresh/only-export-components`).
- **React 19 + `react-jsx`** — no `import React`. Import hooks explicitly (`useState`, `useEffect`).
- **`strict`, `noUnusedLocals`, `noUnusedParameters`** — no unused vars/params.
- **No component test framework** — verify frontend with `npx tsc -b` + `npm run lint` + manual. Backend has a real test suite (`tethys manage test`).
- **Absolute API paths** (`/apps/fimeval-gui/api/...`) work in Vite dev (proxy) and production (same path).
- **Coupling note:** the three component files in Task 4 form one contract change (`App` passes `onJobCreated` to `UploadStep` and `jobId` to `RunningStep`). They must land together — `tsc` will not pass with only some of them changed. That's why they're one task.

## File Structure

- **Modify `tethysapp/fimeval_gui/controllers.py`** — add `ensure_csrf_cookie` import + `api_csrf` controller.
- **Modify `tethysapp/fimeval_gui/tests/test_api.py`** — add `TestCsrfEndpoint`.
- **Create `reactapp/src/api.ts`** — shared backend client (`getCsrfToken`, `ensureCsrf`, `uploadFiles`, `submitJob`).
- **Modify `reactapp/src/App.tsx`** — seed CSRF on mount, hold `jobId`, `onJobCreated` advances.
- **Modify `reactapp/src/UploadStep.tsx`** — chain upload+submit, in-flight + error state, `onJobCreated` prop.
- **Modify `reactapp/src/RunningStep.tsx`** — accept + display `jobId`.
- **Modify `reactapp/src/UploadStep.css`** — error banner + inline spinner.

## Git / Commit Convention (project-specific)

**Commits require explicit user go-ahead; the user tests manually first.** No per-task commits. Implement all tasks, run the gates, then hand off for manual verification. One commit at the end after the user approves (Task 6).

---

### Task 1: Backend — `api_csrf` controller

**Files:**
- Modify: `tethysapp/fimeval_gui/controllers.py`

- [ ] **Step 1: Add the `ensure_csrf_cookie` import**

Add this line to the Django imports block (after the existing `from django.http import ...` line on line 7):

```python
from django.views.decorators.csrf import ensure_csrf_cookie
```

- [ ] **Step 2: Add the `api_csrf` controller**

Insert immediately after the `home` controller (after its `return App.render(...)` line, before the `api_upload` controller):

```python
@controller(url='api/csrf', login_required=False, name='api_csrf')
@ensure_csrf_cookie
def api_csrf(request):
    """Set the csrftoken cookie so the SPA can send X-CSRFToken on POSTs."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return JsonResponse({'detail': 'CSRF cookie set'})
```

- [ ] **Step 3: Sanity check the import resolves**

Run: `cd /home/rragh/tethysdev/tethysapp-fimeval-gui && python -c "from django.views.decorators.csrf import ensure_csrf_cookie; print('ok')"`
Expected: `ok`

---

### Task 2: Backend — `TestCsrfEndpoint`

**Files:**
- Modify: `tethysapp/fimeval_gui/tests/test_api.py`

- [ ] **Step 1: Append the test class**

Add at the end of `test_api.py`:

```python
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
```

- [ ] **Step 2: Run the backend suite**

Run: `cd /home/rragh/tethysdev/tethysapp-fimeval-gui && tethys manage test tethysapp/fimeval_gui/tests`
Expected: all tests pass (was 59; now 61 with the two new ones).

---

### Task 3: Frontend — `src/api.ts` shared client

**Files:**
- Create: `reactapp/src/api.ts`

- [ ] **Step 1: Create api.ts**

```ts
// reactapp/src/api.ts
const API_BASE = '/apps/fimeval-gui/api';

export interface UploadResult {
  upload_id: string;
  benchmark_key: string;
  candidate_keys: string[];
}

export interface SubmitResult {
  job_id: number;
  status: string;
}

export function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function ensureCsrf(): Promise<void> {
  try {
    await fetch(`${API_BASE}/csrf/`, { credentials: 'same-origin' });
  } catch {
    // best effort — a later POST surfaces any real problem
  }
}

async function parseError(response: Response): Promise<never> {
  let message = 'Request failed';
  try {
    const body = await response.json();
    if (body && typeof body.error === 'string') message = body.error;
  } catch {
    // non-JSON response; keep the generic message
  }
  throw new Error(message);
}

export async function uploadFiles(
  benchmark: File,
  candidates: File[],
): Promise<UploadResult> {
  const form = new FormData();
  form.append('benchmark', benchmark);
  candidates.forEach((file) => form.append('candidates', file));

  const response = await fetch(`${API_BASE}/upload/`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCsrfToken() },
    body: form,
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export async function submitJob(
  uploadId: string,
  method: string,
): Promise<SubmitResult> {
  const response = await fetch(`${API_BASE}/jobs/`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    body: JSON.stringify({ upload_id: uploadId, method }),
  });
  if (!response.ok) return parseError(response);
  return response.json();
}
```

Notes:
- Do NOT set `Content-Type` on the multipart upload — the browser sets the multipart boundary automatically.
- `parseError` returns `Promise<never>` (it always throws); `return parseError(response)` is assignable to the declared return type and short-circuits before `response.json()`.

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS (`api.ts` is valid even though nothing imports it yet).

---

### Task 4: Frontend — wire components (App + UploadStep + RunningStep)

These three files form one contract change and must be edited together; `tsc` only passes once all three are done.

**Files:**
- Modify: `reactapp/src/App.tsx` (full replace)
- Modify: `reactapp/src/UploadStep.tsx` (full replace)
- Modify: `reactapp/src/RunningStep.tsx` (full replace)

- [ ] **Step 1: Replace App.tsx**

```tsx
// reactapp/src/App.tsx
import { useEffect, useState } from 'react';
import { STEP_ORDER, type Step } from './types';
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

  const index = STEP_ORDER.indexOf(step);
  const goNext = () => {
    if (index < STEP_ORDER.length - 1) setStep(STEP_ORDER[index + 1]);
  };
  const goBack = () => {
    if (index > 0) setStep(STEP_ORDER[index - 1]);
  };

  const onJobCreated = (id: number) => {
    setJobId(id);
    setStep('running');
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>FIMeval</h1>
        <p className="app-subtitle">Flood Inundation Map Evaluation</p>
      </header>

      <Stepper current={step} />

      <main className="step-container">
        {step === 'upload' && <UploadStep onJobCreated={onJobCreated} />}
        {step === 'running' && (
          <RunningStep jobId={jobId} onNext={goNext} onBack={goBack} />
        )}
        {step === 'results' && <ResultsStep onBack={goBack} />}
      </main>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Replace UploadStep.tsx**

```tsx
// reactapp/src/UploadStep.tsx
import { useState } from 'react';
import Dropzone from './Dropzone';
import { uploadFiles, submitJob } from './api';
import './UploadStep.css';

type Method = 'smallest_extent' | 'convex_hull';

interface UploadStepProps {
  onJobCreated: (jobId: number) => void;
}

function UploadStep({ onJobCreated }: UploadStepProps) {
  const [benchmark, setBenchmark] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<File[]>([]);
  const [method, setMethod] = useState<Method>('smallest_extent');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addCandidates = (files: File[]) => {
    setCandidates((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const fresh = files.filter((f) => !seen.has(`${f.name}:${f.size}`));
      return [...prev, ...fresh];
    });
  };

  const removeCandidate = (index: number) => {
    setCandidates((prev) => prev.filter((_, i) => i !== index));
  };

  const isValid = benchmark !== null && candidates.length > 0;

  const handleSubmit = async () => {
    if (!benchmark) return;
    setError(null);
    setSubmitting(true);
    try {
      const { upload_id } = await uploadFiles(benchmark, candidates);
      const { job_id } = await submitJob(upload_id, method);
      onJobCreated(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="step-placeholder upload-step">
      <h2>Upload Files</h2>

      <span className="upload-field-label">Benchmark raster</span>
      <Dropzone
        label="Drop a .tif here"
        multiple={false}
        accept={['.tif', '.tiff']}
        onAccepted={(files) => setBenchmark(files[0])}
      />
      {benchmark && (
        <div className="upload-selected">
          <span className="upload-tick" aria-hidden="true">&#10003;</span>
          <span className="upload-filename">{benchmark.name}</span>
          <button
            type="button"
            className="upload-remove"
            aria-label="Remove benchmark"
            onClick={() => setBenchmark(null)}
          >
            &#10005;
          </button>
        </div>
      )}

      <span className="upload-field-label">Candidate raster(s)</span>
      <Dropzone
        label="Drop one or more .tif here"
        multiple
        accept={['.tif', '.tiff']}
        onAccepted={addCandidates}
      />
      {candidates.length > 0 && (
        <div className="upload-chips">
          {candidates.map((file, i) => (
            <span className="upload-chip" key={`${file.name}:${file.size}`}>
              <span className="upload-tick" aria-hidden="true">&#10003;</span>
              {file.name}
              <button
                type="button"
                className="upload-chip-remove"
                aria-label={`Remove ${file.name}`}
                onClick={() => removeCandidate(i)}
              >
                &#10005;
              </button>
            </span>
          ))}
        </div>
      )}

      <label className="upload-field-label" htmlFor="method-select">Method</label>
      <select
        id="method-select"
        className="upload-select"
        value={method}
        onChange={(e) => setMethod(e.target.value as Method)}
      >
        <option value="smallest_extent">Smallest extent</option>
        <option value="convex_hull">Convex hull</option>
      </select>

      {error && (
        <div className="upload-error" role="alert">
          {error}
        </div>
      )}

      <div className="upload-actions">
        <button
          type="button"
          className="button-primary"
          disabled={!isValid || submitting}
          onClick={handleSubmit}
        >
          {submitting ? (
            <>
              <span className="upload-spinner" aria-hidden="true" />
              Uploading&hellip;
            </>
          ) : (
            'Upload & Run'
          )}
        </button>
      </div>
    </div>
  );
}

export default UploadStep;
```

- [ ] **Step 3: Replace RunningStep.tsx**

```tsx
// reactapp/src/RunningStep.tsx
interface RunningStepProps {
  jobId: number | null;
  onNext: () => void;
  onBack: () => void;
}

function RunningStep({ jobId, onNext, onBack }: RunningStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Running</h2>
      <p>
        Evaluation running&hellip;
        {jobId !== null && ` (Job #${jobId})`}
      </p>
      {/* TODO(FE4): replace temporary dev nav with real status-poll transition */}
      <div className="dev-nav">
        <button className="btn-back" onClick={onBack}>&larr; Back</button>
        <button className="button-primary" onClick={onNext}>Next &rarr;</button>
      </div>
    </div>
  );
}

export default RunningStep;
```

- [ ] **Step 4: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS. (`.upload-error` / `.upload-spinner` CSS classes don't exist yet — Task 5 adds them; CSS is not type-checked, so this still passes.)

---

### Task 5: Frontend — error banner + spinner styles

**Files:**
- Modify: `reactapp/src/UploadStep.css`

- [ ] **Step 1: Append the styles**

Add at the end of `reactapp/src/UploadStep.css`:

```css
/* Error banner (shown when submit fails) */
.upload-error {
  background: #FDECEC;
  color: var(--color-error);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  padding: 0.6rem 0.8rem;
  font-size: 0.82rem;
  margin-bottom: 1rem;
}

/* Inline button spinner (shown while submitting) */
.upload-spinner {
  display: inline-block;
  width: 0.8rem;
  height: 0.8rem;
  margin-right: 0.45rem;
  vertical-align: -0.1rem;
  border: 2px solid rgba(255, 255, 255, 0.5);
  border-top-color: #fff;
  border-radius: 50%;
  animation: upload-spin 0.6s linear infinite;
}
@keyframes upload-spin {
  to {
    transform: rotate(360deg);
  }
}
```

- [ ] **Step 2: Type-check, lint, build**

Run: `cd reactapp && npx tsc -b && npm run lint && npm run build`
Expected: all PASS (build confirms the bundle is clean).

---

### Task 6: Verify and commit (await user go-ahead)

**Files:** none (verification + git)

- [ ] **Step 1: Full backend + frontend gates**

Run:
```bash
cd /home/rragh/tethysdev/tethysapp-fimeval-gui && tethys manage test tethysapp/fimeval_gui/tests
cd reactapp && npx tsc -b && npm run lint && npm run build
```
Expected: backend all pass (61 tests); frontend tsc/lint/build clean.

- [ ] **Step 2: Manual browser walkthrough**

Prereq: Tethys (`:8000`), Dask scheduler + worker, and MinIO all running; user logged into Tethys.
Run: `cd reactapp && npm run dev` → open http://localhost:5173

- Open DevTools → Application → Cookies; confirm a `csrftoken` cookie is present (seeded by the on-mount `ensureCsrf`).
- Select a benchmark `.tif` + one or more candidate `.tif`s, pick a method, click "Upload & Run":
  - Button shows the spinner + "Uploading…" and is disabled during the requests.
  - On success, the wizard advances to the Running step and shows "Evaluation running… (Job #<id>)".
- Trigger a failure (e.g. stop MinIO, then submit): a red error banner appears above the button with the backend message, and the wizard stays on Upload. The button re-enables.
- (Optional) Verify in MinIO that `uploads/<user>/<upload_id>/benchmark.tif` + candidates were written, and a job was created.

Report results to the user and **wait for go-ahead before committing.**

- [ ] **Step 3: Commit (only after user approval)**

```bash
git add .
git commit -m "feat: FIMEVAL-FE3 wire upload + submit to the backend

Add api/csrf endpoint (@ensure_csrf_cookie) + test, and a shared src/api.ts
client (getCsrfToken/ensureCsrf/uploadFiles/submitJob). UploadStep now chains
upload then submit with an in-flight spinner and a red error banner, and
reports the new job id up to App, which advances to the Running step (now
showing the job id). App seeds the CSRF cookie on mount.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Push (only after user approval)**

```bash
git push
```

---

## Self-Review

**Spec coverage** (against `2026-06-08-fimeval-fe3-upload-submit-integration-design.md`):
- `api_csrf` controller, route `api/csrf`, `login_required=False`, GET-only/405, `@ensure_csrf_cookie`, returns `{detail}` → Task 1 ✓
- Decorator order (`@controller` outer, `@ensure_csrf_cookie` inner) → Task 1 ✓
- `TestCsrfEndpoint` (GET→200 + cookie; POST→405) → Task 2 ✓
- `api.ts`: `API_BASE`, `getCsrfToken`, `ensureCsrf` (swallow errors), `uploadFiles` (multipart, X-CSRFToken), `submitJob` (JSON, Content-Type + X-CSRFToken), `credentials: same-origin`, `parseError` surfacing `body.error`, `UploadResult`/`SubmitResult` types → Task 3 ✓
- `App.tsx`: `ensureCsrf` on mount, `jobId` state, `onJobCreated` advances, passes props → Task 4 ✓
- `UploadStep.tsx`: prop `onJobCreated`, `submitting`/`error` state, chained handler, disabled/spinner button, red error banner → Task 4 ✓
- `RunningStep.tsx`: `jobId` prop displayed, keeps dev nav → Task 4 ✓
- `UploadStep.css`: error banner + spinner → Task 5 ✓
- Error handling surfaces backend message, never advances on error, clears `submitting` in `finally` → Task 4 ✓
- Testing: backend test + frontend tsc/lint/build + manual → Tasks 2, 5, 6 ✓

**Placeholder scan:** No plan-placeholders. The `TODO(FE4)` in RunningStep is an intentional code marker for the throwaway dev nav.

**Type consistency:** `onJobCreated: (jobId: number) => void` defined in UploadStep (Task 4) matches `onJobCreated` in App (Task 4) and the `job_id: number` from `SubmitResult` (Task 3). `RunningStep` `jobId: number | null` matches App's `jobId` state type. `uploadFiles`/`submitJob` signatures (Task 3) match the call sites in UploadStep's `handleSubmit` (Task 4). Class names `upload-error`/`upload-spinner` used in Task 4 have matching rules in Task 5.

**Coupling note:** Task 4 intentionally bundles the three mutually-dependent component edits; per-file `tsc` between them would fail because the prop contracts change in lockstep.
