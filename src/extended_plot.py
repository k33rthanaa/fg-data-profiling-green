#!/usr/bin/env python3
"""Consolidated figure for the extended optimisation levers (all measured, 20 MB)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RU = "#BE1B28"; GR = "#2E7D32"; BL = "#1565C0"; GY = "#888888"
fig, ax = plt.subplots(2, 2, figsize=(12, 8))

# A: config stacking (wall time, mean of n=3)
labels = ["Baseline\n(default load)", "+dtype/usecols", "+lean corr", "+minimal mode"]
vals = [9.07, 4.61, 3.73, 2.57]
colors = [RU, GR, GR, GR]
b = ax[0,0].bar(labels, vals, color=colors)
for i, v in enumerate(vals):
    red = (vals[0]-v)/vals[0]*100
    ax[0,0].text(i, v+0.1, f"{v:.1f}s" + (f"\n-{red:.0f}%" if i>0 else ""),
                 ha="center", va="bottom", fontsize=9, fontweight="bold")
ax[0,0].set_ylabel("Wall time (s)"); ax[0,0].set_title("A. Stacking config strategies (20 MB)")
ax[0,0].set_ylim(0, 10.5); ax[0,0].grid(axis="y", alpha=0.3)

# B: sampling - memory + accuracy
ns = [10, 25, 50, 100]  # k rows
mem = [21.8, 27.5, 46.7, 84.0]
err = [2.73, 0.39, 0.69, 0.0]  # rt_mean error %
ax2 = ax[0,1]; ax2b = ax2.twinx()
ax2.bar([str(n)+"k" for n in ns], mem, color=BL, alpha=0.7, label="Peak Py mem (MB)")
ax2b.plot([str(n)+"k" for n in ns], err, "o-", color=RU, label="Mean-stat error (%)")
ax2.set_ylabel("Peak Python memory (MB)", color=BL); ax2b.set_ylabel("Key-stat error vs full (%)", color=RU)
ax2.set_xlabel("Sample size (rows)"); ax2.set_title("B. Row sampling: memory vs accuracy")
ax2.grid(axis="y", alpha=0.3)

# C: parquet - load time + disk
cats = ["Load time (s)", "Disk size (MB)"]
csvv = [0.135, 15.26]; parv = [0.007, 2.29]
x = np.arange(len(cats)); w = 0.35
ax[1,0].bar(x-w/2, csvv, w, label="CSV", color=RU)
ax[1,0].bar(x+w/2, parv, w, label="Parquet", color=GR)
for i,(c,p) in enumerate(zip(csvv,parv)):
    ax[1,0].text(i+w/2, p, f"-{(c-p)/c*100:.0f}%", ha="center", va="bottom",
                 fontsize=9, color=GR, fontweight="bold")
ax[1,0].set_xticks(x); ax[1,0].set_xticklabels(cats); ax[1,0].set_yscale("log")
ax[1,0].set_ylabel("value (log scale)"); ax[1,0].set_title("C. CSV vs Parquet (20 MB, load + storage)")
ax[1,0].legend(); ax[1,0].grid(axis="y", alpha=0.3)

# D: caching miss vs hit (log)
ax[1,1].bar(["Cache miss\n(compute)", "Cache hit\n(lookup)"], [1.612, 0.0003],
            color=[RU, GR])
ax[1,1].set_yscale("log"); ax[1,1].set_ylabel("Wall time (s, log)")
ax[1,1].set_title("D. Report caching: 99.98% avoided per hit")
ax[1,1].text(1, 0.0003, "0.3 ms\n5339x faster", ha="center", va="bottom", fontsize=9, fontweight="bold", color=GR)
ax[1,1].grid(axis="y", alpha=0.3)

fig.suptitle("Extended green-software levers for fg-data-profiling (all measured)", fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0,0,1,0.97])
fig.savefig("new_plots/extended_optimizations.png", dpi=130); plt.close(fig)
print("wrote new_plots/extended_optimizations.png")
