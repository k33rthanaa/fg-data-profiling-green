# Green Optimisation of fg-data-profiling

**49–64% faster. 88% less load memory. Zero changes to the library.**

This project applies green-software strategies to [fg-data-profiling](https://github.com/Data-Centric-AI-Community/fg-data-profiling)  a widely used automated EDA library with ~13,600 GitHub stars and achieves substantial energy and runtime savings purely from the *caller side*, without modifying any library internals.

Conducted as part of NWI-IMC019 Green Software at Radboud University (Group 14).

---

## Key Results

| Metric | 20 MB input | 50 MB input |
|---|---|---|
| Wall-clock time | **-49.2%** (9.07 → 4.61 s) | **-64.1%** (16.67 → 5.98 s) |
| Measured energy (CodeCarbon) | **-48.7%** | **-63.9%** |
| DataFrame load memory | **-88.3%** (20.7 → 2.4 MB) | **-88.7%** (50.4 → 5.7 MB) |
| Output correctness | ✓ identical | ✓ identical |

The optimised variant's advantage *increases* with input size — at 50 MB it is 2.8× faster than baseline, with gains compounding further at larger scales.

> Full methodology, energy/carbon calculations, and discussion in the [report](../overleaf_report/report.tex).

---

## What Was Done

The default `pd.read_csv()` call inflates a 20 MB CSV to ~20 MB of Python `object`-dtype RAM before any profiling computation begins. The fix is two changes at the call site:

**1. Declare exact dtypes (strategies C5, D6)**
```python
DTYPE_MAP = {
    "status_code":      "int16",
    "response_time_ms": "float32",
    "bytes_sent":       "int32",
    "method":           "category",   # 4 unique values  -> 1-byte index
    "region":           "category",   # 15 unique values -> 1-byte index
    "endpoint":         "category",   # 200 unique values -> 1-byte index
}
```

**2. Drop columns the profiler marks Unsupported anyway (strategies C3, D3)**
```python
USECOLS = ["timestamp", "method", "endpoint", "status_code",
           "response_time_ms", "bytes_sent", "region"]
# drops: ip_address, session_id, user_agent
```

This cuts correlation pairs from 45 to 21 and lets every groupby/correlation operation run on integer indices instead of string comparisons.

---

## Additional Experiments

Beyond the main optimisation, four further levers were measured:

| Lever | Result |
|---|---|
| `minimal=True` config stacked on dtype fix | **-72%** wall time (trade-off: removes correlations) |
| 25% row sampling | **-67%** peak memory, stats within 0.5% of full-data |
| CSV → Parquet (snappy) | **-95%** load time, **-85%** on-disk size |
| Result caching (hash-based) | **99.98%** energy avoided per cache hit |
| JSON output instead of HTML | **+23% slower** (negative result — reported) |

---

## Repository Structure

```
src/
├── generate_dataset.py       # Synthetic server-log dataset generator
├── baseline_pipeline.py      # Unmodified pd.read_csv + ProfileReport
├── baseline_profiling.py     # Baseline profiling subprocess entry point
├── optimized_pipeline.py     # dtype + usecols optimised loader
├── optimized_profiling.py    # Optimised profiling subprocess entry point
├── benchmark.py              # Main benchmark runner (n runs, both variants)
├── bench_runner.py           # Subprocess orchestration
├── bench_cell.py             # Single benchmark cell (memory + time + energy)
├── analyze_results.py        # Generates all plots from results CSVs
├── aggregate_and_plot.py     # Aggregation and grouped plots
├── extended_plot.py          # Plots for additional levers
├── probe_runner.py           # Runner for individual probes
├── caching_probe.py          # Hash-based result caching experiment
├── parquet_probe.py          # CSV vs Parquet comparison
├── sampling_probe.py         # Row-sampling accuracy/memory trade-off
├── verify_correctness.py     # Confirms optimised output is statistically identical
└── data/                     # Generated datasets (git-ignored — see below)
```

---

## Reproducing the Results

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `codecarbon` is optional. If unavailable, the benchmark falls back to CPU-time × TDP for energy estimation.

### 2. Generate datasets

```bash
# Creates data/logs_20mb.csv and data/logs_50mb.csv
python generate_dataset.py --size 20 --out data/logs_20mb.csv
python generate_dataset.py --size 50 --out data/logs_50mb.csv
```

The datasets use a fixed random seed and a synthetic server-access-log schema (timestamp, method, endpoint, status_code, response_time_ms, bytes_sent, region, ip_address, session_id, user_agent).

### 3. Run the main benchmark

```bash
# Full end-to-end ProfileReport, n=3 runs per variant, both input sizes
python benchmark.py --size 20 --runs 3
python benchmark.py --size 50 --runs 3
# Results written to ../results/
```

### 4. Run additional probes

```bash
python probe_runner.py          # Configuration tuning experiments
python sampling_probe.py        # Row-sampling memory/accuracy trade-off
python parquet_probe.py         # CSV vs Parquet load/storage comparison
python caching_probe.py         # Hash-based caching experiment
```

### 5. Generate plots

```bash
python analyze_results.py       # Main benchmark plots -> ../plots/
python extended_plot.py         # Additional lever plots -> ../plots/
```

### 6. Verify correctness

```bash
python verify_correctness.py    # Confirms per-column stats are identical between variants
```

---

## Measurement Setup

| Tool | Purpose |
|---|---|
| `tracemalloc` | Python-level peak memory allocation |
| `psutil` (10 ms sampler) | Process peak RSS |
| `time.perf_counter` | Wall-clock time |
| `psutil.Process.cpu_times` | CPU time |
| `codecarbon` | Energy measurement (falls back to CPU-time × TDP) |

Each (variant, size) cell runs as an isolated subprocess to prevent cross-contamination of memory state between runs.

---

## Strategies Applied

From van Gastel's *Strategies for Green Software* infographic:

| Code | Strategy | Applied as |
|---|---|---|
| C5 | Algorithm to data (avoid copies) | dtype-aware read; no intermediate object buffers |
| D6 | Improve algorithms | `category` dtype: integer-index groupby/correlation |
| C3 | Store less | `usecols` — never decode unused columns |
| D3 | Minimise component interaction | fewer columns → fewer correlation pairs (45 → 21) |

---

## Authors

Keerthana Yelchuru Venkata & Sriyan Ravuri — Group 14, NWI-IMC019 Green Software, Radboud University, 2025–2026.
