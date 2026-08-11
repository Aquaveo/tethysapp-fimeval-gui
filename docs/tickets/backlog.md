# FIMeval GUI — Ticket Backlog

Ticket bodies for the reliability and GUI-expansion work, in Scrum-ready format.
One-line summaries and status live in [`../ROADMAP.md`](../ROADMAP.md).

**⚠ Ticket numbers:** the issue tracker is the source of truth for numbers; the
authoritative local mirror is Claude's `reference_ticket_registry.md`. Do not invent
new numbers — pull the next free one from the tracker (see CLAUDE.md). Known
collisions resolved 2026-08-06: **FE14** = the tracker's "Run Intersected Extent & AOI
(validation)" ticket (so the Input-Files disclosure moved to **FE26**); **BE19** =
"Accept Candidates on Existing upload_id" (so "Bounded Dask Worker Pool" moved to **BE32**).

---

## Reliability & Backend

### FIMEVAL-BE26 — Output retention & cleanup policy

Description: `uploads/` and `outputs/` grow unbounded in MinIO — no lifecycle, so every
run's inputs and artifacts persist forever. Add a retention policy that reclaims storage
without breaking re-run or recent-results access.

[  ]  Inputs (`uploads/<user_id>/<upload_id>/`) removed after a successful run, with a grace window so re-run still works for a configurable period
[  ]  Outputs expire after a configurable N days (MinIO lifecycle rule or scheduled sweep)
[  ]  Failed-job inputs retained long enough to diagnose / re-run
[  ]  Retention window(s) configurable via env var; documented in the hardening notes

Out of Scope
- Per-user storage quotas (separate ticket)
- Any UI for browsing/managing stored artifacts

Notes: Drafted only; NOT started. Feeds the "Effort 3" retention piece of the workspace overhaul.

### FIMEVAL-BE27 — Surface fimeval failure cause

Description: Failed evaluations show a generic "Evaluation failed." `fimeval.EvaluateFIM`
swallows its own exceptions (prints `Error evaluating…`, returns no `EvaluationMetrics.csv`),
and the worker's stdout is block-buffered so even that print is invisible until the process
exits. Capture fimeval's output and surface a real reason.

[  ]  Worker wraps `EvaluateFIM` in `redirect_stdout`/`redirect_stderr` and writes the captured cause into the `_FAILED` marker body
[  ]  `GET api/jobs/{id}` returns that reason; the UI shows it instead of "The evaluation failed"
[  ]  `PYTHONUNBUFFERED=1` in the worker so logs stream live
[  ]  No changes to the `fimeval` package

Out of Scope
- Changing any success-path behavior

Notes: Shipped — `fde55d6`.

### FIMEVAL-BE28 — Disable PROJ network grids in the worker (`PROJ_NETWORK=OFF`)

Description: A transient `1296/1296 points failed to transform` failure was traced to
`PROJ_NETWORK=ON` (env default): PROJ reaches a CDN for datum-shift grid metadata, which
can fail under load. The relevant transforms resolve fully offline, so the dependency is
unnecessary.

[  ]  `PROJ_NETWORK=OFF` exported in `scripts/start_worker.sh` before `exec dask worker …`
[  ]  Verified on a running worker (`/proc/<pid>/environ`)
[  ]  Full evaluation of all five methods still succeeds — no transform regression
[  ]  Rationale documented in the worker-sizing guide / README

Out of Scope
- (none)

Notes: Shipped — `3d8b121`. Pairs with BE27.

### FIMEVAL-BE29 — OOM-killed jobs hang the UI + input guard

Description: A user set the same 0.5 m raster as both benchmark and candidate;
`MakeFIMsUniform` resamples to the coarsest resolution, so two full-res arrays exceeded the
worker budget → the nanny OOM-killed and restarted the worker → the task was cancelled
without writing a `_FAILED` marker → the status endpoint never reported `error` → the UI
polled for 5+ minutes. Fail fast and cleanly, and guard the common accident.

[  ]  OOM-killed / lost / cancelled tasks reach a terminal `error` in the UI within a bounded time, with an actionable message
[  ]  Dask task retries bounded (no restart loop)
[  ]  Server-side wall-clock job timeout marks stuck jobs `error`; status endpoint degrades to the stored marker instead of throwing
[  ]  Pre-submit input guard rejects a job whose working set exceeds the budget
[  ]  Legitimate large jobs that fit the budget still run

Out of Scope
- (none)

Notes: Shipped (three slices). The guard's estimate was later corrected by BE33.

### FIMEVAL-BE30 — Persist & expose input metadata (names, resolution, CRS)

Description: Original filenames are discarded at upload (renamed to `benchmark.tif` /
`candidate_i.tif`), and the job persists only `{upload_id, user_id, method}`. Capture names
+ resolution + CRS at submit and expose them.

[  ]  Original filenames persisted (carried from presign via a `manifest.json`)
[  ]  Each raster's resolution + CRS read from its GeoTIFF header; AOI boundary CRS from its `.prj`
[  ]  `GET api/jobs/{id}` returns an `inputs` object: `benchmark`, `candidates[]`, optional `boundary` — each with name/resolution/CRS
[  ]  Present while the job is still Queued; header reads add no material latency

Out of Scope
- Any change to evaluation behavior

Notes: Shipped — `365530c`. Blocks FE26.

### FIMEVAL-BE31 — Pre-clip candidate to the benchmark extent

Description: A large candidate raster is fully loaded and reprojected before fimeval clips
anything, blowing the worker memory budget. Clip each candidate to the benchmark's extent
(plus a small buffer) in the worker before `EvaluateFIM`. Metric-safe: an evaluation only
ever covers benchmark ∩ candidate.

[  ]  Each candidate clipped to the benchmark extent (+buffer) before fimeval; metrics identical to the unclipped run
[  ]  Worker peak memory materially reduced (live-validated 4638 MB → 542 MB, ~8.5×, identical CSI)
[  ]  A non-overlapping candidate is dropped and the run continues on the valid ones; the job fails only if *no* candidate overlaps
[  ]  Clip preserves dtype / CRS / nodata / band tags / colormap

Out of Scope
- Reprojection/CRS reconciliation (fimeval handles that)

Notes: Shipped — `3c8bae5` (+ review `e8693d1`).

### FIMEVAL-BE32 — Bounded Dask worker pool

Description: One worker handling one heavy job at a time serializes throughput, and with no
per-task memory cap, concurrent heavy jobs can OOM each other. Run a bounded, process-based
worker pool with per-worker memory limits, and report queued status when full.

[  ]  Configurable pool via `start_worker.sh` (`--nworkers` / `--nthreads` + per-worker memory limit)
[  ]  Concurrency bounded; excess jobs queue and report status `queued`
[  ]  Per-worker memory cap contains the blast radius so heavy jobs don't OOM each other or the host
[  ]  Worker-sizing guide documents how to size the pool

Out of Scope
- Autoscaling / dynamic pool resizing
- Cross-user fairness (see BE25 priority/round-robin)

Notes: Shipped. **Renumbered to BE32 on 2026-08-06** (originally collided at BE19).

### FIMEVAL-BE33 — Estimate post-uniformization working set + offer downsample

Description: The BE29 guard rejected jobs on the benchmark's *raw* pixel count, so a
fine-resolution Tier_1 benchmark was refused even though fimeval downsamples every input to
the coarsest input resolution first (the "Tier_1 rejected" bug). Estimate what fimeval will
actually process, and offer a downsample path instead of a hard reject.

[  ]  Guard estimates the working set as benchmark ∩ candidate overlap area ÷ coarsest input resolution² (max over candidates), not raw benchmark pixels
[  ]  A coarsenable Tier_1 raster passes; a genuinely-too-large job is still caught
[  ]  Rejection message exposes no worker-memory internals to the user
[  ]  `downsample: true` resubmit threads a computed fit `target_resolution` through to `EvaluateFIM`

Out of Scope
- A manual per-input resolution control (that's the eval-params panel, FE18)

Notes: Shipped — `d238699`.

---

## Frontend

### FIMEVAL-FE15 — Interactive contingency map viewer

Description: The results view reported metrics numerically but had no spatial visualization.
Serve the contingency raster as web-map tiles (worker writes a COG; rio-tiler tile endpoints)
and render it on a MapLibre map with a TP/FP/FN/TN legend.

[  ]  Worker writes a `contingency.cog.tif`; backend serves `tiles.json` + PNG tile endpoints (per-user/job scoped)
[  ]  Results view shows an interactive pan/zoom map of the contingency raster with a class legend
[  ]  Colors correctly distinguish TP/FP/FN/TN; map fits the data extent
[  ]  Additive — degrades gracefully (panel hidden) when no contingency raster is present

Out of Scope
- Layer toggles / basemap switcher / opacity (delivered as FE19/FE20)

Notes: Shipped (PR #8). MVP; scope B/C became FE19/FE20.

### FIMEVAL-FE16 — Inline plot / PNG previews in results

Description: Results show metric cards, a table, client-rendered box-plots, and download
links — but no fimeval-generated plots, because the worker runs `EvaluateFIM` with
`plot_metrics=False`. Enable plot generation and preview PNGs inline.

[  ]  Worker enables plot generation (`plot_metrics` / `PrintContingencyMap`) and uploads the PNGs
[  ]  Results render image outputs inline as thumbnails with a lightbox/zoom
[  ]  Non-image outputs still appear as downloads; runs with no plots render cleanly

Out of Scope
- Plot styling/theming beyond fimeval defaults

Notes: Drafted; NOT started. Plotting adds compute/memory — validate against the worker budget before enabling by default (gate behind FE18).

### FIMEVAL-FE17 — Job history list

Description: Each run opened in its own pop-up; closing it lost the run from the UI. Jobs are
persisted server-side (Tethys `DaskJob`), so a history view is a read over existing data.

[  ]  Backend "list my jobs" endpoint returns the caller's jobs (id, method, status, created, upload_id), per-user-isolated
[  ]  A history list in the main window: past runs with status, method, timestamp, link to results
[  ]  In-progress rows live-refresh; a user only sees their own jobs

Out of Scope
- Retention/cleanup (BE26)

Notes: **Largely superseded by the Workspace UI overhaul** (the pinned Runs list + `GET api/jobs` = BE34 deliver this). Keep as the tracking ticket or fold into the overhaul.

### FIMEVAL-FE18 — Evaluation parameters panel

Description: The submit UI only picks a method. Framework knobs the library supports are
hardcoded in the worker (bootstrap `sub_method`/`n_iterations`/`n_points`, `target_resolution`).
Expose them as optional advanced parameters.

[  ]  Advanced/optional params section in the submit flow (collapsed by default): bootstrap `sub_method` / `n_iterations` / `n_points`; optional `target_resolution` for all methods
[  ]  Submit endpoint validates and threads them through `build_delayed` → `EvaluateFIM`
[  ]  Defaults preserved when untouched; invalid values rejected with a clear message
[  ]  Params surface in the run's Input details (ties into FE26)

Out of Scope
- Auto-tuning parameters

Notes: Drafted; NOT started. A `target_resolution` control also gives a manual lever against the high-resolution OOM case (complements BE33).

### FIMEVAL-FE19 — Configurable, switchable basemaps

Description: The contingency map had a single hardcoded satellite basemap. Add a configurable
set of basemaps and a switcher, keeping Satellite as the default.

[  ]  New `basemap_layers` custom setting (comma-separated preset keys: satellite/street/topographic; blank = all)
[  ]  `GET api/basemaps` resolves the setting into the layer list + default
[  ]  Frontend switcher swaps the basemap (Satellite default); built-in fallback if the endpoint is unreachable

Out of Scope
- Arbitrary user-supplied tile URLs (preset keys only)

Notes: Shipped — `b9747f0` / `116b30c`.

### FIMEVAL-FE20 — Contingency overlay visibility + opacity

Description: The TP/FP/FN/TN overlay was always fully opaque with no way to see the imagery
underneath. Add a visibility toggle and an opacity slider.

[  ]  "Show overlay" toggle drives the overlay layer's visibility (basemap untouched)
[  ]  Opacity slider (0–100%) drives `raster-opacity`; disabled while the overlay is hidden

Out of Scope
- Per-class visibility toggles

Notes: Shipped — `b41b239`.

### FIMEVAL-FE21 — Contingency map first in results

Description: The results view led with metric cards, the table, and box-plots, with the map
near the bottom. Reorder so the map is the first output.

[  ]  Contingency map renders first in the results view
[  ]  Box-plots (bootstrap) / metrics table (other methods) render second
[  ]  Map self-hides when a run has no contingency COG (no empty gap)

Out of Scope
- Changes to the result components themselves

Notes: Shipped — `8c70f5f`.

### FIMEVAL-FE22 — Input Files disclosure in the results view

Description: The "Input Files" disclosure (FE26) existed only in the running pop-up. Show it
in the results view too, via a shared component.

[  ]  "Input Files ▶" appears in the results view (benchmark / candidate(s) / boundary; name · resolution · CRS)
[  ]  Rendered from a single shared component reused by both views (DRY)
[  ]  Best-effort — hidden if absent; no change to the running view

Out of Scope
- New metadata fields (uses BE30's `inputs`)

Notes: Shipped — `5853326`. Depends on FE26 + BE30.

### FIMEVAL-FE23 — Fix maplibre-gl-worker.mjs 404 in production

Description: The MapLibre worker 404'd only in the Tethys-served production build (dev works,
Vite serves `node_modules` directly). maplibre's minified `new URL('./maplibre-gl-worker.mjs',
<bundle>)` is invisible to Vite's static analysis, so the worker file was never emitted.

[  ]  Worker imported via Vite's `?worker&url` (bundled into a self-contained asset)
[  ]  `maplibregl.setWorkerUrl()` registers the emitted base-prefixed URL
[  ]  Production build emits `assets/maplibre-gl-worker-*.js`; no 404 at `:8000`; tiles render

Out of Scope
- (none)

Notes: Shipped — `6729ee1`.

### FIMEVAL-FE24 — Accept/Reject "coarser resolution" modal

Description: When BE33's guard rejects a job as too large, offer to run it at a coarser
resolution instead of a dead-end error.

[  ]  A `too_large` submit response shows a modal (not a generic error)
[  ]  "Run at a coarser resolution" resubmits the same upload with `downsample: true` (no re-upload; pop-up opens from the click)
[  ]  "Cancel" dismisses and keeps the selected inputs

Out of Scope
- A manual resolution slider (FE18)

Notes: Shipped — `60f41e3`. Depends on BE33.

### FIMEVAL-FE25 — Label benchmark vs candidate in the UI

Description: Boss feedback: stop renaming uploads to `benchmark.tif` / `candidate_N.tif` in
storage. Store inputs under `Benchmark/` and `Candidate/` folders keeping original filenames
(backend half), and make the UI clearly label which raster is the Benchmark and which is the
Candidate.

[  ]  UI labels each input as Benchmark vs Candidate consistently (upload, running, results)
[  ]  Original filenames shown everywhere (no `candidate_0.tif`-style placeholders)
[  ]  Works against the `Benchmark/` + `Candidate/` folder storage layout

Out of Scope
- The backend storage-layout change itself (its own BE ticket — renumber; was loosely earmarked BE34)

Notes: NOT started. Largest blast radius of the map-UX batch (touches the earliest merged branch).

### FIMEVAL-FE26 — "Input Files" disclosure

Description: While a job is queued/running, users can't see which files the run is
evaluating. Add a collapsible "Input Files" disclosure driven by BE30's `inputs`.

[  ]  "Input Files ▶" below the status line; `▶`/`▼` toggle, collapsed by default, keyboard-accessible
[  ]  Each raster shows name · resolution · CRS; AOI runs also show the boundary shapefile name + CRS
[  ]  Works before completion (Queued/Running); non-AOI shows no empty boundary section

Out of Scope
- Showing it in the results view (that's FE22)

Notes: Shipped — but built under the wrong number: commit `597476f` reads `FIMEVAL-FE14`.
**Reassigned to FE26 on 2026-08-06** (FE14 = the tracker's validation ticket). Depends on BE30.
