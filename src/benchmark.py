#!/usr/bin/env python3
"""
benchmark.py
------------
Orchestrates repeated benchmark runs of baseline_profiling and
optimized_profiling, captures measurements, and writes results to CSV.

Usage
-----
    python benchmark.py --size 20 --runs 5
    python benchmark.py --size 20 100 500 --runs 10

Output
------
    results/benchmark_results.csv   — one row per (variant, size, run)
    results/benchmark_summary.csv   — mean ± std per (variant, size)
"""

import argparse
import csv
import gc
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE        = Path(__file__).parent
DATA_DIR    = HERE / "data"
RESULTS_DIR = HERE / "results"

sys.path.insert(0, str(HERE))
import generate_dataset
import baseline_profiling
import optimized_profiling


def csv_path(mb: int) -> Path:
    return DATA_DIR / f"logs_{mb}mb.csv"


def run_experiment(input_path: str, size_mb: int, n_runs: int) -> list:
    rows = []
    for variant, fn in [("baseline",  baseline_profiling.run),
                        ("optimized", optimized_profiling.run)]:
        print(f"\n{'='*55}")
        print(f"  {variant.upper()}  |  {size_mb} MB  |  {n_runs} runs")
        print(f"{'='*55}")
        for i in range(1, n_runs + 1):
            gc.collect()
            time.sleep(0.3)
            print(f"  run {i}/{n_runs} ...", end=" ", flush=True)
            r = fn(input_path, str(RESULTS_DIR))
            print(f"wall={r['wall_time_s']:.2f}s  "
                  f"mem={r['peak_memory_mb']:.1f}MB")
            rows.append({
                "variant":        variant,
                "input_size_mb":  size_mb,
                "run":            i,
                "wall_time_s":    r["wall_time_s"],
                "peak_memory_mb": r["peak_memory_mb"],
                "load_memory_mb": r["mem_after_load_mb"],
                "cpu_time_s":     r["cpu_time_s"] or "",
            })
    return rows


def summarise(all_rows: list) -> list:
    from collections import defaultdict
    groups = defaultdict(list)
    for r in all_rows:
        groups[(r["variant"], r["input_size_mb"])].append(r)

    out = []
    for (variant, size), rows in sorted(groups.items()):
        def stat(col):
            vals = [float(r[col]) for r in rows if r[col] != ""]
            return (round(np.mean(vals), 4), round(np.std(vals, ddof=1), 4)) \
                if vals else ("", "")
        wm, ws   = stat("wall_time_s")
        mm, ms   = stat("peak_memory_mb")
        lm, ls   = stat("load_memory_mb")
        cm, cs   = stat("cpu_time_s")
        out.append({"variant": variant, "input_size_mb": size,
                    "n_runs": len(rows),
                    "wall_mean_s": wm, "wall_std_s": ws,
                    "peak_mem_mean_mb": mm, "peak_mem_std_mb": ms,
                    "load_mem_mean_mb": lm, "load_mem_std_mb": ls,
                    "cpu_mean_s": cm, "cpu_std_s": cs})
    return out


def save_csv(rows, path):
    if not rows: return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"[benchmark] → {path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size",  nargs="+", type=int, default=[20], metavar="MB")
    p.add_argument("--runs",  type=int, default=5)
    p.add_argument("--no-generate", action="store_true")
    a = p.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not a.no_generate:
        for mb in a.size:
            p_ = csv_path(mb)
            if p_.exists():
                print(f"[benchmark] {p_.name} exists, skipping generation.")
            else:
                generate_dataset.generate(mb, str(p_))

    all_rows = []
    for mb in a.size:
        p_ = csv_path(mb)
        if not p_.exists():
            print(f"[benchmark] {p_} not found, skipping."); continue
        all_rows.extend(run_experiment(str(p_), mb, a.runs))

    save_csv(all_rows, RESULTS_DIR / "benchmark_results.csv")
    summ = summarise(all_rows)
    save_csv(summ, RESULTS_DIR / "benchmark_summary.csv")

    print("\n── Summary " + "─"*45)
    print(f"{'variant':<12} {'MB':>4} {'wall(s)':>12} {'mem(MB)':>12} {'cpu(s)':>10}")
    print("─" * 52)
    for s in summ:
        wt  = f"{s['wall_mean_s']:.2f}±{s['wall_std_s']:.2f}"
        mem = f"{s['peak_mem_mean_mb']:.1f}±{s['peak_mem_std_mb']:.1f}"
        cpu = f"{s['cpu_mean_s']:.2f}±{s['cpu_std_s']:.2f}" \
              if s['cpu_mean_s'] != "" else "N/A"
        print(f"{s['variant']:<12} {s['input_size_mb']:>4} {wt:>12} {mem:>12} {cpu:>10}")


if __name__ == "__main__":
    main()
