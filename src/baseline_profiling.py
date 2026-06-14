#!/usr/bin/env python3
"""
baseline_profiling.py
---------------------
BASELINE: runs ydata-profiling with the default (inefficient) data-loading
pattern — pd.read_csv() with no dtype hints and no column subsetting.

Anti-patterns demonstrated
--------------------------
1. pd.read_csv() with no dtype= argument:
     - All integer columns → int64   (8 bytes/value)
     - All float columns   → float64 (8 bytes/value)
     - All string columns  → object  (Python str heap objects, ~50 bytes each)
       e.g. 'method' has only 4 unique values but stores a full string object
       per row — equivalent to storing an 8-MB dictionary in a 4-entry enum slot.

2. No usecols= filter:
     - 'ip_address' and 'session_id' (high-cardinality, not profiled usefully)
       are decoded and stored in RAM even though they add no analytical value.

3. All 10 columns passed to ProfileReport → triggers correlation computation
   across every column pair, including the redundant high-cardinality ones.

Measurements captured
---------------------
  tracemalloc  → peak RSS (MB)
  perf_counter → wall-clock time (s)
  psutil       → user+sys CPU time (s)
"""

import argparse
import os
import sys
import time
import tracemalloc

import pandas as pd

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    from ydata_profiling import ProfileReport
    _PROFILING = True
except ImportError:
    print("[baseline] ydata-profiling not installed. Run: pip install ydata-profiling")
    _PROFILING = False


def run(input_path: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    # ── start measurements ──────────────────────────────────────────────────
    tracemalloc.start()
    t0 = time.perf_counter()
    cpu0 = None
    if _PSUTIL:
        ct   = psutil.Process().cpu_times()
        cpu0 = ct.user + ct.system

    # ── step 1: load CSV with ALL defaults (anti-pattern) ───────────────────
    df = pd.read_csv(input_path)          # object, float64, int64 everywhere

    mem_after_load_mb = tracemalloc.get_traced_memory()[0] / 1024 / 1024

    # ── step 2: pass full DataFrame to ProfileReport (all 10 columns) ───────
    if _PROFILING:
        profile = ProfileReport(
            df,
            title="Baseline Profile",
            explorative=True,           # full correlation + distribution pass
        )
        profile.to_file(os.path.join(output_dir, "baseline_report.html"))
    else:
        # fallback: just do the expensive groupby/describe pass manually
        _ = df.describe(include="all")
        _ = df.select_dtypes("object").apply(lambda c: c.value_counts())

    # ── stop measurements ───────────────────────────────────────────────────
    t1                  = time.perf_counter()
    _, peak             = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cpu1 = None
    if _PSUTIL:
        ct   = psutil.Process().cpu_times()
        cpu1 = ct.user + ct.system

    results = {
        "variant":           "baseline",
        "n_rows":            len(df),
        "n_cols":            len(df.columns),
        "wall_time_s":       round(t1 - t0, 4),
        "peak_memory_mb":    round(peak / 1024 / 1024, 2),
        "mem_after_load_mb": round(mem_after_load_mb, 2),
        "cpu_time_s":        round(cpu1 - cpu0, 4) if cpu0 is not None else None,
    }
    return results


def main():
    p = argparse.ArgumentParser(description="Baseline ydata-profiling run.")
    p.add_argument("--input",  default=os.path.join(
        os.path.dirname(__file__), "data", "logs_20mb.csv"))
    p.add_argument("--output-dir", default=os.path.join(
        os.path.dirname(__file__), "results"))
    a = p.parse_args()

    print(f"[baseline] input={a.input}")
    r = run(a.input, a.output_dir)
    print(f"  rows={r['n_rows']:,}  cols={r['n_cols']}")
    print(f"  wall time    : {r['wall_time_s']:.3f} s")
    print(f"  peak memory  : {r['peak_memory_mb']:.1f} MB")
    print(f"  load memory  : {r['mem_after_load_mb']:.1f} MB")
    if r["cpu_time_s"]:
        print(f"  CPU time     : {r['cpu_time_s']:.3f} s")
    return r


if __name__ == "__main__":
    main()
