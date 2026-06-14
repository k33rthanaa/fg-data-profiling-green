#!/usr/bin/env python3
"""Probe extra optimisation levers on top of the dtype+usecols optimized load.
One config per invocation (fresh process). Always uses the optimized load."""
import sys, time, os, tracemalloc, threading, argparse, warnings, json
warnings.filterwarnings("ignore")
import psutil, pandas as pd
from ydata_profiling import ProfileReport

DTYPE_MAP = {"status_code": "int16", "response_time_ms": "float32", "bytes_sent": "int32",
             "method": "category", "region": "category", "user_agent": "category",
             "endpoint": "category"}
USECOLS = ["timestamp", "method", "endpoint", "status_code", "response_time_ms",
           "bytes_sent", "region"]

def _samp(proc, stop, peak):
    while not stop.is_set():
        try: peak[0] = max(peak[0], proc.memory_info().rss)
        except Exception: pass
        time.sleep(0.01)

def build(df, config):
    if config == "full":            # current optimized baseline-of-comparison
        return ProfileReport(df, explorative=True, progress_bar=False), "file"
    if config == "no_interactions": # drop O(n^2) scatter interactions
        return ProfileReport(df, explorative=True, interactions=None, progress_bar=False), "file"
    if config == "lean_corr":       # keep only pearson; drop spearman/kendall/cramers/phi_k/auto
        corr = {k: {"calculate": False} for k in ["auto","spearman","kendall","cramers","phi_k"]}
        corr["pearson"] = {"calculate": True}
        return ProfileReport(df, explorative=True, interactions=None,
                             correlations=corr, progress_bar=False), "file"
    if config == "minimal":         # library minimal preset
        return ProfileReport(df, minimal=True, progress_bar=False), "file"
    if config == "stats_json":      # CI/CD path: stats only, no HTML render
        return ProfileReport(df, minimal=True, interactions=None, progress_bar=False), "json"
    raise SystemExit("bad config")

def run(path, config):
    proc = psutil.Process(); peak = [proc.memory_info().rss]
    stop = threading.Event(); th = threading.Thread(target=_samp, args=(proc, stop, peak), daemon=True); th.start()
    ct = proc.cpu_times(); cpu0 = ct.user + ct.system
    t0 = time.perf_counter(); tracemalloc.start()
    df = pd.read_csv(path, usecols=USECOLS, dtype=DTYPE_MAP, parse_dates=["timestamp"], engine="c")
    prof, mode = build(df, config)
    if mode == "file": prof.to_file(f"/tmp/probe_{config}.html")
    else: _ = prof.to_json()
    tm_peak = tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
    t1 = time.perf_counter(); ct = proc.cpu_times(); cpu1 = ct.user + ct.system
    stop.set(); th.join(timeout=1)
    return {"config": config, "wall_s": round(t1 - t0, 3), "cpu_s": round(cpu1 - cpu0, 3),
            "tm_peak_mb": round(tm_peak / 1e6, 1), "rss_peak_mb": round(peak[0] / 1e6, 1)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    ap.add_argument("--input", default="../group14-project/data/logs_20mb.csv")
    a = ap.parse_args()
    print("PROBE " + json.dumps(run(a.input, a.config)))
