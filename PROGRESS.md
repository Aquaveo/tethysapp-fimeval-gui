# FIMeval GUI — Session Progress

## What's Done

### Backend API (FIMEVAL-BE) — Complete ✅

All 7 backend tasks are implemented, tested (59 tests passing), committed, and pushed to `main`.

| Task | Commit | Description |
|------|--------|-------------|
| FIMEVAL-1 | `0555a9b` | S3 storage wrapper (`storage.py`) |
| FIMEVAL-2 | `21c62e4` | Job type registry + `evaluate_fim` Dask task |
| FIMEVAL-3 | `d79c2bf` | Upload endpoint `POST /api/upload/` |
| FIMEVAL-4 | `408d34b` | Submit endpoint `POST /api/jobs/` |
| FIMEVAL-5 | `056039d` | Scheduler settings in `app.py` |
| FIMEVAL-6 | `935e2ba` | Status endpoint `GET /api/jobs/{job_id}/` |
| FIMEVAL-7 | `9677424` | Outputs endpoint `GET /api/jobs/{job_id}/outputs/` |
| FIMEVAL-8 | `a73794b` | Download endpoint `GET /api/jobs/{job_id}/download/` |
| Spec gaps | `6e456ba` | 403 cross-user, Complete guards, presigned URL redirect, richer status response |

### Key architecture notes

- **S3 keys**: bucket-relative (no `fimeval/` prefix). Pattern: `uploads/{user_id}/{upload_id}/` and `outputs/{user_id}/{upload_id}/`
- **Status endpoint**: checks Dask live status → falls back to Tethys DB status → MinIO cross-check if still "running" (handles ephemeral Dask futures)
- **Download**: 303 redirect to presigned MinIO URL (1-hour expiry). `file` param is the full S3 key.
- **Complete guard**: `job._status == 'COM'`. In dev, the Tethys job monitor doesn't tick, so `_status` stays `'SUB'` even after completion. Workaround: `tethys manage shell -c "from tethys_sdk.jobs import DaskJob; j = DaskJob.objects.latest('id'); j._status = 'COM'; j.save()"`
- **Tests**: 59 total across `test_storage.py`, `test_job_types.py`, `test_api.py`. All use moto (no real S3 calls).

---

## What's Next

### Frontend React SPA (FIMEVAL-FE) — Pending ⏳

Demo target: **Thursday 2026-06-11** (was set when this was written; confirm date is still valid).

All 6 frontend tasks are ready to start. Backend API is fully functional.

#### FIMEVAL-FE1 — App Shell + Three-Step Layout ✅ Done
Scaffold replaced with `App.tsx` (`step` state), `Stepper`, and placeholder Upload/Running/Results steps with temporary dev nav. Brand theme added: `theme.ts` (inline-style tokens), `styles/theme.css` (CSS vars + `.button-primary`), Alan Sans font, cyan/green/pale-cyan palette wired into the stepper and cards. Spec at `docs/superpowers/specs/2026-06-08-fimeval-fe1-app-shell-design.md`, plan at `docs/superpowers/plans/2026-06-08-fimeval-fe1-app-shell.md`.

#### FIMEVAL-FE2 — Upload Step UI ✅ Done
Reusable `Dropzone` (drag/drop/browse, `.tif`/`.tiff` extension filtering, keyboard-accessible, owns its rejection message) + rewritten `UploadStep`: benchmark + candidate pickers, removable candidate chips with green ✓ accept ticks, red inline reject error, method dropdown, and a validity-gated "Upload & Run" button (calls `onNext` to advance — FE3 swaps in the real upload+submit). Co-located `Dropzone.css` / `UploadStep.css`. Spec at `docs/superpowers/specs/2026-06-08-fimeval-fe2-upload-step-design.md`, plan at `docs/superpowers/plans/2026-06-08-fimeval-fe2-upload-step.md`.

#### FIMEVAL-FE3 — Upload + Submit API Integration ✅ Done
Added `GET /api/csrf/` endpoint (`@ensure_csrf_cookie`) + test (61 backend tests pass). New shared `src/api.ts` (`getCsrfToken`/`ensureCsrf`/`uploadFiles`/`submitJob`, absolute `/apps/fimeval-gui/api` paths, `X-CSRFToken`, `credentials:'same-origin'`, error helper surfacing backend `{error}`). `App` seeds CSRF on mount, holds `jobId`, `onJobCreated` advances to Running. `UploadStep` chains upload→submit with in-flight spinner + red error banner. `RunningStep` displays the job id. Spec at `docs/superpowers/specs/2026-06-08-fimeval-fe3-upload-submit-integration-design.md`, plan at `docs/superpowers/plans/2026-06-08-fimeval-fe3-upload-submit-integration.md`.

#### FIMEVAL-FE4 — Running Step + Status Polling
Poll `GET /api/jobs/{job_id}/` every 3s with `setInterval` in `useEffect`. On `complete` → step 3. On `error` → show message + "Start Over". Worst case: **2 hours**.

#### FIMEVAL-FE5 — Results Step (Metrics + Downloads)
Fetch `GET /api/jobs/{job_id}/outputs/` on mount. Render file list with Download buttons pointing to `GET /api/jobs/{job_id}/download/?file={key}`. "Start New Evaluation" reset button. Worst case: **2.5 hours**.

#### FIMEVAL-FE6 — Production Build + Tethys Serving
`npm run build` → verify output in `public/frontend/` → end-to-end browser test. Worst case: **1.5 hours**.

**Total worst-case frontend: ~12.5 hours.**

---

## Known Follow-Ups / Tech Debt (beyond current MVP scope)

Surfaced 2026-06-09 while manually testing FE3/FE4 with real tier data.

### 1. Pipeline target CRS — ✅ addressed (default), UI selector still a follow-up
`run_evaluate_fim_task` originally called `fimeval.EvaluateFIM(main_dir, method, output_dir)` with **no** `target_crs`. fimeval's `MakeFIMsUniform` (in `fimeval/utilis.py`) auto-reprojects mixed/geographic CRS to `EPSG:5070` **only when every input passes its `is_within_conus(bounds, crs)` check**; otherwise it prints `"Mixed or non-CONUS CRS detected. Please provide a valid target CRS."` and returns without writing anything. If `target_crs` **is** passed, it skips the `is_within_conus` gate and reprojects everything to it.
- **Symptom seen:** a benchmark in WGS 84 (EPSG:4326) / UTM 18N + a candidate in Conus Albers (EPSG:5070) → fimeval bailed, no outputs. (Files uploaded fine — confirmed valid via `gdalinfo`; not an upload bug. Same pipeline runs for curl and UI uploads.)
- **Done:** the worker now passes a default `target_crs='EPSG:5070'` (constant `TARGET_CRS` in `job_types/evaluate_fim.py`), so mixed/non-CONUS inputs reproject instead of bailing.
- **Still a follow-up:** surface the target CRS as a user-selectable option in the Upload UI rather than hardcoding CONUS Albers (matters for non-CONUS study areas).

### 2. "Finished-but-no-outputs" job spins forever in the UI
When fimeval bails (as in #1) the Dask task returns normally — **no exception**. So the job neither errors (the Tethys job monitor doesn't tick in dev, and nothing raised) nor completes (no outputs land for the status endpoint's MinIO cross-check). The FE4 poll loop therefore polls indefinitely with the spinner up.
- **Fix direction:** make a no-output run terminal — e.g. the worker raises if `EvaluateFIM`/`MakeFIMsUniform` produced no outputs, and/or the status endpoint treats a finished-future-with-no-outputs (or a poll timeout) as `error` so FE4 can show the failure screen.

---

## Dev Environment Quick Reference

| Service | Port | Start command |
|---------|------|---------------|
| Tethys/Django | 8000 | `tethys manage start` |
| Vite dev server | 5173 | `cd reactapp && npm run dev` |
| MinIO | 9000 | (starts separately) |
| Dask scheduler | 8786 | (starts separately) |

Run tests: `tethys manage test tethysapp/fimeval_gui/tests`

Frontend build: `cd reactapp && npm run build`
