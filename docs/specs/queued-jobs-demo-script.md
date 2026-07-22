# Demo script: bounded worker pool + honest job queue

Walkthrough for demoing the 2026-07-16 "manage jobs first" slice
(FIMEVAL-BE16–18, FE13). Rehearsed 2026-07-21; numbers below are from that run.

## Before the demo (5 min)

Start the stack in this order (each in its own terminal, `tethys` conda env):

```bash
# 1. MinIO (if not already running as the docker container)
# 2. Dask scheduler
dask scheduler --port 8786
# 3. Bounded worker pool — THE star of the demo
dask worker tcp://127.0.0.1:8786 --nworkers 2 --nthreads 1 --memory-limit 6GB
# 4. Web server
tethys manage start
```

Then open `http://localhost:8000/apps/fimeval-gui/` and **hard-refresh**
(Ctrl+Shift+R) so the browser picks up the current frontend bundle.

Have a heavy dataset ready (e.g. the Tier_1 pair: 390 MB benchmark +
candidate). Small inputs finish too fast to show queueing.

## The demo (5–10 min)

1. **Set the scene** — one sentence: *"Heavy evaluations peak at ~4.5 GB each;
   three at once used to crash the whole server with no error message. Now
   jobs run two at a time and everyone else waits in an honest queue."*
2. **Launch three evaluations back-to-back**: fill the upload form
   (benchmark + candidate, method e.g. Intersection), click **Upload & Run**;
   repeat twice more. Each job opens its own pop-up window.
3. **Point at the pop-ups**:
   - Jobs 1 and 2 show **Running** with a live elapsed counter
     (*"0:42 elapsed — heavy methods typically finish in about a minute"*).
   - Job 3 shows **Queued** — pulsing dot, *"Waiting for a worker slot…"*,
     and the explanation that jobs run two at a time.
4. **Say what's happening underneath**: the worker writes a `_RUNNING` marker
   to object storage the moment it picks a job up; the status endpoint uses
   markers to tell "waiting for a slot" apart from "actually computing" —
   Dask alone cannot tell those apart.
5. **Wait ~90 s**: job 3 flips Queued → Running → Results on its own. Nothing
   crashed; nobody restarted anything.
6. **Optional close**: show `free -h` on the server mid-run — memory stays
   bounded no matter how many jobs are submitted.

## Numbers to quote (2026-07-21 rehearsal, 15.6 GB dev box)

- 5 concurrent `intersected_extent` jobs on the 390 MB Tier_1 benchmark:
  **all 5 succeeded**, wall time **181 s** (single job alone: 100 s — so 5
  jobs cost only ~1.8× one job).
- **Never more than 2 jobs computing** at any instant (5 s marker sampling);
  the queue drained in arrival order.
- Minimum free memory during the run: **7.6 GB** — no OOM kill, no worker
  restart, no swap thrash (compare: 3+ unbounded concurrent heavy jobs
  previously froze the machine for 30+ minutes and killed the web server —
  see `upload-server-incident-2026-07-20.md`).
- Queued job wait ≈ one job duration (~100 s) — matches the "≈ N/2 rounds"
  math the UI hint implies.

## If something goes wrong live

- **Job fails with "Evaluation Failed"**: most likely the flaky upstream
  fimeval permanent-water-bodies fetch (the "arange" bug — network-dependent).
  Just resubmit; it usually passes on retry. The failure screen itself is a
  feature — these used to spin forever.
- **Upload hangs**: check the web server is alive; large uploads still transit
  Daphne until the presigned-uploads ticket lands.
- **Everything shows Queued**: the worker pool isn't running — start it with
  the exact command above.
