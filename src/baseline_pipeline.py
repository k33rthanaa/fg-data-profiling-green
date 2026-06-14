#!/usr/bin/env python3
"""
baseline_pipeline.py
--------------------
INTENTIONALLY INEFFICIENT Pandas pipeline.

This is the *before* implementation that demonstrates common anti-patterns
found in real-world data engineering code:

  1. Loads the entire CSV into memory at once with pd.read_csv()
     (no chunking, no streaming).
  2. Keeps all columns as the default dtypes chosen by Pandas
     (object for strings, int64 for integers, float64 for floats).
  3. Low-cardinality string columns (method, status_code, region,
     user_agent) are stored as Python object arrays instead of
     the memory-efficient category dtype.
  4. Every transformation creates a new intermediate DataFrame,
     causing multiple full copies of the data in RAM.
  5. Unnecessary copies are made explicitly (.copy()) to simulate
     defensive coding patterns common in production pipelines.

Measurements captured
---------------------
  - peak RSS memory (tracemalloc)
  - wall-clock time (perf_counter)
  - CPU user+sys time (psutil.Process)
  - energy estimate (codecarbon, if available)
"""

import argparse
import os
import sys
import time
import tracemalloc
from pathlib import Path

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


# ── pipeline logic ──────────────────────────────────────────────────────────

def run_pipeline(input_path: str, output_path: str) -> dict:
    """Execute the baseline pipeline and return measurement dict."""

    # ── start measurements ──────────────────────────────────────────────────
    tracemalloc.start()
    t_wall_start = time.perf_counter()

    proc = None
    cpu_start = None
    if _PSUTIL:
        proc = psutil.Process(os.getpid())
        cpu_times = proc.cpu_times()
        cpu_start = cpu_times.user + cpu_times.system

    tracker = None
    if _CODECARBON:
        tracker = EmissionsTracker(
            project_name="baseline_pipeline",
            output_dir=str(Path(output_path).parent),
            log_level="error",
            save_to_file=False,
        )
        tracker.start()

    # ── step 1: load entire CSV into memory ─────────────────────────────────
    # Anti-pattern: no dtype hints, no chunking — Pandas infers everything.
    df = pd.read_csv(input_path)                          # ← full load

    # ── step 2: unnecessary copy ────────────────────────────────────────────
    # Anti-pattern: defensive copy of a potentially-gigabyte DataFrame.
    working = df.copy()                                   # ← full copy #1
    del df                                                # df kept alive until here

    # ── step 3: parse timestamps ─────────────────────────────────────────────
    # Anti-pattern: creates a new Series; intermediate stored alongside original.
    working["timestamp"] = pd.to_datetime(working["timestamp"])

    # ── step 4: filter rows ──────────────────────────────────────────────────
    # Anti-pattern: boolean mask creates a copy of the filtered data.
    errors = working[working["status_code"] >= 400].copy()   # ← full copy #2
    non_200 = working[working["status_code"] != 200].copy()  # ← full copy #3

    # ── step 5: add derived columns ──────────────────────────────────────────
    # Anti-pattern: chained assignments that each produce temporary Series.
    working["hour"]         = working["timestamp"].dt.hour
    working["day_of_week"]  = working["timestamp"].dt.day_name()   # object strings
    working["is_error"]     = working["status_code"] >= 400
    working["is_slow"]      = working["response_time_ms"] > 1000.0
    working["kb_sent"]      = working["bytes_sent"] / 1024.0       # float64 ← float64

    # ── step 6: null handling ────────────────────────────────────────────────
    cleaned = working.dropna().copy()                              # ← full copy #4

    # ── step 7: aggregations ────────────────────────────────────────────────
    # Groupby on object-dtype columns is slower than on category dtype.
    endpoint_stats = (
        cleaned.groupby("endpoint", as_index=False)
        .agg(
            request_count=("endpoint", "count"),
            avg_response_ms=("response_time_ms", "mean"),
            p95_response_ms=("response_time_ms", lambda x: x.quantile(0.95)),
            total_bytes=("bytes_sent", "sum"),
            error_count=("is_error", "sum"),
        )
    )

    region_stats = (
        cleaned.groupby("region", as_index=False)
        .agg(
            request_count=("region", "count"),
            avg_response_ms=("response_time_ms", "mean"),
            total_bytes_gb=("bytes_sent", lambda x: x.sum() / 1e9),
            error_rate=("is_error", "mean"),
        )
    )

    method_status = (
        cleaned.groupby(["method", "status_code"], as_index=False)
        .agg(count=("method", "count"))
    )

    hourly = (
        cleaned.groupby("hour", as_index=False)
        .agg(
            request_count=("hour", "count"),
            avg_response_ms=("response_time_ms", "mean"),
            total_bytes=("bytes_sent", "sum"),
        )
    )

    slow_requests = cleaned[cleaned["is_slow"]].copy()            # ← full copy #5

    # ── step 8: sort ─────────────────────────────────────────────────────────
    endpoint_stats = endpoint_stats.sort_values(
        "request_count", ascending=False
    ).copy()                                                       # ← full copy #6

    # ── step 9: write output ─────────────────────────────────────────────────
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    endpoint_stats.to_csv(
        os.path.join(os.path.dirname(output_path), "endpoint_stats_baseline.csv"),
        index=False,
    )
    region_stats.to_csv(
        os.path.join(os.path.dirname(output_path), "region_stats_baseline.csv"),
        index=False,
    )
    method_status.to_csv(
        os.path.join(os.path.dirname(output_path), "method_status_baseline.csv"),
        index=False,
    )
    hourly.to_csv(
        os.path.join(os.path.dirname(output_path), "hourly_baseline.csv"),
        index=False,
    )

    # ── stop measurements ───────────────────────────────────────────────────
    t_wall_end = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    cpu_end = None
    if _PSUTIL and proc is not None:
        cpu_times = proc.cpu_times()
        cpu_end = cpu_times.user + cpu_times.system

    energy_kg = None
    if tracker is not None:
        energy_kg = tracker.stop()

    # ── summary ─────────────────────────────────────────────────────────────
    results = {
        "variant":            "baseline",
        "input_path":         input_path,
        "wall_time_s":        t_wall_end - t_wall_start,
        "peak_memory_mb":     peak / 1024 / 1024,
        "current_memory_mb":  current / 1024 / 1024,
        "cpu_time_s":         (cpu_end - cpu_start) if (cpu_start and cpu_end) else None,
        "energy_kg_co2":      energy_kg,
        "n_rows_endpoint":    len(endpoint_stats),
        "n_rows_region":      len(region_stats),
    }
    return results


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the BASELINE (inefficient) CSV processing pipeline."
    )
    parser.add_argument(
        "--input", "-i",
        default=os.path.join(os.path.dirname(__file__), "data", "logs_100mb.csv"),
        help="Path to the input CSV file.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=os.path.join(os.path.dirname(__file__), "results"),
        help="Directory to write output CSV files.",
    )
    args = parser.parse_args()

    output_path = os.path.join(args.output_dir, "baseline_output.csv")
    print(f"[baseline] Input : {args.input}")
    print(f"[baseline] Output: {output_path}")

    results = run_pipeline(args.input, output_path)

    print("\n── Measurements ────────────────────────────────────")
    print(f"  Wall time      : {results['wall_time_s']:.3f} s")
    print(f"  Peak memory    : {results['peak_memory_mb']:.1f} MB")
    if results["cpu_time_s"] is not None:
        print(f"  CPU time       : {results['cpu_time_s']:.3f} s")
    if results["energy_kg_co2"] is not None:
        print(f"  Energy (CO₂eq) : {results['energy_kg_co2']:.6f} kg")
    print("────────────────────────────────────────────────────")

    return results


if __name__ == "__main__":
    main()
