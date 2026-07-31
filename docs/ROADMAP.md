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

### Reliability & Observability — ✅ shipped (in review)

The 2026-07 investigation + demo fixes are done, in two stacked PRs:
- **PR #6** — **BE27** (surface fimeval failure cause), **BE28**
  (`PROJ_NETWORK=OFF`), **BE31** (pre-clip candidate to the benchmark extent —
  validated 4.6 GB → 0.5 GB peak, identical metrics).
- **PR #7** (stacked on #6) — **BE29** (no-hang timeout · bounded worker-death
  retries · pixel-budget input guard), **BE30** (persist + expose input
  metadata), **FE14** ("Input Files" disclosure).

Merge order **#6 → #7**. Follow-up: `/vsis3` range-read for the guard's benchmark
header (avoid downloading a huge benchmark just to reject it).

### GUI Expansion — the remaining GUI backlog *(FE14 shipped in PR #7)*

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
