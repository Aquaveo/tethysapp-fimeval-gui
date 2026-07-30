# FIMeval GUI — Ticket Backlog

Full ticket bodies for the reliability and GUI-expansion work. One-line summaries
and status live in [`../ROADMAP.md`](../ROADMAP.md).

**Dependency notes:** FE14 depends on BE30; the rest are independent.
Worst-case estimates in dev-days.

---

## Reliability & Observability

### FIMEVAL-BE27 — Surface fimeval failure cause instead of a generic "Evaluation failed"

**Type:** Bug / Observability · **Priority:** High · **Est:** ~1.5 d

**Context**
When a fimeval evaluation fails, users see only a generic "Evaluation failed" with
no cause. Two compounding layers hide the real error:

1. `fimeval.EvaluateFIM` **swallows its own exceptions** — on failure it
   `print()`s `Error evaluating …` / `Error processing folder …` and returns
   *without* raising and without writing `EvaluationMetrics.csv`
   (`evaluationFIM.py`). Our worker (`job_types/evaluate_fim.py`) only observes
   "no CSV" → writes a bare `_FAILED` marker + raises a generic `RuntimeError`.
2. The worker's **stdout is block-buffered** (writes to a pipe, not a TTY), so even
   that printed error is invisible until the worker process exits — confirmed
   2026-07-29: all fimeval output appeared only when the worker was killed. On
   2026-07-28, four real failures (`Too many points (1296/1296) failed to
   transform, unable to compute output bounds`) were printed but never surfaced.

**Scope** *(our code only — do NOT modify the fimeval library)*
- In `run_evaluate_fim_task` (`tethysapp/fimeval_gui/job_types/evaluate_fim.py`),
  wrap the `EvaluateFIM(...)` call in `contextlib.redirect_stdout`/`redirect_stderr`
  to capture fimeval's output. (Technique proven in the 2026-07 investigation.)
- On failure (no `EvaluationMetrics.csv`), write the captured text — or at minimum
  the extracted `Error evaluating` / `Error processing` line — into the `_FAILED`
  marker object body (currently empty) and into the job-status error payload
  returned by `api_job_status`.
- Surface a short, non-generic reason in the UI failure state (`RunningStep.tsx`)
  instead of "The evaluation failed."
- Set `PYTHONUNBUFFERED=1` (or `python -u`) in `scripts/start_worker.sh` so worker
  logs stream live during ops/debugging.

**Acceptance criteria**
- A deliberately-failing evaluation records a `_FAILED` marker whose body contains
  the actual fimeval error text.
- `GET api/jobs/{id}` for a failed job returns that reason; the UI shows it.
- Worker logs flush in real time (no need to kill the worker to see fimeval output).
- No changes to the `fimeval` package.

**Notes:** does not change success behavior; purely makes failures diagnosable.

---

### FIMEVAL-BE28 — Disable PROJ network grids in the worker (`PROJ_NETWORK=OFF`)

**Type:** Hardening · **Priority:** Medium · **Est:** ~0.5 d

**Context**
The 2026-07-28 failures (`1296/1296 points failed to transform`) were transient and
unreproducible across six strategies (direct, thread, fork, real Dask workers ×
concurrency, cold PROJ cache, network on/off); a 2026-07-29 retest passed 7/7. The
best-fit trigger is `PROJ_NETWORK=ON` (default in this env): PROJ reaches a CDN for
datum-shift grid metadata, which can fail transiently under load. Verified the
relevant transforms (EPSG:32618→5070, 5070→5070) need **no** downloadable grid —
they resolve fully offline (0 unavailable operations).

**Scope**
- Set `PROJ_NETWORK=OFF` in the worker environment via `scripts/start_worker.sh`
  (export before `exec dask worker …`).
- Document in `worker-sizing-guide.md` / README why (removes a network dependency
  the transforms don't need; eliminates this transient failure class).

**Acceptance criteria**
- Worker processes run with `PROJ_NETWORK=OFF` (verify via `/proc/<pid>/environ`).
- A full evaluation of each method (smallest_extent, convex_hull,
  intersected_extent, bootstrap, AOI) still succeeds — no transform regression.

**Notes:** low-risk; pairs with BE27 (if a transform ever *does* need a grid, BE27
makes that failure visible).

---

### FIMEVAL-BE29 — Jobs that OOM-kill the worker hang the UI until timeout (+ input guard)

**Type:** Bug / Reliability · **Priority:** High · **Est:** ~4 d

**Context**
Found in live demo 2026-07-29: a user set the **same benchmark raster as both
benchmark and candidate**. Confirmed inputs (upload `69f49c5c`): `benchmark.tif`
= 390 MiB, `candidate_0.tif` = 390 MiB (the same 0.5 m raster,
40885×39527 ≈ 1.6 Gpixels). The request hung 5+ min with no result.

Root cause (evidence-confirmed): `MakeFIMsUniform` resamples all inputs to the
**coarsest** resolution present. Normally a coarser candidate downsamples a fine
benchmark (a run with the same 390 MiB benchmark + a 909 KiB coarse candidate
succeeded). With **two 0.5 m inputs**, coarsest = 0.5 m → nothing downsamples →
two full-res arrays exceed the 6 GB worker budget → the nanny OOM-kills and
restarts the worker → the task is **cancelled and never writes a `_FAILED`
marker** (output dir left with only `_RUNNING`) → `api_job_status` never reports
`error` (its Dask `Future(key).status` call times out) → the frontend polls
indefinitely.

The bounded pool worked as designed (contained the blast — the host never OOM'd).
This ticket is about **failing fast and cleanly**. Note: BE27 does *not* cover this
— the worker dies before it can capture/print anything.

**Scope**
- **(a) Terminal state on worker death.** Make an OOM-killed / lost / cancelled task
  resolve to a terminal `error` quickly instead of hanging:
  - Bound Dask task retries so a memory-killed task isn't silently resubmitted into
    a restart loop.
  - Add a server-side wall-clock job timeout; on exceed, mark the job `error`.
  - In `api_job_status`, treat `lost`/`cancelled`/unreachable-future (after retries)
    as terminal `error`, and harden the 5 s Dask client call so it degrades to the
    stored status instead of throwing.
  - Surface a clear reason in the UI ("Evaluation ran out of memory / did not
    complete") rather than an endless spinner.
- **(b) Input guard (prevent the common accident).** Before submitting:
  - Reject (or warn) when a candidate is byte-identical to the benchmark.
  - Estimate the post-uniformization pixel budget (coarsest res × combined extent)
    and reject with a clear "inputs too large / too high-resolution for the worker
    memory limit — downsample or raise `FIMEVAL_WORKER_MEMORY`" message, linking
    `worker-sizing-guide.md`.

**Acceptance criteria**
- Submitting benchmark-as-candidate (or any job that OOM-kills the worker) reaches
  a terminal **error** in the UI within a bounded time (no 5-min hang), with an
  actionable message.
- A memory-killed task is not resubmitted into an infinite restart loop.
- The input guard blocks the identical benchmark/candidate case pre-submit with a
  clear message.
- Legitimate large jobs that fit the budget still run.

---

### FIMEVAL-BE30 — Persist + expose evaluation input metadata (names, resolution, CRS)

**Type:** Backend / Feature · **Priority:** Medium *(blocks FE14)* · **Est:** ~2 d

**Context**
Original filenames are discarded at upload (renamed to `benchmark.tif` /
`candidate_i.tif`), and the job persists only `{upload_id, user_id, method}`. No
input metadata is available to the frontend. FE14 needs names + resolution + CRS
**while the job is Queued/Running**, so it must be captured at submit — not by the
worker.

**Scope**
- At submit, **persist original filenames** (benchmark + candidates) — carry through
  from the presign step via a `manifest.json` under the upload prefix, or re-send at
  submit.
- Read each raster's **resolution + CRS** from its GeoTIFF header in storage (few-KB
  header range read via `/vsis3` or a boto3 range GET — no full download).
- **AOI:** read the boundary `.shp` **CRS** from its `.prj`, list the bundle
  components (+ geometry type / feature count if easy).
- Persist per-input `{name, resolution, crs}` (job `extended_properties` or the
  manifest).
- **Expose via `api_job_status`** as an `inputs` object:
  `{ benchmark:{name,resolution,crs}, candidates:[…], boundary?:{name,crs,…} }`.

**Acceptance criteria**
- `GET api/jobs/{id}` returns an `inputs` object: benchmark + candidates with
  name/resolution/CRS; AOI jobs also include `boundary` (name/CRS).
- Present while the job is still **Queued** (computed at submit, before the worker
  runs).
- Header reads add no material submit latency (range reads only, no full download).
- No change to evaluation behavior.

---

## GUI

### FIMEVAL-FE14 — "Input Files" disclosure in the run window

**Type:** Frontend / Feature · **Priority:** Medium · **Est:** ~1 d · **Depends on:** BE30

**Context**
Boss request (2026-07-30): while a job is queued/running, users can't see which
files that run is evaluating. Each run opens in its own pop-up window, and the
original filenames are only visible in the upload window.

**Scope** — in `RunningStep` (the Queued/Running pop-up), add an **`Input Files ▶`**
disclosure **below the status line**: `▶`/`▼` toggle, collapsed by default,
keyboard-accessible. Render each input from `api_job_status`'s `inputs` as
`filename · resolution · CRS`; for AOI, add a boundary row (shapefile name + CRS).
Style-consistent; degrades gracefully on missing fields.

**Acceptance criteria**
- `Input Files ▶` appears below Queued/Running; clicking toggles `▶`/`▼` and
  shows/hides the box.
- Every raster shows name + resolution + CRS; AOI also shows boundary shapefile
  name + CRS.
- Works before completion (Queued/Running); non-AOI shows no empty boundary section.

---

### FIMEVAL-FE15 — Interactive contingency map viewer

**Type:** Feature *(FE + BE)* · **Priority:** High *(= roadmap "Version A")* · **Est:** ~5–6 d

**Context**
The results view (Version B) reports metrics numerically but has **no spatial
visualization** — and the app currently has no map component at all. The product
vision is explicitly "explore results: **contingency maps**." Every non-trivial
method produces a **confusion/contingency raster** (TP/FP/FN/TN classes; seen as
`Confusion raster unique values [0 1 2 3 4 5]`) plus clipped benchmark/candidate
rasters in the outputs.

**Scope — Backend**
- Serve the contingency GeoTIFF as web-mappable tiles: convert to **COG** (a
  COG-conversion script already exists in `scripts/`) and expose a raster
  tile/serve endpoint, following the existing `tile_proxy` controller pattern used
  for catalog MVT tiles.
- Endpoint scoped per-user/job (reuse `<user_id>/<upload_id>/` isolation).

**Scope — Frontend**
- Add a **MapLibre** map to the results view (new panel or tab).
- Overlay the contingency raster with a **class color ramp** (TP/FP/FN/TN) +
  **legend**; basemap options (street/satellite, like the catalog map);
  zoom-to-extent.
- Toggle layers (contingency / clipped benchmark / clipped candidate).

**Acceptance criteria**
- Results shows an interactive, pan/zoom map of the contingency raster with a class
  legend.
- Colors correctly distinguish TP/FP/FN/TN; layer toggles work; map fits the data
  extent.
- Works for every method that emits a contingency raster; degrades gracefully if one
  isn't present.

**Notes:** biggest single GUI item; the tiling/COG backend is the main risk. Pairs
with FE16 (static plot previews) as the two "visual results" tickets.

---

### FIMEVAL-FE16 — Inline plot / PNG previews in results

**Type:** Feature *(FE + BE)* · **Priority:** Medium · **Est:** ~1.5–2 d

**Context**
Results currently show metric cards, a table, client-rendered bootstrap box plots,
and download links — but **no fimeval-generated plots**, because the worker runs
`EvaluateFIM` with `plot_metrics=False` and doesn't call `PrintContingencyMap` /
`PlotEvaluationMetrics`, so **no PNGs are produced**.

**Scope — Backend**
- Enable plot generation in the worker (`plot_metrics=True` and/or
  `PrintContingencyMap` / `PlotEvaluationMetrics`), upload resulting PNGs to the
  job's outputs.

**Scope — Frontend**
- In `ResultsStep`, render image outputs (PNG) **inline** as thumbnails with a
  lightbox/zoom, instead of download-only; keep non-image outputs as download links.

**Acceptance criteria**
- Successful runs show inline plot previews (contingency map + metric plots); click
  enlarges.
- Non-image outputs still appear as downloads; results with no plots render cleanly.

**Notes:** plotting adds compute/memory to each run — validate against the worker
memory budget (ties into the perf/OOM findings) before enabling by default;
consider gating behind a parameter (see FE18).

---

### FIMEVAL-FE17 — Job history list

**Type:** Feature *(FE + BE)* · **Priority:** Medium · **Est:** ~3 d

**Context**
Each run opens in its own pop-up; when it's closed the run vanishes from the UI.
Jobs *are* persisted server-side (Tethys `DaskJob` records with
`extended_properties`), so a history view is a read over existing data.

**Scope — Backend**
- Add a **"list my jobs"** endpoint returning the requesting user's jobs: id,
  method, status, created timestamp, upload_id (filtered by `request.user`,
  respecting per-user isolation).

**Scope — Frontend**
- A history list/view in the main window (or a route): past runs with **status
  indicators** (queued / running / complete / error), method, timestamp, and a link
  to open that run's results; live-refresh in-progress rows.

**Acceptance criteria**
- Main window lists the user's past runs with correct status and method/timestamp.
- Clicking a completed run opens its results; a user only sees their own jobs.
- In-progress jobs update status without a manual refresh.

**Notes:** benefits directly from BE27/BE29 (failed/OOM jobs show a real terminal
status here rather than a stale "running").

---

### FIMEVAL-FE18 — Evaluation parameters panel

**Type:** Feature *(FE + BE)* · **Priority:** Medium · **Est:** ~2–3 d

**Context**
The submit UI only picks a method. Framework knobs the library already supports are
**hardcoded** in the worker (`evaluate_fim.py`): bootstrap `sub_method='random'`,
`n_iterations=100`, `n_points=500`, and `target_crs`/`target_resolution`. The vision
includes "configure evaluation parameters."

**Scope — Frontend**
- Add an **advanced/optional parameters** section in `UploadStep` (collapsed by
  default): for bootstrap → `sub_method` (random / systematic / stratified),
  `n_iterations`, `n_points`; optionally `target_resolution` for all methods.
  Sensible defaults, range validation.

**Scope — Backend**
- Accept these params in the submit endpoint, validate, and thread them through
  `build_delayed` → `EvaluateFIM` (they're already function args).

**Acceptance criteria**
- Bootstrap submit exposes `sub_method` / `n_iterations` / `n_points`; values reach
  the worker and change the run.
- Defaults preserved when the panel is untouched; invalid values rejected with a
  clear message.
- Params surface in the run window's Input details (ties into FE14) so a run is
  self-describing.

**Notes:** keep advanced params collapsed to avoid cluttering the simple flow; a
`target_resolution` control also gives users a manual lever against the FE15/BE29
high-resolution OOM case.
