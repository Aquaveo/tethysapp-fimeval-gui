# FIMEVAL-FE4 — Running Step + Status Polling

**Date:** 2026-06-08
**Status:** Approved, ready for implementation plan

## Goal

Turn the Running step from a placeholder into a live status poller. On mount it
polls the job status endpoint; while the job runs it shows a spinner; when the
job completes it auto-advances to Results; if the job errors it shows an error
with a "Start Over" control. Polling is cleaned up on unmount.

## Context

- FE1–FE3 built the wizard shell, the Upload form, and the upload+submit
  integration. `App.tsx` owns `step` and `jobId`; after a successful submit it
  sets `jobId` and advances to the Running step.
- `RunningStep.tsx` is currently a placeholder showing "Evaluation running…
  (Job #N)" with temporary dev nav buttons.
- `src/api.ts` (FE3) exports `getCsrfToken`, `ensureCsrf`, `uploadFiles`,
  `submitJob`, plus the `parseError` helper.
- Backend `GET /apps/fimeval-gui/api/jobs/{job_id}/` (login-required) returns
  `{job_id, status, created, completed, method, upload_id}` where `status` is one
  of `submitted | running | complete | error`. It cross-checks MinIO, so it
  reports `complete` once outputs land even though the dev job monitor does not
  tick.
- Brand theme in place (cyan `#25C2DF`, Alan Sans). React 19 + TS strict +
  `verbatimModuleSyntax` + Vite. No component test framework.

## Decisions

- **Polling mechanism:** recursive `setTimeout` — schedule the next poll only
  after the current response returns, so slow responses never overlap.
- **Poll-request failures:** tolerated. A network blip / 5xx on the status
  request is swallowed and polling continues. Only a job that returns
  `status: 'error'` shows the error screen.

## `api.ts` Addition

```ts
export interface JobStatus {
  job_id: number;
  status: 'submitted' | 'running' | 'complete' | 'error';
  created: string | null;
  completed: string | null;
  method: string | null;
  upload_id: string | null;
}

export async function getJobStatus(jobId: number): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}
```

- GET needs no CSRF token. `credentials: 'same-origin'` sends the session cookie.

## `RunningStep.tsx` (rewrite)

- **Props:** `{ jobId: number; onComplete: () => void; onReset: () => void }`
  (drops the FE1/FE3 `onNext` / `onBack`).
- **State:** `errored: boolean`.
- **Polling effect** — one `useEffect` with deps `[jobId, onComplete]`:
  - Closure vars: `let cancelled = false;` and a `timeout` handle.
  - `poll()`:
    1. `try { const s = await getJobStatus(jobId); }` — on throw, if `cancelled`
       return, else schedule the next poll (tolerate transient failures).
    2. After a successful response, if `cancelled` return.
    3. `s.status === 'complete'` → `onComplete()` and stop (no reschedule).
    4. `s.status === 'error'` → `setErrored(true)` and stop.
    5. otherwise (`submitted` / `running`) → `timeout = setTimeout(poll, 3000)`.
  - Kick off `poll()` immediately on mount (fast first result; 3s gap between
    subsequent polls).
  - **Cleanup:** `cancelled = true; clearTimeout(timeout);` — prevents leaks and
    any state update / `onComplete` after unmount.
- **Render:**
  - Not errored: a centered spinner + "Evaluation in progress…" and "(Job #N)".
  - Errored: a red error message ("The evaluation failed.") + a "Start Over"
    button wired to `onReset` (uses `.button-primary`).

## `RunningStep.css` (new, co-located)

Centered, larger cyan spinner (border-spinner like the FE3 button spinner but
sized ~2.5rem with a `var(--color-primary)` top border), progress text, error
text, and layout. "Start Over" reuses the shared `.button-primary` class.

## `App.tsx` Changes

- Wrap the two transitions in `useCallback` (stable identities keep the poll
  effect from restarting on every render):
  - `const onComplete = useCallback(() => setStep('results'), []);`
  - `const onReset = useCallback(() => { setStep('upload'); setJobId(null); }, []);`
  - (`setStep` / `setJobId` from `useState` are stable, so `[]` deps are correct.)
- Render the Running step with a null-guard that narrows `jobId` to `number`:
  - `{step === 'running' && jobId !== null && (`
    `  <RunningStep jobId={jobId} onComplete={onComplete} onReset={onReset} />`
    `)}`
- Remove `goNext` (now unused — would fail `noUnusedLocals`). Keep `goBack`,
  `index`, and the `STEP_ORDER` import — `ResultsStep` still uses `goBack` as dev
  nav until FE5.

## Data Flow

```
App → RunningStep(jobId, onComplete, onReset)
RunningStep poll loop → getJobStatus(jobId) every ~3s (recursive setTimeout)
  status complete → onComplete() → App: setStep('results')
  status error    → local error screen → "Start Over" → onReset() → setStep('upload'), setJobId(null)
  request throws  → swallow, keep polling
unmount → cancelled = true; clearTimeout(...)
```

## Out of Scope

- Results step content — metrics table, downloads (FE5).
- Elapsed-time display or progress percentage (indeterminate spinner only).
- Job cancellation.
- Retry of a failed job (Start Over restarts the whole wizard).

## Testing

Consistent with FE1–FE3:
- `npx tsc -b` + `npm run lint`.
- Manual (Vite dev against running Tethys + Dask + MinIO, logged in):
  - Submit a job from the Upload step; the wizard advances to Running and shows
    the spinner + "Evaluation in progress… (Job #N)".
  - When the fimeval outputs land in MinIO, the next poll reports `complete` and
    the wizard auto-advances to the Results step.
  - Navigate away (Start Over once available, or reload) mid-poll and confirm via
    the network tab that polling stops (no further `jobs/{id}/` requests).
  - The `error` path is harder to force in dev; the code path is simple and
    covered by reading the status branch.
