#!/usr/bin/env bash
#
# Launch the bounded Dask worker pool with env-configurable limits.
# Choose values with docs/specs/worker-sizing-guide.md.
#
#   FIMEVAL_SCHEDULER      (default tcp://127.0.0.1:8786)
#   FIMEVAL_WORKERS        (default 2)      -> --nworkers
#   FIMEVAL_THREADS        (default 1)      -> --nthreads  (one job per process)
#   FIMEVAL_WORKER_MEMORY  (default 6GB)    -> --memory-limit
#
# Pass --dry-run to print the composed command without launching.
#
set -euo pipefail

# Stream worker stdout live. fimeval prints its progress and (crucially) its
# swallowed error messages; without this Python block-buffers to the pipe and
# those only flush when the worker process exits, hiding failure causes.
export PYTHONUNBUFFERED=1

# Reproject inputs offline. Our CRSs (UTM zones, CONUS Albers) resolve with no
# downloadable PROJ grids. With PROJ_NETWORK on, PROJ reaches a CDN for grid
# metadata, which can fail transiently under load and make every point fail to
# transform ("Too many points failed to transform") — surfacing as a spurious
# evaluation failure. Turning it off removes that whole failure class.
export PROJ_NETWORK=OFF

SCHEDULER="${FIMEVAL_SCHEDULER:-tcp://127.0.0.1:8786}"
WORKERS="${FIMEVAL_WORKERS:-2}"
THREADS="${FIMEVAL_THREADS:-1}"
MEMORY="${FIMEVAL_WORKER_MEMORY:-6GB}"

cmd=(dask worker "$SCHEDULER" --nworkers "$WORKERS" --nthreads "$THREADS" --memory-limit "$MEMORY")

# Echo effective config so a misconfiguration is visible.
echo "FIMeval worker pool: ${WORKERS} worker(s) x ${MEMORY} (threads=${THREADS}) -> ${SCHEDULER}" >&2

# Best-effort soft over-commit warning (reserve ~2.5GB for web server + OS).
mem_gb="$(printf '%s' "$MEMORY" | grep -oiE '^[0-9.]+' || true)"
if [[ -n "$mem_gb" && -r /proc/meminfo ]]; then
  kb="$(awk '/^MemTotal:/{print $2}' /proc/meminfo)"
  if [[ -n "$kb" ]]; then
    total_gb=$(awk -v k="$kb" 'BEGIN{printf "%.1f", k/1048576}')
    pool=$(awk -v w="$WORKERS" -v m="$mem_gb" 'BEGIN{printf "%.1f", w*m}')
    avail=$(awk -v t="$total_gb" 'BEGIN{printf "%.1f", t-2.5}')
    if [[ "$(awk -v p="$pool" -v a="$avail" 'BEGIN{print (p>a)?1:0}')" == "1" ]]; then
      echo "WARNING: pool wants ~${pool}GB but only ~${avail}GB is free after a ~2.5GB web+OS reserve on this ${total_gb}GB host. Lower FIMEVAL_WORKERS or FIMEVAL_WORKER_MEMORY (see docs/specs/worker-sizing-guide.md)." >&2
    fi
  fi
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  printf '%q ' "${cmd[@]}"; echo
  exit 0
fi
exec "${cmd[@]}"
