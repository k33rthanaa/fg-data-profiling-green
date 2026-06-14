#!/usr/bin/env python3
"""Content-hash report cache: in CI/CD the same file is often re-profiled
unchanged. Hash the input; on a cache hit, return the stored report and skip
all compute. Measures cache-miss (compute) vs cache-hit (lookup) cost."""
import time, os, hashlib, shutil, warnings, json, tracemalloc
warnings.filterwarnings("ignore")
import pandas as pd
from ydata_profiling import ProfileReport

DTYPE_MAP = {"status_code": "int16", "response_time_ms": "float32", "bytes_sent": "int32",
             "method": "category", "region": "category", "user_agent": "category", "endpoint": "category"}
USECOLS = ["timestamp", "method", "endpoint", "status_code", "response_time_ms", "bytes_sent", "region"]
PATH = "../group14-project/data/logs_20mb.csv"
CACHE = "/tmp/report_cache"; os.makedirs(CACHE, exist_ok=True)

def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def profile_cached(path, out):
    key = file_hash(path)
    cached = os.path.join(CACHE, key + ".html")
    t0 = time.perf_counter()
    if os.path.exists(cached):           # HIT: skip all compute
        shutil.copy(cached, out)
        return time.perf_counter() - t0, "hit"
    # MISS: full optimized pipeline, then store
    df = pd.read_csv(path, usecols=USECOLS, dtype=DTYPE_MAP, parse_dates=["timestamp"], engine="c")
    ProfileReport(df, explorative=True, progress_bar=False).to_file(cached)
    shutil.copy(cached, out)
    return time.perf_counter() - t0, "miss"

# clear cache so first call is a guaranteed miss
for f in os.listdir(CACHE): os.remove(os.path.join(CACHE, f))
t_miss, s1 = profile_cached(PATH, "/tmp/run1.html")
t_hit, s2 = profile_cached(PATH, "/tmp/run2.html")
t_hit2, s3 = profile_cached(PATH, "/tmp/run3.html")
print("CACHE " + json.dumps({
    "miss_s": round(t_miss, 3), "hit_s": round(t_hit, 4), "hit2_s": round(t_hit2, 4),
    "states": [s1, s2, s3],
    "hit_speedup_x": round(t_miss / t_hit, 1) if t_hit else None,
    "energy_avoided_pct_per_hit": round((1 - t_hit / t_miss) * 100, 2)}))
