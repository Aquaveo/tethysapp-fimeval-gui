#!/usr/bin/env python
"""Generate the charts embedded in perf-profiling-findings.md (FIMEVAL-PERF-1).

Run from the repo root:  python docs/specs/perf-findings-charts.py
Writes PNGs into docs/specs/img/perf/. All numbers come from the profiling runs
recorded in the findings doc; edit here and re-run to refresh the figures.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(__file__), "img", "perf")
os.makedirs(OUT, exist_ok=True)

# Method palette, consistent across figures
C = {"Intersection": "#E74C3C", "Bootstrap": "#F39C12", "AOI": "#2ECC71"}
CEILING = 15.6  # GiB — WSL2 memory limit on the test box


def save(fig, name):
    fig.tight_layout()
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


# ---------------------------------------------------------------------------
# 1. Phase breakdown of a single run — download / compute / upload (sequential)
# ---------------------------------------------------------------------------
methods = ["Intersection", "Bootstrap", "AOI"]
download = [0.9, 0.1, 0.9]
compute = [74.4, 53.6, 55.9]
upload = [1.1, 2.1, 0.7]

fig, ax = plt.subplots(figsize=(9, 3.6))
ax.barh(methods, download, color="#5DADE2", label="download inputs")
ax.barh(methods, compute, left=download, color="#34495E", label="fimeval.EvaluateFIM (compute)")
ax.barh(methods, upload, left=[d + c for d, c in zip(download, compute)],
        color="#95A5A6", label="upload outputs")
for i, (d, c, u) in enumerate(zip(download, compute, upload)):
    total = d + c + u
    ax.text(total + 1, i, f"{c/total*100:.0f}% compute", va="center", fontsize=9)
ax.set_xlabel("seconds")
ax.set_title("Where a single run's time goes — compute dominates, plumbing is negligible")
ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
ax.set_xlim(0, 90)
save(fig, "phase_breakdown.png")

# ---------------------------------------------------------------------------
# 2. Sequential vs concurrent compute time (fimeval.EvaluateFIM)
# ---------------------------------------------------------------------------
seq = [74.4, 53.6, 55.9]
conc = [142.3, 134.1, 78.0]
x = range(len(methods))
w = 0.38

fig, ax = plt.subplots(figsize=(8, 4.6))
b1 = ax.bar([i - w / 2 for i in x], seq, w, label="run alone (sequential)", color="#7FB3D5")
b2 = ax.bar([i + w / 2 for i in x], conc, w, label="3 jobs at once (concurrent)", color="#C0392B")
ax.bar_label(b1, fmt="%.0fs", padding=2, fontsize=8)
ax.bar_label(b2, fmt="%.0fs", padding=2, fontsize=8)
ax.set_xticks(list(x))
ax.set_xticklabels(methods)
ax.set_ylabel("fimeval.EvaluateFIM time (seconds)")
ax.set_title("Concurrency ~doubles compute time (Python GIL serialization)")
ax.legend()
ax.set_ylim(0, 165)
ax.text(0.99, 0.02, "AOI only partly overlapped the others, so its increase is smaller",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=7, style="italic", color="#555")
save(fig, "seq_vs_concurrent_time.png")

# ---------------------------------------------------------------------------
# 3. Peak memory per single job vs the machine ceiling
# ---------------------------------------------------------------------------
labels = ["Intersection\nTier_2", "Bootstrap\nTier_2", "AOI\nTier 2",
          "AOI\nTier_1", "Intersection\nTier_1"]
mem = [4.52, 4.52, 4.10, 2.90, 2.90]
colors = [C["Intersection"], C["Bootstrap"], C["AOI"], C["AOI"], C["Intersection"]]

fig, ax = plt.subplots(figsize=(9, 4.8))
bars = ax.bar(labels, mem, color=colors)
ax.bar_label(bars, fmt="%.2f GB", padding=3, fontsize=9)
ax.axhline(CEILING, color="#C0392B", ls="--", lw=1.5)
ax.text(len(labels) - 0.5, CEILING - 0.7, f"machine memory ceiling = {CEILING} GiB",
        ha="right", color="#C0392B", fontsize=9, fontweight="bold")
ax.set_ylabel("peak RAM for one job (GB)")
ax.set_title("A single heavy job uses only 3–4.5 GB — far below the ceiling")
ax.set_ylim(0, 16.5)
save(fig, "peak_memory.png")

# ---------------------------------------------------------------------------
# 4. Why concurrency causes OOM — memory stacks in one worker process
# ---------------------------------------------------------------------------
n = [1, 2, 3, 4, 5]
per_job = 4.5   # worst single-job peak (GB)
baseline = 1.0  # interpreter + worker overhead
worker = [baseline + per_job * k for k in n]
# with the web server buffering a ~1.14 GB upload at the same time
with_upload = [w + 1.7 for w in worker]

fig, ax = plt.subplots(figsize=(8.5, 4.8))
ax.axhspan(CEILING, 26, color="#E74C3C", alpha=0.10)
ax.axhline(CEILING, color="#C0392B", ls="--", lw=1.5, label=f"OOM ceiling ({CEILING} GiB)")
ax.plot(n, worker, "o-", color="#34495E", label="worker only (N heavy jobs)")
ax.plot(n, with_upload, "s--", color="#E67E22", label="worker + web server staging a large upload")
ax.text(4.05, 26, "OOM ZONE — kernel SIGKILLs a process", color="#C0392B",
        fontsize=9, fontweight="bold", va="top")
ax.set_xticks(n)
ax.set_xlabel("concurrent heavy jobs in the single Dask worker process")
ax.set_ylabel("total process memory (GB)")
ax.set_title("Peak memory stacks with concurrency → crosses the ceiling at ~3–4 jobs")
ax.legend(loc="upper left", fontsize=8)
ax.set_ylim(0, 26)
save(fig, "memory_vs_concurrency.png")

print("done")
