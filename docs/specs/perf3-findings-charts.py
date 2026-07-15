#!/usr/bin/env python
"""Generate the charts embedded in desktop-app-comparison-findings.md (FIMEVAL-PERF-3).

Run from the repo root:  python docs/specs/perf3-findings-charts.py
Writes PNGs into docs/specs/img/perf3/. All numbers come from the profiling runs
recorded in the findings doc; edit here and re-run to refresh the figures.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = os.path.join(os.path.dirname(__file__), "img", "perf3")
os.makedirs(OUT, exist_ok=True)

# Categorical palette, one color per *configuration* (validated: lightness band,
# chroma floor, CVD separation, contrast — all pass on a light surface).
C_WEB     = "#2980B9"   # A — web worker config, fimeval 0.1.64
C_DESKCFG = "#16A085"   # B — desktop config (target_res=10) on fimeval 0.1.64
C_DESKTOP = "#C0392B"   # C — desktop app as-shipped: fimeval 0.1.62 + target_res=10
INK = "#333333"


def save(fig, name):
    fig.tight_layout()
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


# ---------------------------------------------------------------------------
# 1. Serial head-to-head: peak RAM and wall time, per method x config
#    (Tier_2 for Intersection/Bootstrap, For_AOI/Tier_1 for AOI; /usr/bin/time -v)
# ---------------------------------------------------------------------------
methods = ["Intersection", "Bootstrap", "AOI"]
mem = {  # peak RSS, GB
    "A": [4.52, 4.52, 2.90],
    "B": [4.52, 4.52, 2.90],
    "C": [5.75, 5.75, 2.90],
}
wall = {  # EvaluateFIM wall seconds
    "A": [46.2, 41.0, 60.9],
    "B": [39.4, 41.1, 51.3],
    "C": [50.6, 83.8, 51.1],
}
LABELS = {
    "A": "Web app config (fimeval 0.1.64)",
    "B": "Desktop config on 0.1.64 (+ target_res=10 m)",
    "C": "Desktop as-shipped (fimeval 0.1.62 + target_res=10 m)",
}
COLORS = {"A": C_WEB, "B": C_DESKCFG, "C": C_DESKTOP}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
x = np.arange(len(methods))
w = 0.26

for ax, data, unit, fmt in [(ax1, mem, "peak RAM (GB)", "%.2f"),
                            (ax2, wall, "EvaluateFIM wall time (s)", "%.0f")]:
    for i, key in enumerate("ABC"):
        b = ax.bar(x + (i - 1) * w, data[key], w * 0.92,
                   color=COLORS[key], label=LABELS[key])
        ax.bar_label(b, fmt=fmt, padding=2, fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel(unit)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)

ax1.set_ylim(0, 7.0)
ax1.set_title("Desktop as-shipped needs MORE memory (+1.2 GB)\n"
              "— and target_res=10 changes nothing (A ≡ B)", fontsize=10.5)
ax2.set_ylim(0, 118)
ax2.set_title("…and its bootstrap is ≥2× slower\n"
              "(0.1.62 masking flow; repeat run: 102 s)", fontsize=10.5)
ax2.annotate("repeat: 101.5 s", xy=(1 + w, 84), xytext=(1.42, 100),
             fontsize=8, color=C_DESKTOP,
             arrowprops=dict(arrowstyle="->", color=C_DESKTOP, lw=1))

handles, labels = ax1.get_legend_handles_labels()
fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8.5,
           frameon=False, bbox_to_anchor=(0.5, -0.06))
fig.suptitle("Serial head-to-head on identical data: the Desktop app has no per-job advantage",
             fontsize=12, y=1.03)
save(fig, "serial_head_to_head.png")

# ---------------------------------------------------------------------------
# 2. The real difference: what each deployment lets stack up in RAM
# ---------------------------------------------------------------------------
CEILING = 15.6          # WSL2 RAM, GiB (perf-1)
SERVER = 2.0            # web server / rest-of-system share while jobs run
JOB_WEB = 4.52          # per-job peak, web config (this report)
JOB_DESK = 5.75         # per-job peak, desktop as-shipped (this report)

fig, ax = plt.subplots(figsize=(9.5, 4.8))
scenarios = [
    ("Desktop app\n(Busy dialog:\n1 job, ever)",       [JOB_DESK], C_DESKTOP),
    ("Web app today\n(unbounded, shared\nworker process)", [JOB_WEB] * 3, C_WEB),
    ("Web app, bounded pool\n(2 workers × 1 thread ×\n~5 GB limit)", [JOB_WEB] * 2, C_DESKCFG),
]
for xi, (name, jobs, color) in enumerate(scenarios):
    bottom = 0.0
    for j, sz in enumerate(jobs):
        ax.bar(xi, sz, 0.5, bottom=bottom, color=color,
               edgecolor="white", linewidth=1.6)
        ax.text(xi, bottom + sz / 2, f"job {j+1}: {sz:.2f}", ha="center",
                va="center", fontsize=8, color="white", fontweight="bold")
        bottom += sz
    # the web server / OS share rides on top of every scenario
    ax.bar(xi, SERVER, 0.5, bottom=bottom, color="#B0B7BD",
           edgecolor="white", linewidth=1.6)
    ax.text(xi, bottom + SERVER / 2, "server/OS ≈2", ha="center", va="center",
            fontsize=7.5, color=INK)
    total = bottom + SERVER
    ax.text(xi, total + 0.35, f"{total:.1f} GB", ha="center", fontsize=10,
            fontweight="bold", color=INK)

ax.axhline(CEILING, color=INK, ls="--", lw=1.3)
ax.text(2.62, CEILING + 0.25, "WSL2 RAM: 15.6 GiB", fontsize=9, color=INK,
        ha="right")
ax.annotate("kernel OOM-killer\nterritory (perf-1 §3.5)",
            xy=(1, 15.55), xytext=(1.62, 13.2), fontsize=8.5, color=C_WEB,
            arrowprops=dict(arrowstyle="->", color=C_WEB, lw=1))

ax.set_xticks(range(3))
ax.set_xticklabels([s[0] for s in scenarios], fontsize=9)
ax.set_ylabel("resident RAM while heavy jobs run (GB)")
ax.set_ylim(0, 18.4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", color="#dddddd", lw=0.6)
ax.set_axisbelow(True)
ax.set_title("The Desktop app's only advantage is that it forbids concurrency —\n"
             "a bounded worker pool beats it on throughput at the same safety",
             fontsize=11)
save(fig, "oom_mechanism.png")

print("done")
