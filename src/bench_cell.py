#!/usr/bin/env python3
"""Run K recorded reps of ONE (size, variant) cell as fresh subprocesses,
appending each result as a JSON line to results_full.jsonl. Keeps each
invocation short enough to fit the command time budget."""
import subprocess, json, sys, argparse, os

DATA = "../group14-project/data"
PATHS = {"20": f"{DATA}/logs_20mb.csv", "50": f"{DATA}/logs_50mb.csv"}

ap = argparse.ArgumentParser()
ap.add_argument("--size", required=True, choices=["20", "50"])
ap.add_argument("--variant", required=True, choices=["baseline", "optimized"])
ap.add_argument("--runs", type=int, default=3)
a = ap.parse_args()

for _ in range(a.runs):
    cmd = [sys.executable, "bench_runner.py", "--variant", a.variant,
           "--input", PATHS[a.size], "--out-html", f"/tmp/{a.variant}{a.size}.html",
           "--codecarbon"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    line = [l for l in out.stdout.splitlines() if l.startswith("RESULT_JSON")]
    if not line:
        print("FAIL:", out.stderr[-400:]); continue
    r = json.loads(line[0][len("RESULT_JSON "):])
    r["size_mb"] = int(a.size)
    with open("results_full.jsonl", "a") as f:
        f.write(json.dumps(r) + "\n")
    print(f"{a.variant:9s} {a.size}mb wall={r['wall_s']:6.2f}s cpu={r['cpu_s']:6.2f}s "
          f"rss={r['rss_peak_mb']:6.1f} tm_peak={r['tm_peak_mb']:6.1f} "
          f"load_tm={r['load_tm_mb']:5.2f} E={r['energy_kwh']}")
