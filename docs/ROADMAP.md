# FIMeval GUI — Project Board

Multi-user web app to run the FIMeval flood-inundation evaluation framework
entirely in-browser (no local Python). Users upload benchmark + candidate
rasters, pick a method, submit to a distributed Dask backend, and explore
results. Tethys 4 (Django) + React/TypeScript SPA; async jobs via Tethys DaskJob
on a Dask Distributed cluster; files in S3-compatible storage (MinIO dev /
AWS S3 prod).

## 🏁 Completed

- Tethys 4 + React/Vite SPA scaffold (served at `/apps/fimeval-gui/`); `home`
  controller with `catch_all=True`
- MinIO tile-proxy controller; Vite dev proxy (`/apps` → :8000)
- S3/MinIO creds + Dask scheduler wired as Tethys app settings; deps added
  (boto3, moto[s3], dask[distributed])
- **Backend REST API slice** — S3 storage wrapper, pluggable job-type registry +
  `EvaluateFIM` job type, full job lifecycle endpoints
  (upload → submit → status → outputs → download)
- **Presigned uploads** — browser PUTs straight to object storage (bypasses the
  app server; SigV4-signed) *(PR #4)*
- **FIMeval on Dask Distributed** — dev scheduler + worker; **bounded worker
  pool** with configurable limits (`start_worker.sh`) + **worker-sizing guide**
  *(PR #5)*
- **Per-user workspace isolation** — inputs/outputs scoped to
  `<user_id>/<upload_id>/` in S3
- **File-size limits / upload validation** (per-file cap, max candidates,
  extension checks)
- **Guided submission workflow** — upload → method picker → submit → progress
  polling
- **All 5 evaluation methods** live: smallest_extent, convex_hull, intersection,
  bootstrap, AOI (shapefile upload)
- **Results page (Version B)** — headline metric cards (CSI/POD/FAR), full
  metrics table, bootstrap box plots, download-all + per-file downloads
- Error boundary + basic error/loading states
- Local MinIO + `fimeval` bucket

## ⏳ In Progress

- Measurement + reliability hardening pass (see reliability tickets below)
- Removing temporary run-timing instrumentation before merge

## 🔜 To Do

### Reliability & Observability *(from the 2026-07 investigation)*

- **BE27** — Surface fimeval failure cause: capture `EvaluateFIM` stdout →
  `_FAILED` marker + job status + UI; `PYTHONUNBUFFERED=1` in worker *(~1.5 d)*
- **BE28** — Set `PROJ_NETWORK=OFF` in the worker (removes an unneeded transient
  failure trigger) *(~0.5 d)*
- **BE29** — OOM-killed jobs currently hang the UI 5+ min: emit a terminal error
  on worker death (bound retries, wall-clock timeout, harden status endpoint) +
  input guard (reject identical benchmark/candidate; pixel-budget check) *(~4 d)*
- **BE30** — Persist original filenames + read resolution/CRS at submit
  (+ shapefile CRS for AOI); expose via `api_job_status` `inputs`
  *(~2 d; blocks FE14)*
- **BE31** — Pre-clip candidate raster to the evaluation extent before fimeval
  (windowed read + bbox reproject across CRS) — the *real* fix for the 300–377 Mpx
  candidate OOM / memory-pressure failures seen in the 2026-07-30 demo *(~2–3 d)*
- **FE14** — "Input Files ▶" collapsible in the run window showing
  name · resolution · CRS per input (+ boundary shapefile for AOI)
  *(~1 d; needs BE30)*

### GUI Expansion

- **FE15 — Interactive contingency map viewer** *(= roadmap "Version A")*:
  MapLibre overlay of the TP/FP/FN/TN raster with legend, basemap,
  benchmark/candidate toggle; backend serves the contingency GeoTIFF as
  tiles/COG *(~5–6 d)*
- **FE16 — Inline plot/PNG previews** in results (contingency + metric plots,
  lightbox); backend must enable plot generation (`plot_metrics` /
  `PrintContingencyMap`, currently off) *(~1.5–2 d)*
- **FE17 — Job history list** — user's past runs (method, status, timestamp,
  link to results); backend "list my jobs" endpoint *(~3 d)*
- **FE18 — Evaluation parameters panel** — expose bootstrap
  `sub_method`/`n_iterations`/`n_points` + target resolution in the submit UI
  (currently hardcoded) *(~2–3 d)*
- Error states & loading skeletons — polish pass throughout

### Backend / Ops

- Output retention / cleanup policy for old job artifacts (**BE26**, drafted)
- Auth model decision: Tethys default vs SSO

### Testing & Hardening

- Integration tests against real MinIO (not just moto)
- Load-test Dask job submission under concurrent users
- Security audit: upload validation, presigned-URL expiry, per-user S3 key
  isolation

## 🚏 Future Modules (Post-MVP)

- **v3** — Multi-case-study uploads (directory-of-folders structure)
- **v5** — EvaluationWithBuildingFootprint (Microsoft BF default + user-supplied
  option)
- **v6** — benchFIMquery catalog browser (skip uploading a benchmark)
- *Done since original roadmap:* AOI (was v2), bootstrap sub-methods (was v7),
  intersection. **Interactive map (was "Version A") promoted to active backlog
  as FE15.**
