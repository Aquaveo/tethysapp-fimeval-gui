# FIMeval GUI — Initial Proposal

> Captured from a brainstorming session between rragh and Claude. This is a pre-design
> overview to share with stakeholders; it is **not** a finalized spec. Final design and
> implementation plan will be drafted once outstanding decisions are resolved.

## 1. What FIMeval Does (Recap)

FIMeval is a Python package that automates the evaluation of Flood Inundation Maps (FIMs).
A typical user workflow:

1. **Provides inputs** — a "main directory" containing one or more case-study folders,
   each holding a benchmark raster (filename includes the word `benchmark`) and one or
   more candidate model rasters. Optional inputs: permanent water bodies (PWB) vector,
   building footprint vector, AOI vector, target CRS/resolution.
2. **Picks an evaluation method** — `smallest_extent`, `convex_hull`, `AOI`,
   `intersected_extent`, or `bootstrap`.
3. **Runs four modules in sequence**:
   - `EvaluateFIM` → contingency rasters + `EvaluationMetrics.csv` (CSI, POD, FAR, F1,
     accuracy, etc.)
   - `PrintContingencyMap` → styled PNG per case study
   - `PlotEvaluationMetrics` → bar charts of metrics
   - `EvaluationWithBuildingFootprint` → building-level metrics + plots (Microsoft global
     BF by default, or user-supplied)
4. **Also has** `benchFIMquery` for pulling benchmark FIMs from a catalog, and a
   bootstrap sampler.

Today this is driven from a notebook (`fp.EvaluateFIM(main_dir, method, output_dir, ...)`)
against local paths.

## 2. Decisions Already Made

| # | Question | Answer |
|---|----------|--------|
| 1 | Who runs this? | **Multi-user SaaS** |
| 2 | Where do inputs live? | **Uploaded through the browser** (frontend passes data to backend) |
| 3 | How are jobs executed? | **Async via Tethys's built-in `DaskJob` framework** (see below) |
| 4 | Scope | **Full FIMeval surface, built module-by-module**, starting with the simplest case. Must be robust & scalable, not a house of cards. |
| 5 | Results UX | **Pending boss approval** — two options compared below |

## 3. Proposed Webapp Shape

A Tethys 4 app (Django) hosting a React SPA, mirroring the `fimbench-gui` pattern but
with one major addition: **FIMeval needs to actually run**, while fimbench-gui is
read-only visualization. So the architecture has a real backend with file uploads and
async job execution, not just a tile proxy.

### Frontend (React/TypeScript via Vite, served at `/apps/fimeval-gui/`)

- A guided workflow UI: pick/upload inputs → configure method + options → submit job →
  watch progress → explore results.
- Results view: depends on the v1 UX decision (see §5).
- Borrowed from fimbench-gui: SPA-in-Tethys layout (`reactapp/` builds to
  `tethysapp/.../public/frontend/`), Vite dev proxy, MapLibre, split-view layout.

### Backend (Tethys 4 / Django)

- A `home` controller serving the SPA (same pattern as fimbench-gui).
- REST endpoints for: uploading inputs, listing jobs, submitting a run, polling status,
  downloading outputs.
- Async job execution via Tethys's `DaskJob`.
- Storage of inputs & outputs (workspaces, or MinIO/S3 like fimbench-gui).
- A tile/raster proxy or COG endpoint to render contingency rasters on the map (only if
  Version A UX is chosen).

## 4. Job Execution: Why Tethys `DaskJob`

**Recommendation:** Tethys's built-in `DaskJob` framework, with `LocalCluster` in dev
and a distributed Dask cluster in prod.

Rationale:

- Tethys ships with first-class Dask integration (`tethys_sdk.jobs.DaskJob` plus a
  `DaskScheduler` registered in admin). Job status is persisted in Django's DB, so jobs
  survive worker restarts.
- The `JobsTable` gizmo provides a free "my jobs" UI out of the box (we can replace it
  with a custom React UI; the backend stays the same).
- Dask's `LocalCluster` works in dev with zero infra; prod can point at a distributed
  cluster (or HPC via `dask-jobqueue`) without app-code changes.
- FIMeval workloads are CPU + I/O-bound raster processing — Dask's threading/process
  model fits naturally.

**Celery would also work**, and is more widely known, but it forces a separate broker
(Redis/RabbitMQ), a separate worker process, and doesn't integrate with Tethys's job
admin UI. Net: more moving parts for the same outcome.

## 5. Architectural Principles for "Robust & Scalable"

Two principles shape the design so adding modules later does not destabilize earlier
work:

1. **Pluggable "job type" abstraction.** Each FIMeval module (`EvaluateFIM`,
   `PrintContingencyMap`, `PlotEvaluationMetrics`, `EvaluationWithBuildingFootprint`,
   `benchFIMquery`, `bootstrap`) becomes a registered job type with:
   - a JSON schema for inputs,
   - a Dask task function,
   - a result descriptor (what files/metrics/plots it produces).

   Adding a new module = registering a new job type + a frontend form generated from
   its schema. The submit/poll/download plumbing is written once.

2. **Strict layering between FIMeval and the app.** The Tethys app never reaches into
   FIMeval internals — it only calls the public API (`fp.EvaluateFIM(...)`, etc.) inside
   Dask workers and reads the files that FIMeval writes. If FIMeval changes its
   internals, only the thin wrapper layer needs updating.

## 6. Proposed Module Rollout Roadmap

| Version | Scope |
|---------|-------|
| v1 (MVP) | `EvaluateFIM` with `smallest_extent` + `convex_hull` only. Single case study. Results: metrics CSV + contingency raster. |
| v2 | Add `AOI` method (requires AOI shapefile upload + validation). |
| v3 | Multi-case-study uploads (directory-of-folders structure). |
| v4 | `PrintContingencyMap` + `PlotEvaluationMetrics` built into the results view. |
| v5 | `EvaluationWithBuildingFootprint` (Microsoft default + user-upload option). |
| v6 | `benchFIMquery` — catalog browser; users skip uploading benchmark and pull from server-side catalog. |
| v7 | `bootstrap` evaluation with sub-methods (`random`, `systematic`, `stratified`). |

Each version ships with full tests, isolated from later versions. The pluggable
job-type abstraction means v2 – v7 don't require touching v1's submit plumbing.

## 7. Results UX: Two Versions (Awaiting Decision)

### Version A — Interactive Map Exploration

After a job completes, contingency rasters are converted to **Cloud-Optimized GeoTIFFs
(COGs)** and served via a Tethys raster endpoint (or `titiler`). The React frontend has
a MapLibre map with the contingency raster as an overlay (custom color stops matching
FIMeval's TP/FP/FN/TN/NoData/PWB classes), a basemap toggle (Street / Topo / Satellite),
and a side panel showing metrics. Users can zoom/pan, switch between candidate FIMs in
the same case study, and overlay AOI vectors / PWB boundaries.

- **Pros:** Real geographic context. Lets domain experts spot artifacts, edge effects,
  misregistration. Side-by-side comparison of candidate FIMs at the same view. Matches
  the polish of `fimbench-gui`.
- **Cons:** Significant extra infrastructure — COG conversion pipeline
  (`rio-cogeo` or FIMeval post-processing), raster tile serving (`titiler` or a custom
  Django proxy), browser-side raster styling logic. More frontend code (~3–5× the map
  module work). Risk of perf issues with large rasters.
- **Effort estimate:** ~4–6 weeks for a polished v1 on top of MVP backend.

### Version B — Download-and-Plot Dashboard

After a job completes, the results page shows:

1. the metrics CSV rendered as a sortable table,
2. the PNG outputs from `PrintContingencyMap` and `PlotEvaluationMetrics` displayed
   inline (these are *already produced by FIMeval*),
3. download buttons for each output file (GeoTIFF, CSV, PNG, shapefile).

PNG previews can be pan/zoom'd with a lightweight image viewer (no geographic context).

- **Pros:** Reuses FIMeval's existing outputs as-is — no COG/tile pipeline. Tiny
  frontend surface area. Ships fast. Low risk. Robust by virtue of being simple.
- **Cons:** PNG previews lack basemap context (you see the contingency map but not
  "where on the river"). No zoom-to-feature, no side-by-side candidate comparison at
  arbitrary scales, no overlay toggles. Users who want geographic context have to
  download the GeoTIFF and open it in QGIS.
- **Effort estimate:** ~1–2 weeks on top of MVP backend.

### Claude's Recommendation

**Build B first, then add A as v-next.** Reasoning: the pluggable job-type architecture
treats "result rendering" as another swappable concern. Shipping B gets a working
end-to-end pipeline (upload → job → result) quickly, which de-risks the harder
integration questions (Dask config, file lifecycle, multi-user isolation). Then A
becomes a focused frontend-only project on top of the same backend. This also fits the
"module-by-module, not a house of cards" preference: B's smaller surface area is easier
to harden before adding visualization complexity.

That said, if interactive maps are a hard requirement for stakeholders, building A from
the start avoids a UX regression mid-rollout.

## 8. Open Questions

1. **Version A vs Version B vs A-after-B?** (Pending boss decision.)
2. Storage backend for uploads & outputs — Tethys workspaces vs MinIO/S3 (same as
   `fimbench-gui`)?
3. Authentication model — Tethys/Django default auth, or SSO integration?
4. File-size limits / quotas per user — needed for multi-user safety.
5. Output retention policy — how long do job results stick around before cleanup?

## 9. Inspiration: `fimbench-gui`

Notes drawn from `/home/rragh/tethysdev/tethysapp-fimbench_gui/fimbench-gui`:

- Layout: `reactapp/` (Vite + React + TS) builds to `tethysapp/<app>/public/frontend/`.
- A single `home()` controller with `catch_all=True` serves the SPA.
- A `tile_proxy()` controller forwards gzip-compressed MVT tiles from MinIO.
- Vite dev server (5173) proxies `/apps` → Tethys (8000) to dodge CORS.
- App.tsx holds top-level state (filters, visible features, selection) and pushes via
  props to `FilterSidebar`, `Map`, `FIMTable`.
- Tier-based map styling with zoom-level crossfade.

Differences for `fimeval-gui`:

- **Read/write, not read-only.** Needs upload endpoints, job submission, async
  execution.
- **Many controllers, not two.** Upload, submit-job, list-jobs, job-status,
  download-output, (optionally) raster-tile.
- **Job state.** Django models for `Job`, `JobInput`, `JobOutput` (or rely on
  `DaskJob`'s persistence).
- **Per-user isolation.** Each user's uploads and outputs are scoped to them.
