#!/usr/bin/env python3
"""Row-sampling tradeoff: profile a sample of N rows (optimized load, full
explorative report) and measure cost + accuracy vs the full dataset."""
import sys, time, os, tracemalloc, argparse, warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from ydata_profiling import ProfileReport

DTYPE_MAP = {"status_code": "int16", "response_time_ms": "float32", "bytes_sent": "int32",
             "method": "category", "region": "category", "user_agent": "category", "endpoint": "category"}
USECOLS = ["timestamp", "method", "endpoint", "status_code", "response_time_ms", "bytes_sent", "region"]
PATH = "../group14-project/data/logs_20mb.csv"

full = pd.read_csv(PATH, usecols=USECOLS, dtype=DTYPE_MAP, parse_dates=["timestamp"], engine="c")

def keystats(df):
    return {
        "rt_mean": float(df["response_time_ms"].mean()),
        "rt_std": float(df["response_time_ms"].std()),
        "bytes_mean": float(df["bytes_sent"].mean()),
        "error_rate": float((df["status_code"] >= 400).mean()),
        "endpoint_distinct": int(df["endpoint"].nunique()),
        "region_distinct": int(df["region"].nunique()),
    }

REF = keystats(full)

def run(n):
    df = full if n >= len(full) else full.sample(n=n, random_state=42)
    t0 = time.perf_counter(); tracemalloc.start()
    ProfileReport(df, explorative=True, progress_bar=False).to_file(f"/tmp/samp_{n}.html")
    peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
    wall = time.perf_counter() - t0
    st = keystats(df)
    acc = {k: (abs(st[k] - REF[k]) / REF[k] * 100 if REF[k] else 0.0) for k in REF}
    return {"n": len(df), "wall_s": round(wall, 3), "tm_peak_mb": round(peak/1e6, 1),
            "rt_mean_err_pct": round(acc["rt_mean"], 3), "bytes_mean_err_pct": round(acc["bytes_mean"], 3),
            "error_rate_err_pct": round(acc["error_rate"], 3),
            "endpoint_coverage_pct": round(st["endpoint_distinct"]/REF["endpoint_distinct"]*100, 1),
            "region_coverage_pct": round(st["region_distinct"]/REF["region_distinct"]*100, 1)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, required=True); a = ap.parse_args()
    print("SAMP " + json.dumps(run(a.n)))
