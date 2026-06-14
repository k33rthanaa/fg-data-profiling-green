#!/usr/bin/env python3
"""Aggregate results_full.jsonl -> CSVs + plots for the full end-to-end benchmark."""
import json, csv, statistics, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

rows = [json.loads(l) for l in open("results_full.jsonl") if l.strip()]
PLOTS = "new_plots"; os.makedirs(PLOTS, exist_ok=True)

FIELDS = ["wall_s", "cpu_s", "rss_peak_mb", "load_rss_mb", "tm_peak_mb", "load_tm_mb", "energy_kwh"]

# per-run CSV
keys = ["variant", "size_mb", "wall_s", "cpu_s", "rss_peak_mb", "load_rss_mb",
        "tm_peak_mb", "load_tm_mb", "energy_kwh", "n_rows", "n_cols"]
with open("benchmark_results_full.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
    for r in rows: w.writerow({k: r.get(k) for k in keys})

def cell(size, variant):
    return [r for r in rows if r["size_mb"] == size and r["variant"] == variant]

def mean(rs, fld):
    v = [x[fld] for x in rs if x.get(fld) is not None]
    return statistics.mean(v) if v else None
def std(rs, fld):
    v = [x[fld] for x in rs if x.get(fld) is not None]
    return statistics.pstdev(v) if len(v) > 1 else 0.0

sizes = sorted({r["size_mb"] for r in rows})
summary = {}
srows = []
for size in sizes:
    for variant in ["baseline", "optimized"]:
        rs = cell(size, variant)
        d = {"variant": variant, "size_mb": size, "n_runs": len(rs)}
        for fld in FIELDS:
            d[fld + "_mean"] = mean(rs, fld); d[fld + "_std"] = std(rs, fld)
        summary[(size, variant)] = d; srows.append(d)

with open("benchmark_summary_full.csv", "w", newline="") as f:
    sk = ["variant", "size_mb", "n_runs"] + [f + s for f in FIELDS for s in ["_mean", "_std"]]
    w = csv.DictWriter(f, fieldnames=sk); w.writeheader()
    for d in srows: w.writerow(d)

# reductions table
print("=== REDUCTIONS (optimized vs baseline) ===")
red = {}
for size in sizes:
    b, o = summary[(size, "baseline")], summary[(size, "optimized")]
    red[size] = {}
    for fld in FIELDS:
        bm, om = b[fld + "_mean"], o[fld + "_mean"]
        if bm: red[size][fld] = (bm - om) / bm * 100
    print(f"\n-- {size} MB --")
    for fld in FIELDS:
        print(f"  {fld:14s} base={b[fld+'_mean']:.4g}  opt={o[fld+'_mean']:.4g}  "
              f"reduction={red[size].get(fld,0):.1f}%")

# ---- plots ----
RU = "#BE1B28"; GR = "#2E7D32"; x = np.arange(len(sizes)); wdt = 0.36
labels = [f"{s} MB" for s in sizes]

def grouped(field, ylabel, title, fname, scale=1.0):
    bvals = [summary[(s, "baseline")][field + "_mean"] * scale for s in sizes]
    ovals = [summary[(s, "optimized")][field + "_mean"] * scale for s in sizes]
    berr = [summary[(s, "baseline")][field + "_std"] * scale for s in sizes]
    oerr = [summary[(s, "optimized")][field + "_std"] * scale for s in sizes]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x - wdt/2, bvals, wdt, yerr=berr, capsize=4, label="Baseline", color=RU)
    ax.bar(x + wdt/2, ovals, wdt, yerr=oerr, capsize=4, label="Optimised", color=GR)
    for i, s in enumerate(sizes):
        r = red[s].get(field, 0)
        ax.text(x[i] + wdt/2, ovals[i], f"-{r:.0f}%", ha="center", va="bottom",
                fontsize=9, color=GR, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylabel(ylabel)
    ax.set_title(title); ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(f"{PLOTS}/{fname}", dpi=130); plt.close(fig)

grouped("wall_s", "Wall-clock time (s)", "End-to-end wall time (full ProfileReport)", "full_wall_time.png")
grouped("energy_kwh", "Energy (Wh)", "Measured energy per run (CodeCarbon)", "full_energy.png", scale=1000)
grouped("tm_peak_mb", "Python peak memory (MB)", "Peak Python allocation (tracemalloc)", "full_tm_peak.png")
grouped("load_tm_mb", "DataFrame load memory (MB)", "Memory after CSV load", "full_load_memory.png")
grouped("rss_peak_mb", "Process peak RSS (MB)", "Peak process RSS (incl. report-gen)", "full_rss_peak.png")

# scaling line: wall vs size
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(sizes, [summary[(s, "baseline")]["wall_s_mean"] for s in sizes], "o-", color=RU, label="Baseline")
ax.plot(sizes, [summary[(s, "optimized")]["wall_s_mean"] for s in sizes], "s-", color=GR, label="Optimised")
ax.set_xlabel("Input size (MB)"); ax.set_ylabel("Wall-clock time (s)")
ax.set_title("Scaling: optimised grows far slower with input size")
ax.legend(); ax.grid(alpha=0.3); fig.tight_layout()
fig.savefig(f"{PLOTS}/full_scaling.png", dpi=130); plt.close(fig)

# reduction % grouped by size
fig, ax = plt.subplots(figsize=(7, 4))
metrics = ["wall_s", "energy_kwh", "tm_peak_mb", "load_tm_mb"]
mlabels = ["Wall time", "Energy", "Py peak mem", "Load mem"]
xm = np.arange(len(metrics))
for i, s in enumerate(sizes):
    vals = [red[s].get(m, 0) for m in metrics]
    ax.bar(xm + (i - 0.5) * wdt, vals, wdt, label=f"{s} MB")
ax.set_xticks(xm); ax.set_xticklabels(mlabels); ax.set_ylabel("Reduction vs baseline (%)")
ax.set_title("Percentage reduction by metric and input size")
ax.legend(); ax.grid(axis="y", alpha=0.3); fig.tight_layout()
fig.savefig(f"{PLOTS}/full_reduction_pct.png", dpi=130); plt.close(fig)

print("\nWrote benchmark_results_full.csv, benchmark_summary_full.csv, and", len(os.listdir(PLOTS)), "plots in", PLOTS)
