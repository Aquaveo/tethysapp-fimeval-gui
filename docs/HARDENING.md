# FIMeval GUI — Hardening & Scaling Notes

Assessment of the v1.0.0 architecture for reliability and multi-user parallel
use, with prioritized recommendations. This is planning guidance, not shipped
behavior.

## Where it stands today

The current design is fine for a handful of concurrent users but **not yet safe
for exponential scaling.** Two serial bottlenecks set the ceiling:

1. **Uploads go through Django synchronously** (browser → Daphne → MinIO). Each
   large upload ties up a server worker thread for its whole duration; a few
   simultaneous big-raster uploads saturate the dev server and start timing out
   (`ERR_EMPTY_RESPONSE`).
2. **One Dask worker handles one heavy job at a time.** Each evaluation is a
   single GIL-holding task (reproject + clip + contingency + bootstrap) running
   seconds-to-minutes (hence the "event loop unresponsive" warnings). Throughput
   ≈ number of workers; everything else queues.

**Practical ceiling today: a few concurrent users.** Beyond that, uploads time
out and the Dask queue backs up — with no guardrails (no size limits, quotas, or
cleanup) to keep it safe.

## Risks under parallel load

| Risk | Why it bites under load |
|------|--------------------------|
| Synchronous uploads | Django thread saturation + timeouts |
| Single worker / heavy tasks | Jobs serialize; long waits |
| No per-task memory cap | Large rasters can OOM a worker; concurrent heavy tasks compound it |
| No input limits | A user can upload huge files or spam jobs |
| No storage cleanup | `uploads/` + `outputs/` grow unbounded in MinIO |
| Per-job ArcGIS PWB fetch | External dependency on every run; can rate-limit/fail under load |

## Recommendations (prioritized)

### P1 — unblock throughput & safety
- **Presigned direct-to-MinIO uploads** (browser → MinIO; Django only mints the
  URL). Removes the #1 bottleneck and the Django saturation. *(Roadmap Task #1.)*
- **Input limits & validation**: max file size, max number of candidates,
  extension allow-list, reject non-rasters/empty files early with clear 400s.

### P2 — scale the compute & protect it
- **Size the worker pool**; run **process-based** workers
  (`--nworkers N --nthreads 1`) with **per-worker memory limits**. Optionally use
  Dask **resource tags** to cap concurrent heavy tasks so they don't OOM each other.
- **Per-user concurrent-job quota + basic rate limiting** on submit/upload.
- **Storage lifecycle**: delete inputs after a successful run; expire outputs
  after N days (MinIO lifecycle rule or a scheduled sweep — the code already
  anticipates this).

### P3 — resilience & ops
- **Cache or accept a local PWB** layer to avoid the per-job ArcGIS dependency.
- **Observability**: structured logs, job metrics, worker-health monitoring.

## Notes on current safeguards (already in place)

- Login required on all data endpoints; CSRF cookie enforced on POSTs.
- Per-job isolation by `user_id` + UUID `upload_id`; cross-user access returns 403.
- Marker-based completion (`_SUCCESS`/`_FAILED`) so failures surface instead of
  hanging, and status never races ahead of the full output set.
