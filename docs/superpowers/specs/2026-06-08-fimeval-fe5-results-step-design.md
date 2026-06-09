# FIMEVAL-FE5 — Results Step (metrics + downloads)

**Date:** 2026-06-08
**Status:** Approved, ready for implementation plan

## Goal

Turn the Results step from the FE1 placeholder into the payoff screen: on mount
it loads the job's evaluation metrics and output files, renders a metrics table
(headline CSI/POD/FAR cards + full table) and a download list, and offers a
"Start New Evaluation" reset. Two backend changes support it.

## Context

- FE1–FE4 built the wizard, Upload form, upload+submit integration, and the
  Running step's status polling (which auto-advances to Results on `complete`).
- `App.tsx` owns `step` + `jobId` and a `useCallback`-stable `onReset` (from FE4).
  It currently passes `onBack={goBack}` to `ResultsStep` (FE1 dev nav).
- `src/api.ts` has `getCsrfToken` / `ensureCsrf` / `uploadFiles` / `submitJob` /
  `getJobStatus`, plus `parseError` and `API_BASE`.
- Existing backend endpoints:
  - `GET /api/jobs/{job_id}/outputs/` → `{job_id, files: [{name, key}]}`.
  - `GET /api/jobs/{job_id}/download/?file={key}` → 303 redirect to a presigned
    MinIO URL (1h).
  - Both currently return **400** when `job._status != 'COM'`.
- **Dev quirk:** the Tethys job monitor doesn't tick, so `_status` stays `'SUB'`
  even after a job completes. The status endpoint already works around this with
  a MinIO cross-check (outputs-present ⇒ complete); the outputs/download
  endpoints do **not**, so they 400 in dev right when FE5 needs them.
- `EvaluationMetrics.csv` format (confirmed from a real run):
  ```
  Metrics,candidate_0
  CSI_values,0.3656507191183279
  TN_values,4992447.0
  ...
  FAR_values,0.4182017683549446
  ```
  Column 1 is `<MetricName>_values`; each remaining column is a candidate.
- Brand theme in place (cyan `#25C2DF`, Alan Sans loaded globally, co-located CSS
  per component). React 19 + TS strict + `verbatimModuleSyntax` + Vite. No
  frontend component test framework; backend has a real suite (`tethys manage test`).

## Backend Changes

### 1. Relax the Complete guard on outputs + download (align with status endpoint)

The authoritative completion signal across the app is "outputs landed in MinIO"
(what the status endpoint uses). Make outputs/download consistent:

- **`api_job_outputs`**: remove the `job._status != 'COM' → 400` guard. Keep the
  existing flow: reconstruct the prefix from `extended_properties`, `list_prefix`,
  and return `files` if present, else `404 {'error': 'no outputs yet'}`. (Ownership
  403 and 503-on-storage-error unchanged.)
- **`api_job_download`**: remove the `job._status != 'COM' → 400` guard. Keep the
  prefix-scope check (403 if `file` is outside the job's `outputs/{user}/{upload}/`
  prefix) and `key_exists` (404 if missing). 303 redirect to presigned URL unchanged.
- **Tests:** update the existing `TestOutputsEndpoint` / `TestDownloadEndpoint`
  cases that asserted **400 when not complete** — they should reflect the new
  behavior (a `RUN`/`SUB` job with outputs present returns them / redirects; a job
  with no outputs returns 404). Ownership-403 and missing-file-404 tests stay.

### 2. New metrics endpoint — `GET /api/jobs/{job_id}/metrics/`

- Route `api/jobs/{job_id}/metrics`, name `api_job_metrics`, `login_required=True`,
  GET only (405 otherwise).
- Look up `DaskJob.objects.get(id=job_id)` → 404 if missing; `job.user != request.user`
  → 403.
- Build the output prefix from `extended_properties` (`user_id`, `upload_id`);
  `list_prefix` and find the key whose basename is `EvaluationMetrics.csv`. If none
  → `404 {'error': 'metrics not available yet'}`.
- `get_object` that key, decode, parse with the `csv` module:
  - Header row: `['Metrics', <candidate columns...>]` → `candidates` = columns[1:].
  - Each data row: `['<Metric>_values', <value per candidate...>]`. Strip the
    trailing `_values` to get the metric name. Parse values as floats.
  - Return `JsonResponse({'job_id': job.id, 'candidates': [...], 'metrics': [{'metric': 'CSI', 'values': {'candidate_0': 0.3656...}}, ...]})`.
- Storage errors (`ClientError`/`BotoCoreError`) → 503.
- **Tests:** `TestMetricsEndpoint` — parses a seeded `EvaluationMetrics.csv` from
  (mocked) MinIO and returns the expected JSON; 404 when the CSV is absent; 403 for
  another user's job; 405 on non-GET.

## Frontend Changes

### `src/api.ts` (additions)
```ts
export interface OutputFile { name: string; key: string; }
export interface JobOutputs { job_id: number; files: OutputFile[]; }

export interface MetricRow { metric: string; values: Record<string, number>; }
export interface JobMetrics { job_id: number; candidates: string[]; metrics: MetricRow[]; }

export async function getJobOutputs(jobId: number): Promise<JobOutputs> { /* GET .../outputs/ */ }
export async function getJobMetrics(jobId: number): Promise<JobMetrics> { /* GET .../metrics/ */ }

// Anchor href target; the browser follows the 303 → presigned URL (no CORS issue
// because it's a navigation/download, not a JS body read).
export function downloadUrl(jobId: number, key: string): string {
  return `${API_BASE}/jobs/${jobId}/download/?file=${encodeURIComponent(key)}`;
}
```
`getJobOutputs` / `getJobMetrics` use `credentials: 'same-origin'`, non-OK → `parseError`.

### `src/ResultsStep.tsx` (rewrite)
- **Props:** `{ jobId: number; onReset: () => void }` (replaces `onBack`).
- **State:** `status: 'loading' | 'ready' | 'error'`, `outputs: OutputFile[]`,
  `metrics: JobMetrics | null`, `errorMsg: string`.
- **On mount** (`useEffect`, dep `[jobId]`): load outputs + metrics. Because FE4
  only advances on `complete` (outputs exist), both should be ready — but to cover
  the rare race where the listing lags, if outputs come back empty / 404, show
  "Waiting for outputs…" and **retry once after 2s**; if still empty, show error.
  Metrics 404 is tolerated (table simply omitted) so a run lacking a metrics CSV
  still shows downloads. Use a `cancelled` flag for cleanup.
- **Render** (centered wrapper, `max-width: 75vw`):
  - Header: "Evaluation Results" + `Job #{jobId}` (+ method/candidate if available).
  - Headline metric cards: CSI / POD / FAR (CSI in brand cyan), pulled from the
    first candidate's values (omit a card if that metric is absent).
  - Full metrics table: one row per metric, one value column per candidate; ratios
    formatted to 4 decimals, integer-valued counts shown as integers.
  - Download list: one row per `OutputFile` — name + a Download control rendered as
    `<a href={downloadUrl(jobId, file.key)} download>` (styled like `.button-primary`).
  - "Start New Evaluation" button → `onReset`.
- **Error state:** a message + a "Start Over" button (`onReset`).

### `src/ResultsStep.css` (new, co-located)
Centered `max-width: 75vw; margin: 0 auto` wrapper; headline stat cards; metrics
table (theme tokens, zebra rows); download rows; "Start New Evaluation" via the
shared `.button-primary`. Font inherited (Alan Sans).

### `src/App.tsx`
- Render `{step === 'results' && jobId !== null && <ResultsStep jobId={jobId} onReset={onReset} />}`.
- Remove `goBack` and `index` (now unused) and the now-unused `STEP_ORDER` import.
  Keep `type Step` (used by `useState`). This is a coupled App+ResultsStep change.

## Data Flow

```
App → ResultsStep(jobId, onReset)
mount → getJobOutputs(jobId) + getJobMetrics(jobId)
  → headline cards + table (metrics) + download list (outputs)
download click → <a> → GET /api/jobs/{id}/download/?file={key} → 303 → presigned MinIO URL
Start New Evaluation → onReset() → setStep('upload'); setJobId(null)
```

## Error Handling

- Outputs empty/404 on first try → "Waiting for outputs…", retry once after 2s →
  then error if still empty.
- Metrics 404 → omit the table/cards, still show downloads (graceful partial).
- Any hard fetch error → error state + "Start Over".
- A `cancelled` flag prevents state updates after unmount.

## Out of Scope

- In-app map / raster preview of the contingency or clipped TIFs (download only).
- Special multi-candidate styling (the table supports N candidates generically).
- Sorting/filtering the file list.
- FE6: production build + Tethys serving verification.

## Testing

- **Backend:** `TestMetricsEndpoint` added; `TestOutputsEndpoint` /
  `TestDownloadEndpoint` updated for the relaxed guard. Run `tethys manage test
  tethysapp/fimeval_gui/tests`.
- **Frontend:** `npx tsc -b` + `npm run lint` + `npm run build`.
- **Manual end-to-end** (Tethys + Dask + MinIO, logged in): run an evaluation;
  when it auto-advances to Results, confirm the headline cards + full metrics
  table match `EvaluationMetrics.csv`, every output file downloads, and
  "Start New Evaluation" returns to a fresh Upload step.
