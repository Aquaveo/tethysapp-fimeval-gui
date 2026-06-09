# FIMEVAL-FE3 — Upload + Submit API Integration

**Date:** 2026-06-08
**Status:** Approved, ready for implementation plan

## Goal

Wire the FE2 Upload form to the real backend. Clicking "Upload & Run" reads the
CSRF token, POSTs the files to the upload endpoint, POSTs the job to the submit
endpoint, and advances to the Running step carrying the returned `job_id`. A
small backend endpoint guarantees the CSRF cookie exists in any environment.

## Context

- FE1 built the three-step wizard shell (`App.tsx` owns `step`); FE2 built the
  Upload form (`UploadStep.tsx` holds `benchmark`, `candidates`, `method` and
  currently calls an `onNext` prop to advance).
- Backend endpoints already exist and work (login-required, JSON):
  - `POST /apps/fimeval-gui/api/upload/` — multipart, field `benchmark` (single)
    + `candidates` (repeated). Returns `{upload_id, benchmark_key, candidate_keys}`.
  - `POST /apps/fimeval-gui/api/jobs/` — JSON `{upload_id, method}`. Returns 202
    `{job_id, status: "submitted"}`. Errors return `{error: "..."}`.
- The Vite dev server (`:5173`) proxies `/apps` → `http://127.0.0.1:8000`.
- Brand theme is in place (cyan `#25C2DF`, Alan Sans, `theme.ts` / `styles/theme.css`).
- React 19 + TS strict + `verbatimModuleSyntax` + Vite. No component test framework.

## CSRF Strategy

Django's CSRF protection requires the `csrftoken` cookie in the browser and an
`X-CSRFToken` header on unsafe requests. The custom SPA `index.html` may not
trigger Django to set the cookie, and in Vite dev the page isn't served by Django
at all. To guarantee the cookie in every environment, add a dedicated endpoint
the SPA calls on mount.

## Backend Addition

### `controllers.py` — `api_csrf` controller
- Route `api/csrf`, name `api_csrf`, `login_required=False` (it only sets a
  non-sensitive cookie and must be seedable regardless of auth state), `GET` only.
- Decorated with Django's `@ensure_csrf_cookie` so the response sets `csrftoken`.
- Returns `JsonResponse({'detail': 'CSRF cookie set'})`.
- Non-GET returns 405, matching the other controllers' style.

### `tests/test_api.py` — `TestCsrfEndpoint`
- `GET /apps/fimeval-gui/api/csrf/` returns 200 and the response sets a
  `csrftoken` cookie (assert `'csrftoken' in response.cookies`).
- Non-GET (POST) returns 405.

## Frontend

### `src/api.ts` (new, shared module)
Centralizes all backend calls so FE4/FE5 can reuse them.

- `const API_BASE = '/apps/fimeval-gui/api'` — absolute path works in Vite dev
  (via proxy) and in production (app served under the same path).
- `getCsrfToken(): string` — parses `document.cookie` for `csrftoken`; returns
  `''` if absent.
- `ensureCsrf(): Promise<void>` — `GET ${API_BASE}/csrf/` with
  `credentials: 'same-origin'`; seeds the cookie. Errors are swallowed (best
  effort) — a later POST surfaces any real problem.
- `uploadFiles(benchmark: File, candidates: File[]): Promise<{ upload_id: string }>`
  — builds `FormData` (`benchmark`, then each `candidates`), `POST ${API_BASE}/upload/`
  with header `X-CSRFToken` and `credentials: 'same-origin'`. On non-OK, throws
  via the shared error helper.
- `submitJob(uploadId: string, method: string): Promise<{ job_id: number }>` —
  `POST ${API_BASE}/jobs/` with JSON body `{upload_id, method}`, headers
  `Content-Type: application/json` + `X-CSRFToken`, `credentials: 'same-origin'`.
  On non-OK, throws via the shared error helper.
- Internal helper `parseError(response): Promise<never>` — reads the JSON body,
  throws `new Error(body.error ?? 'Request failed')`.

Types (`UploadResult`, `SubmitResult`) are defined and used within `api.ts`. They
may be exported (it is not a component file, so `react-refresh/only-export-components`
does not apply).

### `src/App.tsx` (modified)
- On mount, `useEffect(() => { ensureCsrf(); }, [])` to seed the cookie.
- Add `const [jobId, setJobId] = useState<number | null>(null)`.
- Add `const onJobCreated = (id: number) => { setJobId(id); setStep('running'); }`.
- Render `<UploadStep onJobCreated={onJobCreated} />` (replaces `onNext`).
- Render `<RunningStep jobId={jobId} onNext={goNext} onBack={goBack} />`. (`jobId`
  is non-null by the time Running renders, but typed `number | null`; RunningStep
  guards/falls back if null.)

### `src/UploadStep.tsx` (modified)
- Prop changes: `{ onJobCreated: (jobId: number) => void }` (was `onNext`).
- New local state: `submitting: boolean`, `error: string | null`.
- Submit handler (on "Upload & Run" click, only reachable when valid):
  1. `setError(null); setSubmitting(true)`.
  2. `try { const { upload_id } = await uploadFiles(benchmark!, candidates);`
     `const { job_id } = await submitJob(upload_id, method); onJobCreated(job_id); }`
  3. `catch (e) { setError(e instanceof Error ? e.message : 'Upload failed. Please try again.'); }`
  4. `finally { setSubmitting(false); }`
- Button: `disabled={!isValid || submitting}`. While submitting, show a small
  spinner + "Uploading…" label inside the button; otherwise "Upload & Run".
- Error banner: when `error` is set, render a red banner above the action row with
  the message. It clears on the next submit attempt.

### `src/RunningStep.tsx` (modified)
- Add prop `jobId: number | null`.
- Display the job id, e.g. "Evaluation running… (Job #123)" when present.
- Keep the temporary dev nav (`onNext` / `onBack`) for now — FE4 replaces it with
  real status polling and the automatic Running→Results transition.

### `src/UploadStep.css` (modified)
- Styles for the error banner (red text/background tint, rounded) and the inline
  button spinner (a small CSS border-spinner animation).

## Data Flow

```
App (mount)            --ensureCsrf()-->  GET /api/csrf/   (seeds csrftoken cookie)
UploadStep "Upload&Run" --uploadFiles--> POST /api/upload/  -> { upload_id }
                        --submitJob----> POST /api/jobs/    -> { job_id }
                        --onJobCreated(job_id)--> App: setJobId + setStep('running')
App                    --jobId-->        RunningStep (displays it; FE4 polls)
```

## Error Handling

- `uploadFiles` / `submitJob` throw `Error(body.error)` on non-OK, surfacing the
  backend message (e.g. "storage unavailable", "upload_id not found"); generic
  fallback "Upload failed. Please try again." when no message is available.
- Any error sets the `UploadStep` error banner and leaves the user on the Upload
  step (no advance). `submitting` is always cleared in `finally`.

## Out of Scope

- Status polling and the Running→Results auto-transition — FE4.
- Results display (metrics, downloads) — FE5.
- Job cancellation, retry, or re-submit flows.
- Upload progress percentage (only an indeterminate spinner).

## Testing

- **Backend:** `TestCsrfEndpoint` added to `tests/test_api.py` (GET → 200 + sets
  cookie; POST → 405). Run with the existing suite:
  `tethys manage test tethysapp/fimeval_gui/tests`.
- **Frontend:** `npx tsc -b` + `npm run lint` + manual browser walkthrough
  (consistent with FE1/FE2; no component test framework). `api.ts` is structured
  to be unit-testable later.
- **Manual walkthrough (Vite dev against a running Tethys + Dask + MinIO):**
  - Load the app; confirm a `csrftoken` cookie is set (DevTools → Application).
  - Select a benchmark + candidate(s), pick a method, click "Upload & Run":
    button shows a spinner/"Uploading…"; on success the wizard advances to Running
    and shows the job id.
  - Force an error (e.g. stop MinIO) and confirm the red error banner appears with
    a useful message and the wizard stays on Upload.
