#!/usr/bin/env python3
"""
analyze_results.py  —  generates all plots for the report.

Outputs (in plots/)
-------------------
  memory_bar.png          grouped bar: peak memory by variant & size
  wall_time_bar.png       grouped bar: wall time by variant & size
  cpu_time_bar.png        grouped bar: CPU time by variant & size
  load_memory_bar.png     grouped bar: post-load memory (data-loading stage)
  memory_boxplot.png      box plot: peak memory run distribution
  wall_time_boxplot.png   box plot: wall time run distribution
  reduction_pct.png       horizontal bar: % reduction vs baseline
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE        = Path(__file__).parent
RESULTS_DIR = HERE / "results"
PLOTS_DIR   = HERE / "plots"

PAL = {"baseline": "#e74c3c", "optimized": "#27ae60"}
LAB = {"baseline": "Baseline", "optimized": "Optimised"}


def _save(fig, name):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOTS_DIR / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[plots] {PLOTS_DIR/name}")


def bar_chart(summ, mean_col, std_col, ylabel, title, fname):
    variants = summ["variant"].unique()
    sizes    = sorted(summ["input_size_mb"].unique())
    x, w     = np.arange(len(sizes)), 0.35
    fig, ax  = plt.subplots(figsize=(7, 4))
    for i, v in enumerate(variants):
        sub = summ[summ["variant"] == v].set_index("input_size_mb")
        means = [float(sub.loc[s, mean_col]) if s in sub.index else 0 for s in sizes]
        stds  = [float(sub.loc[s, std_col])  if s in sub.index else 0 for s in sizes]
        ax.bar(x + (i - .5) * w, means, w * .9,
               label=LAB.get(v, v), color=PAL.get(v, "grey"),
               yerr=stds, capsize=4, error_kw={"elinewidth": 1})
    ax.set_xticks(x); ax.set_xticklabels([f"{s} MB" for s in sizes])
    ax.set_xlabel("Input size"); ax.set_ylabel(ylabel); ax.set_title(title)
    ax.legend(); ax.yaxis.grid(True, linestyle="--", alpha=.5); ax.set_axisbelow(True)
    _save(fig, fname)


def box_plot(df, col, ylabel, title, fname):
    variants = df["variant"].unique()
    sizes    = sorted(df["input_size_mb"].unique())
    fig, axes = plt.subplots(1, len(sizes), figsize=(5*len(sizes), 4), sharey=True)
    if len(sizes) == 1: axes = [axes]
    for ax, s in zip(axes, sizes):
        sub  = df[df["input_size_mb"] == s]
        data = [sub[sub["variant"] == v][col].dropna().tolist() for v in variants]
        bp   = ax.boxplot(data, tick_labels=[LAB.get(v,v) for v in variants],
                          patch_artist=True,
                          medianprops={"color": "black", "linewidth": 2})
        for patch, v in zip(bp["boxes"], variants):
            patch.set_facecolor(PAL.get(v, "grey")); patch.set_alpha(.7)
        ax.set_title(f"{s} MB"); ax.yaxis.grid(True, linestyle="--", alpha=.5)
        ax.set_axisbelow(True)
    fig.suptitle(title, fontsize=12); axes[0].set_ylabel(ylabel)
    _save(fig, fname)


def reduction_chart(summ):
    metrics = [("peak_mem_mean_mb", "Peak memory"),
               ("wall_mean_s",      "Wall time"),
               ("cpu_mean_s",       "CPU time")]
    sizes = sorted(summ["input_size_mb"].unique())
    for size in sizes:
        b = summ[(summ["variant"]=="baseline")  & (summ["input_size_mb"]==size)]
        o = summ[(summ["variant"]=="optimized") & (summ["input_size_mb"]==size)]
        if b.empty or o.empty: continue
        labels, pcts = [], []
        for col, label in metrics:
            bv = float(b.iloc[0][col]) if b.iloc[0][col] != "" else None
            ov = float(o.iloc[0][col]) if o.iloc[0][col] != "" else None
            if bv and ov and bv > 0:
                labels.append(label); pcts.append((bv - ov) / bv * 100)
        if not labels: continue
        fig, ax = plt.subplots(figsize=(7, 3))
        colors  = ["#27ae60" if p >= 0 else "#e74c3c" for p in pcts]
        bars    = ax.barh(labels, pcts, color=colors, edgecolor="white")
        ax.axvline(0, color="black", lw=.8)
        ax.set_xlabel("Reduction vs baseline (%)")
        ax.set_title(f"Optimised improvement — {size} MB input")
        for bar, val in zip(bars, pcts):
            ax.text(val + .5, bar.get_y() + bar.get_height()/2,
                    f"{val:.1f}%", va="center", fontsize=10)
        ax.set_xlim(-5, max(pcts) + 15)
        _save(fig, f"reduction_pct_{size}mb.png")


def main():
    rp = RESULTS_DIR / "benchmark_results.csv"
    sp = RESULTS_DIR / "benchmark_summary.csv"
    if not rp.exists():
        print("No results yet — run benchmark.py first."); sys.exit(1)

    df   = pd.read_csv(rp)
    summ = pd.read_csv(sp)

    bar_chart(summ, "peak_mem_mean_mb", "peak_mem_std_mb",
              "Peak memory (MB)", "Peak memory by variant & input size", "memory_bar.png")
    bar_chart(summ, "load_mem_mean_mb", "load_mem_std_mb",
              "Memory after load (MB)", "Post-load DataFrame memory", "load_memory_bar.png")
    bar_chart(summ, "wall_mean_s", "wall_std_s",
              "Wall time (s)", "Wall time by variant & input size", "wall_time_bar.png")
    if summ["cpu_mean_s"].replace("", np.nan).dropna().any():
        bar_chart(summ, "cpu_mean_s", "cpu_std_s",
                  "CPU time (s)", "CPU time by variant & input size", "cpu_time_bar.png")
    box_plot(df, "peak_memory_mb", "Peak memory (MB)",
             "Peak memory distribution", "memory_boxplot.png")
    box_plot(df, "wall_time_s", "Wall time (s)",
             "Wall time distribution", "wall_time_boxplot.png")
    reduction_chart(summ)
    print("[plots] All done →", PLOTS_DIR)


if __name__ == "__main__":
    main()
