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

#### FIMEVAL-FE3 — Upload + Submit API Integration
`getCsrfToken()` cookie helper, chain `POST /api/upload/` → `POST /api/jobs/`, CSRF header, spinner, advance to step 2 on success. Worst case: **3 hours**.

#### FIMEVAL-FE4 — Running Step + Status Polling
Poll `GET /api/jobs/{job_id}/` every 3s with `setInterval` in `useEffect`. On `complete` → step 3. On `error` → show message + "Start Over". Worst case: **2 hours**.

#### FIMEVAL-FE5 — Results Step (Metrics + Downloads)
Fetch `GET /api/jobs/{job_id}/outputs/` on mount. Render file list with Download buttons pointing to `GET /api/jobs/{job_id}/download/?file={key}`. "Start New Evaluation" reset button. Worst case: **2.5 hours**.

#### FIMEVAL-FE6 — Production Build + Tethys Serving
`npm run build` → verify output in `public/frontend/` → end-to-end browser test. Worst case: **1.5 hours**.

**Total worst-case frontend: ~12.5 hours.**

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
