# Worker-Pool Sizing Guide

The bounded Dask worker pool has to share a host with the web server (Daphne)
and the operating system. This guide picks values for `FIMEVAL_WORKERS` and
`FIMEVAL_WORKER_MEMORY` (consumed by
[`tethysapp/fimeval_gui/scripts/start_worker.sh`](../../tethysapp/fimeval_gui/scripts/start_worker.sh))
so the pool fits without starving the web server — the failure that OOM-killed
Daphne on 2026-07-20.

## The formula

```
workers = floor( (total_RAM − daphne_reserve − os_reserve) / per_worker_memory )
```

| Term | Recommended | Why |
|------|-------------|-----|
| `daphne_reserve` | **~1.5 GB** | Headroom for the web server. Presigned uploads (FIMEVAL-BE16) keep file bytes out of Daphne, so its footprint is now small and stable — **measured idle ~0.41 GB, peak ~0.46 GB, flat even during 72–85 s uploads** (2026-07-29, below). 1.5 GB is deliberately conservative; on a tight host you can justify ~1 GB. |
| `os_reserve` | **~1 GB** | Kernel, shell, MinIO client, misc. |
| `per_worker_memory` | **≥ 6 GB** | Heavy methods peak ~4.5 GB per job (**measured**: a worker paused at Dask's 80 % threshold at 4.52 GiB process memory). 6 GB keeps a worker below the pause threshold while leaving room for the nanny to restart a runaway. |

**Do not** drop `per_worker_memory` below the ~4.5 GB job peak to fit more
workers — a limit under the peak OOM-kills individual heavy jobs. On a small
host, cut **concurrency** (fewer workers), not the per-worker limit.

## Worked examples

**16 GB host (current dev default):**
```
floor((16 − 1.5 − 1) / 6) = floor(2.25) = 2 workers
→ FIMEVAL_WORKERS=2 FIMEVAL_WORKER_MEMORY=6GB
```
This is exactly the pool the wrapper launches by default.

**8 GB host:**
```
floor((8 − 1.5 − 1) / 6) = floor(0.9) = 0 heavy workers
```
6 GB doesn't fit even once with reserves. Options:
- **One worker at 5 GB** — `FIMEVAL_WORKERS=1 FIMEVAL_WORKER_MEMORY=5GB`. Heavy
  jobs run one at a time; 5 GB still clears the ~4.5 GB peak. (Everything beyond
  one job queues — the pool already serializes.)
- **Move workers to a separate host** (see below).

## Dev vs production topology

- **Co-located (typical dev):** web server and workers share one machine, so you
  **must** reserve for Daphne + OS as in the formula. This is the configuration
  where the 2026-07-20 shared-memory OOM happened.
- **Separate hosts (recommended for production):** run workers on a different
  machine from the web server. That host has no Daphne to protect, so size it as
  `workers = floor((total_RAM − os_reserve) / per_worker_memory)`. In this
  topology the shared-memory OOM cannot occur — the web server and workers no
  longer compete for the same RAM.

## Measuring Daphne on your host

The `daphne_reserve` above is a safe default; confirm it on your own deployment.
With the Tethys server running:

```bash
# Idle web-server RSS (sum across Daphne worker processes):
ps -o rss= -C daphne | awk '{s+=$1} END{printf "daphne idle: %.0f MB\n", s/1024}'

# Peak during the heaviest web operation — a results "Download all" (ZIP):
#   trigger the download, then sample RSS for a few seconds
for i in $(seq 1 10); do
  ps -o rss= -C daphne | awk '{s+=$1} END{printf "%.0f MB\n", s/1024}'
  sleep 0.5
done
```

If your web server runs under a different process name (e.g. `gunicorn` or
`python manage.py runserver`), find its PID with `ss -ltnp | grep :8000` and use
`ps -o rss= -p <pid>`. Set `daphne_reserve` to the observed peak plus a little
headroom (round up). Post-BE16 this is a few hundred MB (measured below), so
1.5 GB is already conservative.

## Measured on the dev host (16 GB, 2026-07-29)

Numbers from a live session of 7 back-to-back runs (all methods, some overlapping)
on the default `FIMEVAL_WORKERS=2 FIMEVAL_WORKER_MEMORY=6GB` pool, host total
15.6 GB:

| What | Idle | Peak | Takeaway |
|------|------|------|----------|
| Web server (Daphne / dev `runserver`) | ~0.41 GB | **~0.46 GB** | Essentially flat, even during 72–85 s uploads — presigned uploads keep bytes out of the app server. `daphne_reserve` 1.5 GB is ~3× the observed peak. |
| Worker (pool of 2, RSS summed) | ~0.24 GB | **~5.9 GB** | A single heavy job drove one worker to ~4.5 GB (Dask paused it at the 80 % threshold), validating `per_worker_memory ≥ 6 GB`. |
| Host free RAM | ~12.9 GB | floor **~7.2 GB** | No OOM. Dask's pause/resume throttled memory as designed (3 pause/resume cycles observed). |

**Pathological input caution.** A job with **two very-high-resolution rasters**
(a 0.5 m benchmark used as both benchmark *and* candidate, ~1.6 Gpixels each)
blew past the 6 GB limit — `MakeFIMsUniform` resamples to the *coarsest* input, so
with no coarse input nothing downsamples. The nanny OOM-restarted the worker and
the job was lost. The bounded pool contained the blast (the host never OOM-killed),
but this confirms the rule above: **cut concurrency, not `per_worker_memory`**, and
see FIMEVAL-BE29 (input guard + fast terminal error) for the fix.
