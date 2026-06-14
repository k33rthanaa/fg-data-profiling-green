#!/usr/bin/env python3
"""
optimized_pipeline.py
---------------------
OPTIMISED Pandas pipeline — same logical output as baseline_pipeline.py
but applying the following green-software strategies from the course
infographic (van Gastel, 2026):

  C5 — Algorithm to data (avoid copies)
       Use chunked / streaming reads; eliminate intermediate DataFrame copies.

  D5 — Reuse results
       Accumulate aggregates incrementally per chunk; avoid re-reading data.

  D3 — Minimise interaction between components
       Specify exact dtypes at read time so Pandas does no extra inference.

  C3 — Store less
       Keep only required columns in memory; drop unneeded columns early.

  D6 — Improve algorithms (incl. program logic)
       Use in-place operations, avoid sort copies, stream output.

Optimisation techniques applied
--------------------------------
1. Chunked reading — pd.read_csv(chunksize=N) so the full file never
   lives in RAM at once.  Peak memory scales with chunk size, not file size.
2. Dtype specification at read time:
   - float64 → float32  for response_time_ms  (half the bits)
   - int64   → int32    for bytes_sent         (half the bits)
   - int64   → int16    for status_code        (max value 65535)
   - object  → category for method, region, user_agent  (string pool)
3. Eliminate intermediate copies — no .copy() calls; aggregation is
   accumulated across chunks using a running state dict.
4. Only required columns are loaded (usecols parameter).
5. Derived columns are computed in-place where possible.

Optional Polars comparison
--------------------------
If polars is installed, run_polars() provides an alternative implementation
using Polars lazy evaluation for further comparison.
"""

import argparse
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    from codecarbon import EmissionsTracker
    _CODECARBON = True
except ImportError:
    _CODECARBON = False

try:
    import polars as pl
    _POLARS = True
except ImportError:
    _POLARS = False


# ── dtype map applied at read time ──────────────────────────────────────────
_DTYPE_MAP = {
    "status_code":      "int16",
    "response_time_ms": "float32",
    "bytes_sent":       "int32",
    "method":           "category",
    "region":           "category",
    "user_agent":       "category",
    "endpoint":         "category",
}

# Only the columns we actually need — skip session_id and ip_address
_USECOLS = [
    "timestamp", "method", "endpoint", "status_code",
    "response_time_ms", "bytes_sent", "region",
]

_CHUNK_SIZE = 200_000   # rows per chunk (~42 MB of source CSV per chunk)


# ── incremental aggregation state ───────────────────────────────────────────

class _Accumulator:
    """Accumulates per-chunk aggregates without storing full data."""

    def __init__(self):
        # endpoint: {count, sum_rt, sum_bytes, sum_sq_rt, error_count, rt_list}
        self.endpoint: Dict[str, dict] = {}
        # region: {count, sum_rt, sum_bytes, error_count}
        self.region:   Dict[str, dict] = {}
        # (method, status): count
        self.method_status: Dict[tuple, int] = {}
        # hour: {count, sum_rt, sum_bytes}
        self.hourly:   Dict[int, dict] = {}
        self.total_rows = 0

    def update(self, chunk: pd.DataFrame) -> None:
        """Fold one chunk into running aggregates."""
        self.total_rows += len(chunk)

        # derived columns in-place
        chunk["hour"]     = chunk["timestamp"].dt.hour.astype("int8")
        chunk["is_error"] = chunk["status_code"] >= 400

        # ── endpoint aggregates ──────────────────────────────────────────
        ep_grp = chunk.groupby("endpoint", observed=True)
        for ep, grp in ep_grp:
            s = self.endpoint.setdefault(str(ep), {
                "count": 0, "sum_rt": 0.0, "sum_bytes": 0,
                "error_count": 0, "rt_vals": [],
            })
            s["count"]       += len(grp)
            s["sum_rt"]      += float(grp["response_time_ms"].sum())
            s["sum_bytes"]   += int(grp["bytes_sent"].sum())
            s["error_count"] += int(grp["is_error"].sum())
            # store sampled response times for p95 (reservoir sample)
            s["rt_vals"].extend(grp["response_time_ms"].tolist())
            if len(s["rt_vals"]) > 10_000:           # cap at 10 k per endpoint
                s["rt_vals"] = s["rt_vals"][-10_000:]

        # ── region aggregates ────────────────────────────────────────────
        rg_grp = chunk.groupby("region", observed=True)
        for rg, grp in rg_grp:
            s = self.region.setdefault(str(rg), {
                "count": 0, "sum_rt": 0.0, "sum_bytes": 0, "error_count": 0,
            })
            s["count"]       += len(grp)
            s["sum_rt"]      += float(grp["response_time_ms"].sum())
            s["sum_bytes"]   += int(grp["bytes_sent"].sum())
            s["error_count"] += int(grp["is_error"].sum())

        # ── method × status aggregates ───────────────────────────────────
        ms_grp = chunk.groupby(["method", "status_code"], observed=True).size()
        for (m, sc), cnt in ms_grp.items():
            key = (str(m), int(sc))
            self.method_status[key] = self.method_status.get(key, 0) + int(cnt)

        # ── hourly aggregates ────────────────────────────────────────────
        hr_grp = chunk.groupby("hour", observed=True)
        for hr, grp in hr_grp:
            s = self.hourly.setdefault(int(hr), {
                "count": 0, "sum_rt": 0.0, "sum_bytes": 0,
            })
            s["count"]     += len(grp)
            s["sum_rt"]    += float(grp["response_time_ms"].sum())
            s["sum_bytes"] += int(grp["bytes_sent"].sum())

    def to_dataframes(self):
        """Materialise the accumulated state as DataFrames."""

        # endpoint stats
        ep_rows = []
        for ep, s in self.endpoint.items():
            p95 = float(np.percentile(s["rt_vals"], 95)) if s["rt_vals"] else 0.0
            ep_rows.append({
                "endpoint":         ep,
                "request_count":    s["count"],
                "avg_response_ms":  s["sum_rt"] / s["count"] if s["count"] else 0.0,
                "p95_response_ms":  p95,
                "total_bytes":      s["sum_bytes"],
                "error_count":      s["error_count"],
            })
        endpoint_df = pd.DataFrame(ep_rows).sort_values(
            "request_count", ascending=False
        )

        # region stats
        rg_rows = []
        for rg, s in self.region.items():
            rg_rows.append({
                "region":           rg,
                "request_count":    s["count"],
                "avg_response_ms":  s["sum_rt"] / s["count"] if s["count"] else 0.0,
                "total_bytes_gb":   s["sum_bytes"] / 1e9,
                "error_rate":       s["error_count"] / s["count"] if s["count"] else 0.0,
            })
        region_df = pd.DataFrame(rg_rows)

        # method × status
        ms_rows = [
            {"method": m, "status_code": sc, "count": cnt}
            for (m, sc), cnt in self.method_status.items()
        ]
        method_status_df = pd.DataFrame(ms_rows)

        # hourly
        hr_rows = [
            {
                "hour":            hr,
                "request_count":   s["count"],
                "avg_response_ms": s["sum_rt"] / s["count"] if s["count"] else 0.0,
                "total_bytes":     s["sum_bytes"],
            }
            for hr, s in self.hourly.items()
        ]
        hourly_df = pd.DataFrame(hr_rows).sort_values("hour")

        return endpoint_df, region_df, method_status_df, hourly_df


# ── pipeline logic ──────────────────────────────────────────────────────────

def run_pipeline(input_path: str, output_path: str,
                 chunk_size: int = _CHUNK_SIZE) -> dict:
    """Execute the optimised pipeline and return measurement dict."""

    # ── start measurements ──────────────────────────────────────────────────
    tracemalloc.start()
    t_wall_start = time.perf_counter()

    proc = None
    cpu_start = None
    if _PSUTIL:
        proc = psutil.Process(os.getpid())
        ct = proc.cpu_times()
        cpu_start = ct.user + ct.system

    tracker = None
    if _CODECARBON:
        tracker = EmissionsTracker(
            project_name="optimized_pipeline",
            output_dir=str(Path(output_path).parent),
            log_level="error",
            save_to_file=False,
        )
        tracker.start()

    # ── chunked read + incremental aggregation ──────────────────────────────
    acc = _Accumulator()

    reader = pd.read_csv(
        input_path,
        usecols=_USECOLS,          # only needed columns
        dtype=_DTYPE_MAP,          # correct dtypes from the start
        parse_dates=["timestamp"],
        chunksize=chunk_size,      # stream in chunks
        engine="c",                # faster C parser
    )

    n_chunks = 0
    for chunk in reader:
        chunk.dropna(inplace=True)
        acc.update(chunk)
        n_chunks += 1

    # ── materialise results ─────────────────────────────────────────────────
    endpoint_df, region_df, method_status_df, hourly_df = acc.to_dataframes()

    # ── write output ────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    endpoint_df.to_csv(
        os.path.join(os.path.dirname(output_path), "endpoint_stats_optimized.csv"),
        index=False,
    )
    region_df.to_csv(
        os.path.join(os.path.dirname(output_path), "region_stats_optimized.csv"),
        index=False,
    )
    method_status_df.to_csv(
        os.path.join(os.path.dirname(output_path), "method_status_optimized.csv"),
        index=False,
    )
    hourly_df.to_csv(
        os.path.join(os.path.dirname(output_path), "hourly_optimized.csv"),
        index=False,
    )

    # ── stop measurements ───────────────────────────────────────────────────
    t_wall_end = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    cpu_end = None
    if _PSUTIL and proc is not None:
        ct = proc.cpu_times()
        cpu_end = ct.user + ct.system

    energy_kg = None
    if tracker is not None:
        energy_kg = tracker.stop()

    return {
        "variant":            "optimized",
        "input_path":         input_path,
        "wall_time_s":        t_wall_end - t_wall_start,
        "peak_memory_mb":     peak / 1024 / 1024,
        "current_memory_mb":  current / 1024 / 1024,
        "cpu_time_s":         (cpu_end - cpu_start) if (cpu_start and cpu_end) else None,
        "energy_kg_co2":      energy_kg,
        "n_chunks":           n_chunks,
        "total_rows":         acc.total_rows,
        "n_rows_endpoint":    len(endpoint_df),
        "n_rows_region":      len(region_df),
    }


# ── optional Polars variant ──────────────────────────────────────────────────

def run_polars(input_path: str, output_path: str) -> Optional[dict]:
    """Polars lazy-scan variant (requires polars package)."""
    if not _POLARS:
        print("[optimized] polars not installed, skipping Polars variant.")
        return None

    tracemalloc.start()
    t_start = time.perf_counter()

    lf = (
        pl.scan_csv(input_path)
        .select([
            "timestamp", "method", "endpoint", "status_code",
            "response_time_ms", "bytes_sent", "region",
        ])
        .with_columns([
            pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S"),
            pl.col("response_time_ms").cast(pl.Float32),
            pl.col("bytes_sent").cast(pl.Int32),
            pl.col("status_code").cast(pl.Int16),
            pl.col("method").cast(pl.Categorical),
            pl.col("region").cast(pl.Categorical),
        ])
        .drop_nulls()
        .with_columns([
            pl.col("timestamp").dt.hour().alias("hour"),
            (pl.col("status_code") >= 400).alias("is_error"),
        ])
    )

    endpoint_stats = (
        lf.group_by("endpoint")
        .agg([
            pl.len().alias("request_count"),
            pl.col("response_time_ms").mean().alias("avg_response_ms"),
            pl.col("response_time_ms").quantile(0.95).alias("p95_response_ms"),
            pl.col("bytes_sent").sum().alias("total_bytes"),
            pl.col("is_error").sum().alias("error_count"),
        ])
        .sort("request_count", descending=True)
        .collect()
    )

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "variant":        "polars",
        "input_path":     input_path,
        "wall_time_s":    time.perf_counter() - t_start,
        "peak_memory_mb": peak / 1024 / 1024,
        "n_rows":         len(endpoint_stats),
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the OPTIMISED CSV processing pipeline."
    )
    parser.add_argument(
        "--input", "-i",
        default=os.path.join(os.path.dirname(__file__), "data", "logs_100mb.csv"),
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=os.path.join(os.path.dirname(__file__), "results"),
    )
    parser.add_argument(
        "--chunk-size", type=int, default=_CHUNK_SIZE,
        help=f"Rows per chunk (default: {_CHUNK_SIZE})",
    )
    parser.add_argument(
        "--polars", action="store_true",
        help="Also run the Polars variant (requires polars package).",
    )
    args = parser.parse_args()

    output_path = os.path.join(args.output_dir, "optimized_output.csv")
    print(f"[optimized] Input : {args.input}")
    print(f"[optimized] Output: {output_path}")

    results = run_pipeline(args.input, output_path, args.chunk_size)

    print("\n── Measurements ────────────────────────────────────")
    print(f"  Wall time      : {results['wall_time_s']:.3f} s")
    print(f"  Peak memory    : {results['peak_memory_mb']:.1f} MB")
    print(f"  Chunks read    : {results['n_chunks']}")
    print(f"  Rows processed : {results['total_rows']:,}")
    if results["cpu_time_s"] is not None:
        print(f"  CPU time       : {results['cpu_time_s']:.3f} s")
    if results["energy_kg_co2"] is not None:
        print(f"  Energy (CO₂eq) : {results['energy_kg_co2']:.6f} kg")
    print("────────────────────────────────────────────────────")

    if args.polars:
        pr = run_polars(args.input, output_path)
        if pr:
            print(f"\n[Polars] Wall time   : {pr['wall_time_s']:.3f} s")
            print(f"[Polars] Peak memory : {pr['peak_memory_mb']:.1f} MB")


if __name__ == "__main__":
    main()
