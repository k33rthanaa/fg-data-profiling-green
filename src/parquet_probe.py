#!/usr/bin/env python3
"""CSV vs Parquet: load time, load memory, and on-disk size for the columns
ProfileReport actually uses. Parquet is columnar + typed + compressed."""
import time, os, tracemalloc, warnings, json, statistics
warnings.filterwarnings("ignore")
import pandas as pd

DTYPE_MAP = {"status_code": "int16", "response_time_ms": "float32", "bytes_sent": "int32",
             "method": "category", "region": "category", "user_agent": "category", "endpoint": "category"}
USECOLS = ["timestamp", "method", "endpoint", "status_code", "response_time_ms", "bytes_sent", "region"]

for SIZE, CSV in [("20", "../group14-project/data/logs_20mb.csv"),
                  ("50", "../group14-project/data/logs_50mb.csv")]:
    PARQUET = f"/tmp/logs_{SIZE}mb.parquet"
    # build optimized-typed df and write parquet once
    df = pd.read_csv(CSV, usecols=USECOLS, dtype=DTYPE_MAP, parse_dates=["timestamp"], engine="c")
    df.to_parquet(PARQUET, engine="pyarrow", compression="snappy", index=False)

    def load_csv():
        t0 = time.perf_counter(); tracemalloc.start()
        d = pd.read_csv(CSV, usecols=USECOLS, dtype=DTYPE_MAP, parse_dates=["timestamp"], engine="c")
        m = tracemalloc.get_traced_memory()[0]; tracemalloc.stop()
        return time.perf_counter() - t0, m / 1e6, len(d)

    def load_parquet():
        t0 = time.perf_counter(); tracemalloc.start()
        d = pd.read_parquet(PARQUET, engine="pyarrow")
        m = tracemalloc.get_traced_memory()[0]; tracemalloc.stop()
        return time.perf_counter() - t0, m / 1e6, len(d)

    cw = [load_csv() for _ in range(3)]; pw = [load_parquet() for _ in range(3)]
    csv_t = statistics.mean(x[0] for x in cw); par_t = statistics.mean(x[0] for x in pw)
    csv_m = statistics.mean(x[1] for x in cw); par_m = statistics.mean(x[1] for x in pw)
    csv_disk = os.path.getsize(CSV) / 1e6; par_disk = os.path.getsize(PARQUET) / 1e6
    print("PARQ " + json.dumps({
        "size_mb": SIZE,
        "csv_load_s": round(csv_t, 3), "parquet_load_s": round(par_t, 3),
        "load_time_reduction_pct": round((csv_t - par_t)/csv_t*100, 1),
        "csv_load_mem_mb": round(csv_m, 2), "parquet_load_mem_mb": round(par_m, 2),
        "csv_disk_mb": round(csv_disk, 2), "parquet_disk_mb": round(par_disk, 2),
        "disk_reduction_pct": round((csv_disk - par_disk)/csv_disk*100, 1),
        "rows": cw[0][2]}))
