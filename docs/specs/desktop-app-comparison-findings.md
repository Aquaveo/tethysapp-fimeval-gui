# Desktop App Comparison Findings — FIMEVAL-PERF-3

**Question (follow-up to [perf-profiling-findings.md](perf-profiling-findings.md)
and [fimeval-optimization-findings.md](fimeval-optimization-findings.md)):** the
FIMeval **Desktop app** (a tkinter GUI built by the FIMeval method's designer,
repo `~/random/FIMeval/fimpef_final`) runs the same heavy methods without ever
OOMing. Does it do anything per-job that makes it faster or leaner than the web
app — and how does it stack up in a serial, apples-to-apples comparison?

**Answer, in one line:** it doesn't — the Desktop app **as-shipped is heavier
(5.75 vs 4.52 GB peak) and ≥2× slower on bootstrap** than the web app's
configuration on identical data, because it ships the older fimeval 0.1.62; its
entire reliability advantage is a `"Busy"` dialog that **forbids running more
than one job, ever** (`gui.py:774-780`). A bounded worker pool gives the web app
the same safety with strictly more throughput.

**Date:** 2026-07-15 · WSL2, 15.6 GiB RAM · fimeval **0.1.64** (web / tethys
env) vs **0.1.62** (the wheel shipped in the Desktop repo's `dist/`) · methodology
identical to PERF-1 (`/usr/bin/time -v`, one job at a time, same datasets).

---

## 1. What the Desktop app actually is

A single-file tkinter GUI (`fimpef_final/gui.py`, 984 lines) wrapping the same
pip `fimeval` package the web worker imports. Facts that matter here:

- **Strict serial execution.** `_run_task` (gui.py:774) refuses to start while
  `self._running` is set — a *"A task is already running. Please wait."* dialog —
  and disables both Run buttons for the duration. One background thread, one job.
  The web app's OOM scenario (3 concurrent heavy methods) is unreachable by
  construction.
- **Same compute.** The Run buttons call `fe.EvaluateFIM(**kwargs)`
  (gui.py:844) — no chunking, no Dask, no memory management of its own.
- **Two config differences from our worker:** it defaults **Target Resolution
  to 10 m** (passed as `target_resolution`; our worker passes only
  `target_crs='EPSG:5070'`), and it exposes a **PWB_dir** field (empty by
  default, so the network PWB fetch happens there too).
- It ships fimeval **0.1.62** (`pyproject.toml` / bundled `.venv`, macOS-built);
  the web worker requires **≥ 0.1.64**.

## 2. Experiment design

Harness: `measure_mem_desktop.py` (checked in next to PERF-1's
`measure_mem.py` in `~/random/fimeval-notebook/FIMeval/`) — identical staging
(`main_dir/case_study/` symlinks, `target_crs='EPSG:5070'`,
`sub_method='random'` for bootstrap, recursive shapefile discovery for AOI),
plus one flag: `--target-res`, mirroring the Desktop GUI default.

Three configurations per method, all **serial**, all under `/usr/bin/time -v`:

| Run | Config | fimeval | Mirrors |
|---|---|---|---|
| **A** | `target_crs` only | 0.1.64 | the web worker (`evaluate_fim.py`) |
| **B** | + `target_resolution=10` | 0.1.64 | Desktop *config* on the web's library |
| **C** | + `target_resolution=10` | 0.1.62 | the Desktop app as-shipped |

Datasets: **Tier_2** (Intersection, Bootstrap) and **For_AOI/Tier_1** (AOI) —
the exact PERF-1 datasets, so run A doubles as a reproduction check. The 0.1.62
code came from the Desktop repo's own wheel
(`fimpef_final/dist/fimeval-0.1.62-py3-none-any.whl`), shadowed via
`PYTHONPATH` over the tethys env.

## 3. Findings

### F0 — Harness validation: run A reproduces PERF-1 within 1 MB

| Method · data | PERF-1 peak RSS (KB) | This report, run A (KB) |
|---|--:|--:|
| Intersection · Tier_2 | 4,741,304 | 4,742,108 |
| Bootstrap · Tier_2 | 4,743,540 | 4,743,112 |
| AOI · For_AOI/Tier_1 | 3,038,940 | 3,038,556 |

Memory is deterministic and the comparison is apples-to-apples. (Wall times ran
~35 % faster than PERF-1's across the board — an unloaded box, same code.)

### F1 — The Desktop app as-shipped is *heavier* per job, and slower on bootstrap

![Serial head-to-head: memory and time per method and configuration](img/perf3/serial_head_to_head.png)

| Method | A: web (0.1.64) | B: 0.1.64 + res=10 | C: **desktop, 0.1.62 + res=10** |
|---|--:|--:|--:|
| Intersection | 4.52 GB / 46 s | 4.52 GB / 39 s | **5.75 GB** / 51 s |
| Bootstrap | 4.52 GB / 41 s | 4.52 GB / 41 s | **5.75 GB** / 84 s *(repeat: 102 s)* |
| AOI | 2.90 GB / 61 s | 2.90 GB / 51 s | 2.90 GB / 51 s |

The +1.2 GB and the bootstrap slowdown land between **B and C** — same config,
different library version — so they are 0.1.62's cost, not the Desktop app's
config. The 0.1.62→0.1.64 diff shows a rework of the benchmark masking flow in
`ContingencyMap/evaluationFIM.py` (0.1.62 does a rasterio `mask(crop=True)`
read plus a PWB `geometry_mask` over the cropped full-res image; 0.1.64 reads
the raw benchmark once and binarizes before masking). The warp/compress hot path
(`utilis.py`, the PERF-2 F2/F3 ceiling) is **byte-identical** between versions.

The delta is data-dependent: on For_AOI/Tier_1 the peak (2.90 GB, set by the
warp phase) is identical across all three configs — 0.1.62's extra masking copy
stays *below* the warp ceiling there, while on Tier_2's finer evaluation grid it
pokes ~1.2 GB above it. C's 5.75 GB peak reproduced in all three C runs
(6,031,604 / 6,034,024 / 6,031,128 KB).

**Consequence:** the web app already runs the *leaner* library. Keep the worker
pinned to fimeval ≥ 0.1.64 — and per-job sizing should assume ~4.5 GB, not the
Desktop app's ~5.75 GB.

### F2 — `target_resolution=10` saves **zero** memory (A ≡ B, byte-for-byte)

Peak RSS with and without the Desktop's 10 m target differs by < 1 MB in every
method. This independently confirms PERF-2 F3: the memory ceiling is set by
`compress_tif_lzw` reading the **full-native-resolution warp intermediate**,
which exists *before* any resampling — so the resample target cannot move it.
Only the single-pass warp fix (PERF-2 F2) moves the ceiling.

It does trim ~15 % wall time on Intersection and AOI (smaller grid for the
masking/metrics stages; bootstrap is unchanged — its extra cost is sampling).
Whether the web app should pass `target_resolution=10` is a **science
question** (it changes output granularity), not a performance one; the method's
designer made it her GUI's default, which is worth raising with her.

### F3 — The Desktop app's only structural advantage is that it forbids concurrency

![What each deployment lets stack up in RAM](img/perf3/oom_mechanism.png)

At 5.75 GB/job the Desktop app could not safely run even two concurrent jobs on
this machine — it simply never tries. One job at a time is safe on any
reasonably specced laptop, which fully explains the "runs fine on the
colleague's Mac" observation from PERF-1 §5: **the Mac's RAM was never the
point; the serialization was.** Meanwhile the web app's single shared worker
lets three 4.52 GB jobs stack to ~13.6 GB + the web server — the PERF-1 §3.5
OOM-killer scenario.

A bounded pool (e.g. `dask worker --nworkers 2 --nthreads 1 --memory-limit 5GB`,
already sketched in [HARDENING.md](../HARDENING.md) P2) is strictly better than
the Desktop app's discipline: same safety, 2× the throughput, process isolation
(no GIL contention — PERF-1 §3.3), and excess jobs queue instead of stacking.

## 4. Recommendations

1. **Nothing to port from the Desktop app.** It has no per-job optimization to
   learn from; the web app's library version is newer and leaner. Its one good
   idea — never exceed the memory budget — belongs at the worker pool
   (HARDENING.md P2), not in the UI.
2. **Keep fimeval pinned ≥ 0.1.64** (F1). If the Desktop app is ever
   redistributed, suggest the same upgrade to its author — it's a free 1.2 GB
   and a 2× bootstrap speedup for her users.
3. **Don't adopt `target_resolution=10` for performance** (F2 — no memory
   effect); raise it with the FIMeval team as a *default-output* question.
4. PERF-2 recommendations unchanged: the single-pass warp remains the only
   change that moves the per-job memory ceiling.

## 5. Caveats

- **Single run per cell**, except: C's memory (3 consistent runs) and C's
  bootstrap slowdown (84 s and 102 s vs 41 s — well beyond the network-PWB
  variance included in every run).
- C runs 0.1.62's *Python code* on the tethys env's dependency stack (rasterio
  1.5.0 etc.), not the Desktop `.venv`'s macOS binaries (which don't run on
  Linux). Version-vs-version conclusions are about fimeval's code, and the hot
  path is byte-identical; the exact +1.2 GB could shift on other dependency
  versions.
- The Desktop GUI also passes `seed=42` / `plot_metrics=True` for bootstrap by
  default; the harness keeps PERF-1's exact call instead (neither affects peak
  memory; `plot_metrics` adds plotting time not measured here).
- Wall times moved ~35 % vs PERF-1 with machine load alone — compare *within*
  this report's columns, not across reports.

## Appendix — reproduce

```bash
# harness lives next to PERF-1's:
cd ~/random/fimeval-notebook/FIMeval
conda activate tethys

# A — web worker config (identical to measure_mem.py):
/usr/bin/time -v python measure_mem_desktop.py intersected_extent Tier_2

# B — desktop config on 0.1.64:
/usr/bin/time -v python measure_mem_desktop.py intersected_extent Tier_2 --target-res 10

# C — desktop as-shipped (0.1.62 wheel from the Desktop repo, shadowed):
pip install --no-deps --target /tmp/fimeval062 \
    ~/random/FIMeval/fimpef_final/dist/fimeval-0.1.62-py3-none-any.whl
PYTHONPATH=/tmp/fimeval062 /usr/bin/time -v \
    python measure_mem_desktop.py intersected_extent Tier_2 --target-res 10

# AOI uses For_AOI/Tier_1 (shapefile auto-discovered from its AOI/ subfolder)
```

Raw results (peak RSS in KB from `/usr/bin/time -v`; wall = `EvaluateFIM` only):

| Run | wall (s) | peak RSS (KB) |
|---|--:|--:|
| intersected_extent A | 46.2 | 4,742,108 |
| intersected_extent B | 39.4 | 4,742,632 |
| intersected_extent C | 50.6 | 6,031,604 |
| bootstrap A | 41.0 | 4,743,112 |
| bootstrap B | 41.1 | 4,743,248 |
| bootstrap C | 83.8 | 6,034,024 |
| bootstrap C (repeat) | 101.5 | 6,031,128 |
| AOI A | 60.9 | 3,038,556 |
| AOI B | 51.3 | 3,040,868 |
| AOI C | 51.1 | 3,041,100 |

Charts regenerate via `python docs/specs/perf3-findings-charts.py`.
