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

## Worst-case estimates (dev-days, single dev)

Conservative upper bounds incl. tests + review. Done tickets show the effort they
warranted (historical); the numbers to plan around are the not-started ones.

| Ticket | Status | Est |
|--------|--------|----:|
| BE26 | not started | ~2 d |
| BE27 | done | ~1.5 d |
| BE28 | done | ~0.5 d |
| BE29 | done | ~4 d |
| BE30 | done | ~2 d |
| BE31 | done | ~2 d |
| BE32 | done | ~3 d |
| BE33 | done | ~2.5 d |
| BE34 | done | ~1 d |
| BE35 | ✅ done | ~1 d |
| FE15 | done | ~5–6 d |
| FE17 | ✅ done (via BE34 + FE28) | ~3 d |
| ~~FE16~~ → FE35 | renumbered (FE16 is the tracker's) | — |
| ~~FE18~~ → FE36 | renumbered (FE18 = tracker's "Pre-staged Benchmark Upload UI") | — |
| FE19 | done | ~1.5 d |
| FE20 | done | ~0.5 d |
| FE21 | done | ~0.5 d |
| FE22 | done | ~0.5 d |
| FE23 | done | ~1.5 d |
| FE24 | done | ~1 d |
| FE25 | not started | ~1 d (UI only; + ~2–3 d backend storage-layout) |
| FE26 | done | ~1 d |
| FE27 | ✅ done | ~3 d |
| FE28 | ✅ done | ~2 d |
| FE29 | ✅ done | ~3 d |
| FE30 | ✅ done | ~2 d |
| FE31 | ✅ done | ~2 d |
| FE32 | done | ~1.5 d |
| FE33 | not started | ~1.5 d |
| FE34 | not started | ~2–3 d |
| FE35 | not started (was FE16) | ~1.5–2 d |
| FE36 | not started (was FE18) | ~2–3 d |
| BE36 | not started | ~1 d |
| BE37 | not started | ~1.5 d |
| BE38 | not started | ~0.25 d |
| BE39 | not started | ~3–4 d |
| FE37 | not started | ~2 d |
| FE38 | blocked (scope TBD) | ~0.5–1 d |
| FE39 | not started | ~0.5 d |
| FE40 | not started | ~1 d |
| FE41 | not started | ~1 d |
| FE42 | not started | ~2–3 d |
| FE43 | not started | ~1–2 d |
| FE44 | not started | ~1 d |
| FE45 | not started | ~1–1.5 d |
| FE46 | not started | ~2–3 d |

**Remaining, worst-case:** Workspace overhaul (FE27–FE32, BE34 done) ≈ **~13.5 d**;
BE26 ~2 d; FE25 + its backend storage-layout ~3–4 d. Overhaul's biggest uncertainty
is the FE27 router migration and FE31's ECharts→PNG export.

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

### FIMEVAL-BE34 — List a user's runs (`GET api/jobs`)

Description: The workspace's Runs list needs the user's past and in-progress evaluations,
but the app only has `POST api/jobs` (submit) — no way to enumerate jobs. Tethys already
persists a `DaskJob` record per user, so this is a read over existing data.

[  ]  `GET api/jobs` returns the caller's jobs — `[{job_id, method, status, created, upload_id}]`, newest first
[  ]  Per-user isolated (`request.user`); another user's jobs never appear
[  ]  `status` uses the same vocabulary as the status endpoint (submitted/queued/running/complete/error)
[  ]  `POST api/jobs` unchanged; TDD (moto/Tethys): only-my-jobs, ordering, ownership, empty list

Out of Scope
- Pagination/filtering (the list is small for v1)
- Retention/cleanup (BE26)

Notes: New (Workspace UI overhaul). Delivers the backend half of FE17. Provisional number —
BE34 was loosely earmarked for the folder-rename backend (FE25); confirm on the board.

### FIMEVAL-BE35 — Fail fast when no worker picks a job up (short "never-started" timeout)

Description: The wall-clock safety net (BE29) only flips a job to terminal `error` when it's
stuck **`running`** (`if status == 'running' and age > FIMEVAL_JOB_TIMEOUT_SECONDS`, default
30 min). A job that never *starts* — scheduler/worker down, or the pool saturated so it sits
`queued`/`submitted` — isn't covered, so the UI polls "in progress" indefinitely. A no-worker
job should fail in a couple of minutes; but a genuinely-running heavy job must NOT be cut off
early, so this needs a *separate, shorter* threshold than the running timeout.

[  ]  Add a short "never-started" timeout (env `FIMEVAL_JOB_START_TIMEOUT_SECONDS`, default ~120s) applied to `queued`/`submitted` jobs by `creation_time` age → terminal `error` with a clear reason ("no worker picked this up — is the Dask worker running?")
[  ]  Keep the existing running timeout (`FIMEVAL_JOB_TIMEOUT_SECONDS`, 30 min) for jobs actually executing, so a legitimate heavy run isn't killed mid-flight
[  ]  Once a worker writes `_RUNNING` (job is executing), the never-started timeout no longer applies — only the running timeout does
[  ]  Both thresholds env-configurable; documented in HARDENING.md

Out of Scope
- Cancelling / removing the stuck Tethys job record (separate cleanup)
- Fixing submit when the scheduler is unreachable (that already errors)

Notes: Found 2026-08-12 while testing the workspace overhaul with Dask stopped. Provisional
number BE35 — confirm on the board. Complements BE29. Est: ~1 d.

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

> **⚠ FE16 / FE17 / FE18 were early *invented* draft numbers — they belong to the tracker,
> not us (confirmed 2026-08-12: FE18 = "Pre-staged Benchmark Upload UI"). FE17's content
> (job history) already shipped via **BE34 + FE28**. The two still-unbuilt features below are
> renumbered *up* from FE34 → FE35 / FE36. Don't reuse FE16/17/18 for our work.**

### FIMEVAL-FE35 — Inline plot / PNG previews in results

Description: Results show metric cards, a table, client-rendered box-plots, and download
links — but no fimeval-generated plots, because the worker runs `EvaluateFIM` with
`plot_metrics=False`. Enable plot generation and preview PNGs inline.

[  ]  Worker enables plot generation (`plot_metrics` / `PrintContingencyMap`) and uploads the PNGs
[  ]  Results render image outputs inline as thumbnails with a lightbox/zoom
[  ]  Non-image outputs still appear as downloads; runs with no plots render cleanly

Out of Scope
- Plot styling/theming beyond fimeval defaults

Notes: Was mislabeled FE16. Drafted; NOT started. Plotting adds compute/memory — validate against the worker budget before enabling by default (gate behind FE36). Est: ~1.5–2 d.

### FIMEVAL-FE36 — Evaluation parameters panel

Description: The submit UI only picks a method. Framework knobs the library supports are
hardcoded in the worker (bootstrap `sub_method`/`n_iterations`/`n_points`, `target_resolution`).
Expose them as optional advanced parameters.

[  ]  Advanced/optional params section in the wizard (collapsed by default): bootstrap `sub_method` / `n_iterations` / `n_points`; optional `target_resolution` for all methods
[  ]  Submit endpoint validates and threads them through `build_delayed` → `EvaluateFIM`
[  ]  Defaults preserved when untouched; invalid values rejected with a clear message
[  ]  Params surface in the run's Input Files details (ties into FE26)

Out of Scope
- Auto-tuning parameters

Notes: Was mislabeled FE18 (which is the tracker's "Pre-staged Benchmark Upload UI"). Drafted; NOT started. A `target_resolution` control also gives a manual lever against the high-resolution OOM case (complements BE33). Est: ~2–3 d.

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

---

## Workspace UI Overhaul (new — not started)

Single-page workspace replacing the pop-up flow: FIM-family chrome, a persistent Runs
list, a detail pane, and a guided New-Evaluation wizard. Spec + plan (local, gitignored):
`docs/superpowers/{specs,plans}/2026-08-11-workspace-ui-overhaul*`. Base branch
`feat/map-ux`. See BE34 above for the backend endpoint.

### FIMEVAL-FE27 — Workspace shell: single-page layout, routing & FIM chrome

Description: Replace the pop-up run flow with a single-page workspace. Add client-side
routing (`react-router-dom`, as FIMbench uses) and an `AppShell` — FIM-family header +
footer + theme, a left nav, a persistent Runs-list column, and a detail pane.

[  ]  `react-router-dom` added; routes `/new`, `/runs/:jobId`, `/docs` (`/` redirects)
[  ]  `AppShell` renders header + nav + Runs-list slot + detail `<Outlet/>` + footer, fixed full-height
[  ]  Header/footer/theme match FIMbench (navy chrome, partner-logo footer, cyan accent), titled "FIMeval" + tagline; light + dark
[  ]  No `window.open` anywhere in the new shell

Out of Scope
- Runs-list contents (FE28), wizard (FE29), detail pane (FE30)

Notes: New. Combo layout agreed via mockup. Plan Tasks 3–4.

### FIMEVAL-FE28 — Persistent Runs list

Description: A pinned Runs column beside the detail pane lists the user's runs and lets them
jump between results without losing the list. Backed by BE34.

[  ]  `fetchJobs()` data layer + `Job` type in `api.ts`
[  ]  Runs column renders run cards (# · method · status pill · candidates · relative time); click routes to `/runs/:jobId`; selected highlights
[  ]  In-progress rows poll and refresh status live; polling stops when none are active
[  ]  Non-blocking error state if the list can't load (New Evaluation still works)

Out of Scope
- Infinite scroll / search

Notes: New. Delivers the FE17 job-history UI. Plan Tasks 2 + 5. Depends on BE34.

### FIMEVAL-FE29 — New Evaluation wizard

Description: Creating a run becomes a guided 3-step wizard in the detail pane (no pop-up):
① Upload → ② Method → ③ Run. Reuses the existing presign → upload → submit path, so the
BE33 guard + FE24 downsample modal come along.

[  ]  3-step wizard (Upload / Method / Run) with Back/Next in the detail pane
[  ]  "Run evaluation" runs presign → `putFile` → `submitJob(upload_id, method)`; on success routes to `/runs/:jobId`
[  ]  The FE24 too-large modal surfaces at step 3 when the guard fires (Accept → downsample resubmit)
[  ]  `window.open` removed; the new run lands atop the Runs list and auto-opens

Out of Scope
- Advanced evaluation parameters (FE18)

Notes: New. Reworks today's `UploadStep`. Plan Task 6.

### FIMEVAL-FE30 — Run detail pane

Description: Selecting a run shows its detail in the pane, by status: queued/running → live
progress; error → the captured reason (BE27) + Re-run; complete → the existing results
(map-first per FE21, box-plot, metrics, Input Files).

[  ]  `/runs/:jobId` polls status and renders by state (running / error / complete)
[  ]  Reuses `ContingencyMap`, `BootstrapBoxPlots`, `InputFiles`, and the FE21 results order
[  ]  Error state shows the failure reason + a Re-run action
[  ]  A completed run auto-opens after submission

Out of Scope
- Re-run / Export mechanics (FE31)

Notes: New. Plan Task 7.

### FIMEVAL-FE31 — Re-run & downloads

Description: From a run's detail, let users re-run it with one click and download the
outputs. Re-run resubmits the stored `upload_id + method` (inputs persist) — no re-upload.

[  ]  Re-run button (error + completed states) → `submitJob(upload_id, method)` → routes to the new run; guard/modal reused
[  ]  Download the box-plot as PNG (from the ECharts instance)
[  ]  Download the contingency map (GeoTIFF) and the all-results zip

Out of Scope
- Batch re-run / export-all

Notes: New. The "restart on error" boss ask. Plan Task 8.

### FIMEVAL-FE32 — Retire the pop-up flow + polish

Description: Remove the old Stepper/pop-up machinery now that everything lives in the
workspace, and do a responsive + accessibility + light/dark polish pass.

[  ]  `Stepper.tsx` and the pop-up/stepper code removed; no dead paths; no `window.open` remains
[  ]  Responsive (nav + Runs list collapse), visible keyboard focus, light/dark verified
[  ]  `tsc` + `lint` + `build` clean; manual script (create → auto-open → open past run → re-run error → downloads → no pop-ups) passes

Out of Scope
- Effort 3 (retention/cleanup — BE26)

Notes: New. Plan Task 9.

### FIMEVAL-FE33 — Mobile: restack the workspace on small screens

Description: The workspace's three columns (nav · Runs list · detail) only *shrink* on
narrow screens (FE32), so they get cramped on a phone. Make it genuinely responsive:
below a breakpoint the columns **restack** into a mobile layout — nav as a top bar /
menu, the Runs list collapsible or full-width, and the detail full-width.

[  ]  Below ~640px the columns restack rather than shrink (nav → top bar/menu; Runs list → collapsible drawer or full-width list; detail full-width)
[  ]  No horizontal body scroll at any width; wide content (map, tables) scrolls within its own container
[  ]  Touch-sized targets; the Runs list stays reachable (toggle/drawer) without losing the detail
[  ]  Usable down to ~360px

Out of Scope
- Native app / offline

Notes: New. Follow-up to FE32 (which shrinks but doesn't restack). User request 2026-08-12. Est: ~1.5 d.

### FIMEVAL-FE34 — Dark mode

Description: Add a dark theme to the workspace. The FIM chrome (blue banner header/footer)
stays; the content area — Runs list, detail pane, cards, tables, contingency map panel,
box-plots — flips to dark surfaces with light text, following the viewer's OS preference
and/or an in-app toggle. Requires theming every component through tokens (some currently
hardcode light colours). **Design sign-off on a dark mock-up required before build.**

[  ]  Dark token set (dark surfaces/borders/text, brighter cyan accent) via `prefers-color-scheme` + optional in-app toggle
[  ]  All content components theme correctly in dark: runlist cards, results panels/tables/cards, ECharts box-plots, contingency map legend + controls, wizard, modals
[  ]  **All text stays light/readable on dark surfaces** — incl. the run **method name** in the Runs cards (user flagged it as unreadable in the dark preview)
[  ]  **Dark banner assets:** swap Header-HQ / Footer-HQ / FilterSidebar to dark-recoloured variants (e.g. `*-dark.png`, user is preparing them) under `prefers-color-scheme: dark` / the toggle
[  ]  Chrome banners + partner logos stay legible on dark; contrast meets WCAG AA in both themes
[  ]  No light-mode regressions

Out of Scope
- Per-user *persisted* theme preference (default to OS is fine for v1)

Notes: New. User wants a mock-up to sign off before build. Follow-up to the overhaul.
User request 2026-08-12. Est: ~2–3 d.

---

## Method, Input & UI Refinements (2026-08 meetings + backlog sweep)

From two rounds of meeting notes (evaluation-methodology; MVP/memory) plus a backlog
sweep, 2026-08-13. Numbers continue *up* from the overhaul (last used FE36 / BE35);
next free after this batch = **FE47 / BE40**. Meeting owners noted where assigned.

### FIMEVAL-BE36 — Thread the bootstrap sampling approach; default to Stratified

Description: The worker hardcodes `sub_method='random'` for bootstrap. Accept the chosen
sampling approach (random / systematic / stratified) at submit and thread it to
`EvaluateFIM`, defaulting to **stratified** (team decision).

[  ]  Submit accepts `sub_method` ∈ {random, systematic, stratified}; validated; threaded via `build_delayed` → `EvaluateFIM`
[  ]  Default = **stratified** when unspecified (replacing the hardcoded 'random')
[  ]  Verified against fimeval that all three sub_methods run
[  ]  TDD

Out of Scope
- `n_iterations` / `n_points` exposure (FE36)

Notes: Pairs with FE37; a slice of / overlaps FE36. Est: ~1 d.

### FIMEVAL-BE37 — Benchmark input validation: duplicate + "BM" naming convention

Description: fimeval keys off a "BM" token to recognize the benchmark, so a duplicated or
mis-named benchmark confuses it → the 5-min timeout. Validate benchmark inputs pre-run.

[  ]  Reject a candidate byte-identical to the benchmark (and any two-benchmark case) with a clear message — no 5-min timeout
[  ]  **Require a distinct "BM" token** in the benchmark filename (`_BM` / `BM_`, e.g. `BLE_2048397_BM` — NOT `BLEBM_24947028`); block if absent
[  ]  **Warn if a *candidate* name contains `_BM` / `BM_`** → "Did you mean to add <file> as the Benchmark raster?"; block until changed
[  ]  Surfaced in the wizard before submit where possible; enforced at submit; TDD

Out of Scope
- Deep raster content comparison beyond byte identity

Notes: Owner Supath (meeting). Merges the meeting's duplicate-benchmark task + the user's
BM-naming rules. Completes an unshipped BE29 criterion. Est: ~1.5 d.

### FIMEVAL-BE38 — Raise the per-file upload cap to 2 GB

Description: The team set a **2 GB per-file** ceiling (memory safeguard). Our default is 1 GB
(`FIMEVAL_MAX_UPLOAD_BYTES`). Align it to 2 GB and keep the FE messaging consistent.

[  ]  Per-file cap = 2 GB (default or env); enforced at presign/submit
[  ]  The FE40 modal + upload validation quote **2 GB**
[  ]  Still env-overridable

Out of Scope
- The working-set pixel guard (BE33) is unchanged

Notes: Small. Est: ~0.25 d. Could fold into FE40.

### FIMEVAL-BE39 — Reduce reproject/resample memory footprint to raise concurrency

Description: The box is memory-limited to ~2 concurrent jobs; the **repro** and **resample**
steps are the heaviest. Reduce their footprint (windowed/streaming reprojection, or
pre-resampling inputs before fimeval — we don't modify fimeval) so more jobs fit.

[  ]  Measure repro/resample peak RSS on representative inputs
[  ]  Reduce it via our own pre-processing, verified metric-identical
[  ]  Concurrency can rise above 2 on the same box; documented in the worker-sizing guide

Out of Scope
- New hardware / autoscaling

Notes: Builds on BE31's pre-clip (~8.5×); overlaps the earlier perf probe. Est: ~3–4 d.

### FIMEVAL-FE37 — Split "Method" into Full Domain vs Bootstrap (+ new defaults)

Description: Restructure the method step into two clearly-separated categories (per the
desktop app): **Full Domain** (Convex Hull · AOI · Intersected Extent) — evaluates *all*
pixels — and **Bootstrap** (Random · Stratified · Systematic) — *samples* pixels (runs the
intersected analysis internally). **Remove Smallest Extent.**

[  ]  Two visually-separated sections: "Full Domain" (3 methods) + "Bootstrap" (3 sampling approaches)
[  ]  **Smallest Extent removed** from the picker
[  ]  Defaults: **Full Domain = Intersected Extent**; **Bootstrap = Stratified**
[  ]  Choosing Bootstrap reveals the sampling picker; copy clarifies all-pixels vs sampled

Out of Scope
- `n_iterations` / `n_points` controls (FE36)

Notes: Depends on BE36. ⚠ Confirm: remove Smallest Extent from the UI only, or from
backend `VALID_METHODS` too? Est: ~2 d.

### FIMEVAL-FE38 — Reposition interface elements onto the main page

Description: Nathan asked that *specific* interface elements move to the main/dashboard area
for consistency, validated by testing.

[  ]  *(pending)* List the elements to reposition
[  ]  Move them into the main dashboard area
[  ]  Verify consistent behavior during testing

Out of Scope
- Broader layout redesign

Notes: **Blocked** on the element list. Est: TBD (~0.5–1 d once scoped).

### FIMEVAL-FE39 — Improve logo visibility against the background

Description: The logo reads poorly against the gray background; rethink its treatment for
contrast/visibility.

[  ]  Logo clearly legible against its background (adjust logo, backing, or placement)
[  ]  Works in the header chrome across sizes

Out of Scope
- Full rebrand

Notes: Confirm which logo / where it sits on gray. Est: ~0.5 d.

### FIMEVAL-FE40 — Welcome / guidelines modal on page load

Description: A page-load modal that gives a broad "what FIMeval does" overview **and** the
file requirements users need before submitting — formats, the **2 GB limit**, resolution
guidance, and target CRS — to preempt size/memory failures.

[  ]  Modal appears on first load: app overview + file guidelines (formats, 2 GB, resolution, target CRS)
[  ]  Dismissible; doesn't reappear every navigation (session/localStorage), with a way to reopen
[  ]  Accessible (focus trap, escape/close)

Out of Scope
- Per-user server-side "seen it" tracking

Notes: Owner Reshma (meeting). Merges the meeting's guidelines modal + the app-overview idea. Est: ~1 d.

### FIMEVAL-FE41 — "Re-evaluate" (rename Re-run) → wizard with same inputs, jump to Method

Description: Rename **Re-run → "Re-evaluate"**. Instead of resubmitting the same config, it
opens **New Evaluation** pre-loaded with the run's input files and **jumps to the Method
step**, so the user picks a different method/sampling without re-uploading.

[  ]  Button reads "Re-evaluate"
[  ]  Opens the wizard pre-filled from the run's `upload_id`, starting at the Method step
[  ]  User changes method/sampling and submits, re-using the existing upload (no re-upload)
[  ]  The too-large/downsample modal still applies

Out of Scope
- Editing the input files themselves (re-upload is a fresh New Evaluation)

Notes: Changes the shipped FE31 behavior. Est: ~1 d.

### FIMEVAL-FE42 — Candidate raster: folder & .zip upload

Description: Let users add candidates as a selected **folder** (all GeoTIFFs within) or a
**.zip** (unzip → GeoTIFFs), each checked against the benchmark — in addition to picking
individual files.

[  ]  Folder select adds all `.tif`/`.tiff` within as candidates
[  ]  `.zip` is unzipped (client or server) and its GeoTIFFs added as candidates
[  ]  Non-GeoTIFF entries ignored with a note; per-file limits + BE37 naming checks still apply

Out of Scope
- Nested archives

Notes: FE + BE (presign flow / unzip). Est: ~2–3 d.

### FIMEVAL-FE43 — AOI shapefile: folder / .zip upload

Description: Accept the AOI shapefile bundle as a **.zip** or a selected **folder** (all
sidecars), not only multi-file selection.

[  ]  `.zip` of shapefile parts accepted → extracted (`.shp`/`.shx`/`.dbf`/`.prj`…)
[  ]  Folder select accepted
[  ]  Validates a `.shp` + required sidecars are present; clear error otherwise

Out of Scope
- Reconstructing sidecars from a lone `.shp` (not possible)

Notes: ⚠ "single shapefile" read as folder/zip (a lone `.shp` lacks its sidecars — confirm). Est: ~1–2 d.

### FIMEVAL-FE44 — Consolidate the sidebar (Runs previews into the nav)

Description: The left nav is sparse (＋New / Documentation / signed-in). Merge the **Runs
previews into it** so the left column is one useful sidebar and the detail pane gets more width.

[  ]  Left sidebar shows ＋New Evaluation, the Runs previews (status · method · time), and Documentation / signed-in
[  ]  Selecting a run still opens it in the detail pane; polling + highlight preserved
[  ]  Detail pane gains the reclaimed width

Out of Scope
- Mobile restack (FE33)

Notes: Refines the FE27 shell (drops the separate 3rd column). Est: ~1 d.

### FIMEVAL-FE45 — Two-column results layout

Description: Lay results out in two columns so the contingency map and the box-plot/metrics
table are visible **without scrolling**.

[  ]  Results use a responsive two-column grid (e.g. map one side, box-plot/metrics the other)
[  ]  Key outputs visible without scrolling on a typical screen; collapses to one column when narrow
[  ]  Preserves the FE21 emphasis (map prominent)

Out of Scope
- Per-user layout persistence

Notes: Refines ResultsView (FE30). Est: ~1–1.5 d.

### FIMEVAL-FE46 — Contingency map class controls (per-class visibility + recolor)

Description: Add **per-class visibility toggles** on the contingency map (TP · FP · FN · TN ·
Permanent Water) so a user can isolate, e.g., only False Positives; and **recolor FN → Red,
FP → Yellow**.

[  ]  Recolor: **FN = Red**, **FP = Yellow** (backend colormap + frontend legend)
[  ]  Per-class visibility toggles for TP / FP / FN / TN / Permanent Water
[  ]  Rendering approach chosen for per-class visibility — per-class tile layers OR a client-side paint filter (the COG bakes class codes into one raster, so it's more than a CSS toggle)

Out of Scope
- Per-class opacity

Notes: Extends FE20. The recolor half is trivial + can ship independently. Est: ~2–3 d.
