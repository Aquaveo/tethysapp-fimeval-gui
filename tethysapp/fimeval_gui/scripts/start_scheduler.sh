#!/usr/bin/env bash
#
# Launch the Dask scheduler for FIMeval.
#
# Bounds how many times a task is retried after a worker DIES (e.g. an OOM-kill)
# before it is marked errored — distributed.scheduler.allowed-failures. Dask's
# default is 3, so an OOM-looping task kills three workers (thrashing the pool
# and disrupting other jobs) before it errs. We default to 1: tolerate one
# transient worker loss, then fail the task fast so the UI reaches a terminal
# error quickly (see also the wall-clock timeout in api_job_status).
#
#   FIMEVAL_SCHEDULER_PORT    (default 8786)
#   FIMEVAL_ALLOWED_FAILURES  (default 1)  -> distributed.scheduler.allowed-failures
#
# Pass --dry-run to print the composed command without launching.
#
set -euo pipefail

PORT="${FIMEVAL_SCHEDULER_PORT:-8786}"
export DASK_DISTRIBUTED__SCHEDULER__ALLOWED_FAILURES="${FIMEVAL_ALLOWED_FAILURES:-1}"

echo "FIMeval scheduler: port ${PORT}, allowed-failures=${DASK_DISTRIBUTED__SCHEDULER__ALLOWED_FAILURES}" >&2

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "DASK_DISTRIBUTED__SCHEDULER__ALLOWED_FAILURES=${DASK_DISTRIBUTED__SCHEDULER__ALLOWED_FAILURES} dask scheduler --port ${PORT}"
  exit 0
fi
exec dask scheduler --port "$PORT"
