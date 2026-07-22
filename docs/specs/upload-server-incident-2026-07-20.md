# Incident note: web server killed during overnight testing (2026-07-20)

**Author:** Reshma Raghavan · **Status:** for team discussion
**Related:** `performance-story.md` (PERF-1..3), 2026-07-16 meeting decisions

## What happened

While manually testing the new job-queue features (evening of July 20):

1. **19:58 — Bootstrap run** on a 408 MB benchmark: upload succeeded, the
   evaluation failed inside the fimeval library (the known flaky
   permanent-water-bodies "arange" bug, see PERF-2 findings). The UI showed an
   honest "Evaluation Failed" screen — the new `_RUNNING`/`_FAILED` marker
   system working as designed. Before this week, this failure spun forever.
2. **20:00 — AOI run** on the same 408 MB benchmark: succeeded in 65 s.
3. **~20:02 — Intersection run** (tiny 7 MB inputs): the upload hung
   indefinitely. No data reached storage; no job was created.
4. **20:03–20:37 — the machine stalled.** Dask worker logs show event loops
   frozen for up to 25 minutes at a stretch; 1.9 GB was still sitting in swap
   the next morning — the signature of memory exhaustion and swap thrash
   (compounded by the PC locking during the episode).
5. **The Tethys web server (Daphne) was killed silently** — no traceback, no
   log line — and stayed dead overnight. The Dask nanny killed and restarted
   its own stalled worker at 20:37 (**the bounded pool self-healed as
   designed**).

## Why it matters: the web server is now the weakest link

The bounded worker pool agreed at the 2026-07-16 meeting protects the
*workers*: at most 2 evaluations run at once, each capped at 6 GB, and a
runaway worker is restarted automatically. Last night confirmed all of that
works.

But the **web server has no such protection**:

- Every upload passes through it: browser → Daphne → MinIO. Daphne buffers
  request bodies in memory, and Python does not return that memory to the
  operating system — two back-to-back ~410 MB uploads leave a permanent
  footprint.
- When the machine ran short of memory, the OOM killer's likely target was
  therefore the web server — and unlike the workers, **nothing restarts it**.
  One kill took the whole app offline until a human noticed.

In short: we fenced the workers, and the pressure moved to the web server.

## Recommendations

1. **Pull the presigned-uploads ticket forward** (queued since July 1, branch
   `fix/upload-reliability` exists). The browser gets a short-lived signed URL
   and sends file bytes **directly to MinIO**; the web server only handles a
   tiny JSON exchange. This removes the web server from the upload data path
   entirely — its memory use becomes flat regardless of file size. Works
   identically in local dev (MinIO supports presigned URLs natively) and in
   any cloud deployment, and also fixes the long-standing "large uploads crawl
   and time out" issue.
2. **Watch web-server memory during the queue rehearsal** (Task 6 of the
   current plan): record `free -h` while 5 jobs + uploads run concurrently, so
   we have numbers for how much headroom Daphne actually needs.
3. **Dev quality-of-life:** run the dev server under a trivial auto-restart
   wrapper so an overnight kill doesn't strand testing. In production this job
   belongs to the process supervisor / orchestrator, plus a reverse proxy
   (which spools large request bodies to disk) and separate memory budgets for
   web and worker processes.
4. **Report the fimeval "arange" bug upstream** (sdmlua/fimeval): the
   permanent-water-bodies fetch intermittently returns invalid bounds and
   kills otherwise-valid evaluations. It is unrelated to this app's code and
   hits real user data.

## What last night proved works

- Upload CSRF self-healing fix (same evening): both large uploads succeeded.
- `_RUNNING`/`_SUCCESS`/`_FAILED` markers: correct queued/running/ failed/
  complete reporting on every job, including an honest failure screen.
- Bounded pool self-healing: the stalled worker was killed and restarted
  automatically; no manual intervention needed on the worker side.

## Addendum — reproduced with a hard OOM trace (2026-07-21)

Reran the sequence: Bootstrap → Intersection (both queued/ran/completed
cleanly — "Queued" screen confirmed) → AOI. The AOI upload never landed and
the web server was killed, same as before — this time the kernel log captured
the exact cause:

```
2026-07-21 16:13:38  HeapHelper invoked oom-killer
Out of memory: Killed process 4415 (python3.13)
  total-vm:19.4 GB, anon-rss:14.7 GiB
```

This upgrades "the OOM killer's *likely* target was the web server" to a
confirmed fact:

- The victim was a **single python process at ~14.7 GiB RSS**. The Dask
  workers are hard-fenced at 5.59 GiB (nanny pauses at 80%, recycles ~95% —
  visible self-healing in the worker log at 16:11:44), so a 14.7 GiB process
  cannot be a worker. It is the unfenced web server buffering the AOI
  multipart body in RAM (`api_upload` in `controllers.py` accepts up to
  ~11 GB per request by its own limits).
- **Why always the 3rd job:** by the third run the two worker processes are
  still sitting on several GB each of *un-released* memory (worker log:
  "Unmanaged memory: 3.95 GiB … may not be released to the OS"). The first two
  uploads had headroom; the third lands the upload buffer on top of two fat
  workers and tips a 15 GiB machine over.
- **The queue is not at fault.** It only gates *compute* (`api_jobs_submit`);
  the *upload* stage (`api_upload`) is ungated and runs upstream of it, so AOI
  died before it ever reached the queue. Serializing compute to 1-at-a-time
  would not fix this — the killer is the upload buffer, not compute
  concurrency. This is the direct case for Recommendation 1 (presigned uploads
  remove the web server from the upload data path entirely).

**WSL-relay casualty (2nd-order effect of the 07-20 freeze):** the overnight
memory episode also wedged the WSL→Windows localhost relay — the server was
healthy inside WSL (`curl` 200) but Windows browsers hung on
"Waiting for 127.0.0.1". Killing the wedged WSL Relay procs and Windows-side
`wslrelay.exe` (CLOSE_WAIT pileup) did not re-establish forwarding for new
listeners; a full reboot was required. Diagnostic trick that worked:
`powershell.exe` from WSL to run `netstat` / `Test-NetConnection` /
`Stop-Process` on the Windows side.
