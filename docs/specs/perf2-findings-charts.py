#!/usr/bin/env python
"""Generate the charts embedded in fimeval-optimization-findings.md (FIMEVAL-PERF-2).

Run from the repo root:  python docs/specs/perf2-findings-charts.py
Writes PNGs into docs/specs/img/perf2/. All numbers come from the profiling runs
recorded in the findings doc; edit here and re-run to refresh the figures.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(__file__), "img", "perf2")
os.makedirs(OUT, exist_ok=True)


def save(fig, name):
    fig.tight_layout()
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


# ---------------------------------------------------------------------------
# 1. Phase breakdown per heavy method — it's all preprocessing
#    (measured phases; the network PWB step was bypassed and measured
#    separately at ~10.5s)
# ---------------------------------------------------------------------------
methods = ["Intersection\n(60.3s)", "Bootstrap\n(60.7s)", "AOI\n(53.4s)"]
warp = [50.9, 44.8, 44.0]
resample = [2.4, 2.4, 2.3]
pre_other = [6.5, 6.9, 6.8]          # MakeFIMsUniform minus warp/resample (incl. compress)
method_t = [0.2, 0.5, 0.1]
sampling = [0.0, 5.5, 0.0]
eval_other = [0.3, 0.6, 0.2]

fig, ax = plt.subplots(figsize=(9.5, 4.0))
left = [0.0] * 3
for vals, label, color in [
    (warp, "CRS warp (reprojectFIMs)", "#34495E"),
    (resample, "resample to coarsest", "#5DADE2"),
    (pre_other, "preprocess other (incl. compress)", "#85929E"),
    (method_t, "the method itself", "#E74C3C"),
    (sampling, "bootstrap sampling", "#F39C12"),
    (eval_other, "eval other (align/mask/metrics)", "#2ECC71"),
]:
    ax.barh(methods, vals, left=left, color=color, label=label)
    left = [l + v for l, v in zip(left, vals)]
for i, tot in enumerate(left):
    m = method_t[i] + sampling[i]
    ax.text(tot + 0.8, i, f"method = {m/tot*100:.0f}%", va="center", fontsize=9)
ax.set_xlabel("seconds")
ax.set_title('The "heavy" methods are ~all preprocessing — the method itself is ≤1%\n'
             "(bootstrap adds ~9% sampling)", fontsize=11)
ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
ax.set_xlim(0, 68)
save(fig, "phase_breakdown_methods.png")

# ---------------------------------------------------------------------------
# 2. The fix, measured — two-step vs single-pass warp (time + peak memory)
# ---------------------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.2))

labels = ["two-step\n(fimeval today)", "single-pass\n(proposed)"]
colors = ["#C0392B", "#27AE60"]

b = ax1.bar(labels, [45.6, 8.7], color=colors)
ax1.bar_label(b, fmt="%.1fs", padding=3, fontsize=10)
ax1.set_ylabel("preprocess time per raster (seconds)")
ax1.set_title("5.2× faster", fontsize=11)
ax1.set_ylim(0, 52)
ax1.annotate("warps a 1.71-BILLION-pixel\nintermediate, then discards\n99.8% of it",
             xy=(0.25, 40), xytext=(0.42, 40), fontsize=8, color="#C0392B",
             va="center",
             arrowprops=dict(arrowstyle="->", color="#C0392B", lw=1))
ax1.annotate("warps directly onto the\n3.5M-pixel final grid",
             xy=(1, 10.5), xytext=(0.55, 21), fontsize=8, color="#27AE60",
             arrowprops=dict(arrowstyle="->", color="#27AE60", lw=1))

b2 = ax2.bar(labels, [1.09, 0.93], color=colors)
ax2.bar_label(b2, fmt="%.2f GB", padding=3, fontsize=10)
ax2.axhline(2.93, color="#C0392B", ls="--", lw=1.2)
ax2.text(1.45, 2.83, "2.93 GB peak in the full fimeval pipeline\n"
         "(compress_tif_lzw reads the giant\nintermediate whole, twice)",
         ha="right", va="top", fontsize=8, color="#C0392B")
ax2.set_ylabel("peak RAM (GB)")
ax2.set_title("…and removes the memory spike", fontsize=11)
ax2.set_ylim(0, 3.3)

fig.suptitle("Proof of fix: reproject straight to the final coarse grid "
             "(same result to 0.003%)", fontsize=12, y=1.02)
save(fig, "warp_fix_measured.png")

# ---------------------------------------------------------------------------
# 3. Level-2 (multi-candidate) scaling — time linear, memory flat
# ---------------------------------------------------------------------------
n = [1, 2, 3]
wall = [60.3, 126.1, 167.1]
mem = [2.93, 2.93, 2.93]

fig, ax = plt.subplots(figsize=(8.5, 4.6))
ax.plot(n, wall, "o-", color="#34495E", lw=2, ms=8, label="wall time (s)")
for x, y in zip(n, wall):
    ax.annotate(f"{y:.0f}s", (x, y), textcoords="offset points", xytext=(0, 9),
                ha="center", fontsize=9)
ax.set_xlabel("benchmark-sized candidate rasters in the case study")
ax.set_ylabel("wall time (seconds)", color="#34495E")
ax.set_xticks(n)
ax.set_ylim(0, 190)

ax2 = ax.twinx()
ax2.plot(n, mem, "s--", color="#27AE60", lw=2, ms=8, label="peak RAM (GB)")
ax2.set_ylabel("peak RAM (GB)", color="#27AE60")
ax2.set_ylim(0, 16)
ax2.annotate("memory FLAT at 2.93 GB — warps run sequentially;\n"
             "multi-candidate does NOT raise the memory ceiling",
             xy=(2, 2.93), xytext=(1.25, 6.2), fontsize=9, color="#27AE60",
             arrowprops=dict(arrowstyle="->", color="#27AE60", lw=1))
ax.annotate("time LINEAR — one full warp per raster\n(the single-pass fix pays (N+1)× here)",
            xy=(2.5, 147), xytext=(1.05, 158), fontsize=9, color="#34495E",
            arrowprops=dict(arrowstyle="->", color="#34495E", lw=1))
ax.set_title("Level-2 scaling (Intersection, end-to-end): time grows linearly, memory doesn't")

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, loc="lower right", fontsize=9)
save(fig, "level2_scaling.png")

print("done")
