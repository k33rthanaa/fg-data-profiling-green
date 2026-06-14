#!/usr/bin/env python3
"""
generate_dataset.py
-------------------
Generates synthetic but realistic tabular CSV datasets to use as input for
ydata-profiling benchmarks.

The schema mimics a server-access log, a domain where ydata-profiling is
widely applied for data-quality validation and exploratory analysis.

Usage
-----
    python generate_dataset.py --size 20    # ~20 MB CSV
    python generate_dataset.py --size 100   # ~100 MB CSV
    python generate_dataset.py --size 500   # ~500 MB CSV

Schema
------
timestamp         str   ISO-8601, 1-year window
ip_address        str   ~5 000 unique values
method            str   GET/POST/PUT/DELETE  (low cardinality → category)
endpoint          str   ~200 unique paths    (low cardinality → category)
status_code       int   200/301/400/404/500  (fits int16)
response_time_ms  float log-normal, ms       (fits float32)
bytes_sent        int   200 B – 5 MB         (fits int32)
user_agent        str   ~30 unique strings   (low cardinality → category)
region            str   ~15 unique strings   (low cardinality → category)
session_id        str   UUID-like, ~50 000 unique values
"""

import argparse
import csv
import os
import random
import time
from datetime import datetime, timedelta

SEED = 42
random.seed(SEED)

METHODS   = ["GET"] * 6 + ["POST", "PUT", "DELETE"]
ENDPOINTS = [
    f"/api/v{v}/{res}/{act}"
    for v   in (1, 2)
    for res in ("users","orders","products","sessions","reports",
                "inventory","billing","analytics","notifications","search")
    for act in ("","create","update","delete","list","detail",
                "export","import","bulk","stats")
][:200]

STATUS_CODES  = [200, 200, 200, 200, 200, 301, 400, 404, 404, 500]
USER_AGENTS   = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148",
    "Mozilla/5.0 (Android 14; Mobile; rv:121.0) Gecko/121.0",
    "curl/8.4.0","python-requests/2.31.0","Go-http-client/2.0",
    "Googlebot/2.1","Bingbot/2.0","DuckDuckBot/1.1","Twitterbot/1.0",
    "facebookexternalhit/1.1","LinkedInBot/1.0","Slackbot-LinkExpanding 1.0",
    "PostmanRuntime/7.36.0","insomnia/2023.5.8","HTTPie/3.2.2",
    "Wget/1.21.4","axios/1.6.2","node-fetch/3.3.2","okhttp/4.12.0",
    "Apache-HttpClient/5.3","Dalvik/2.1.0","CFNetwork/1410.0.3",
    "Jakarta Commons-HttpClient/3.1","libwww-perl/6.77",
    "Ruby/3.3.0","PHP/8.3.0","Java/21.0.1",
]
REGIONS = [
    "us-east-1","us-west-2","eu-west-1","eu-central-1","ap-southeast-1",
    "ap-northeast-1","sa-east-1","ca-central-1","af-south-1","me-south-1",
    "ap-south-1","ap-southeast-2","eu-north-1","us-east-2","eu-west-2",
]
IP_POOL = [
    f"{random.randint(1,254)}.{random.randint(0,255)}"
    f".{random.randint(0,255)}.{random.randint(1,254)}"
    for _ in range(5_000)
]
SESSION_POOL = [
    f"{random.randint(0,0xFFFFFFFF):08x}-{random.randint(0,0xFFFF):04x}-"
    f"{random.randint(0,0xFFFF):04x}-{random.randint(0,0xFFFF):04x}-"
    f"{random.randint(0,0xFFFFFFFFFFFF):012x}"
    for _ in range(50_000)
]
START = datetime(2024, 1, 1)
RANGE_S = int((datetime(2025, 1, 1) - START).total_seconds())
HEADER  = ["timestamp","ip_address","method","endpoint","status_code",
           "response_time_ms","bytes_sent","user_agent","region","session_id"]
_APPROX_BYTES_PER_ROW = 210


def _row():
    ts = (START + timedelta(seconds=random.randint(0, RANGE_S))).strftime(
        "%Y-%m-%d %H:%M:%S")
    return [ts, random.choice(IP_POOL), random.choice(METHODS),
            random.choice(ENDPOINTS), random.choice(STATUS_CODES),
            round(random.lognormvariate(3.5, 1.2), 3),
            random.randint(200, 5_242_880),
            random.choice(USER_AGENTS), random.choice(REGIONS),
            random.choice(SESSION_POOL)]


def generate(target_mb: int, out: str) -> None:
    n = target_mb * 1024 * 1024 // _APPROX_BYTES_PER_ROW
    print(f"[dataset] target={target_mb} MB  rows≈{n:,}  → {out}")
    t0 = time.perf_counter()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        buf = []
        for i in range(n):
            buf.append(_row())
            if len(buf) == 50_000:
                w.writerows(buf); buf = []
                print(f"  {100*i/n:.0f}%", end="\r")
        if buf:
            w.writerows(buf)
    mb = os.path.getsize(out) / 1024 / 1024
    print(f"[dataset] done  {mb:.1f} MB  {time.perf_counter()-t0:.1f}s")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=20)
    p.add_argument("--out",  type=str, default=None)
    a = p.parse_args()
    if a.out is None:
        a.out = os.path.join(os.path.dirname(__file__), "data",
                             f"logs_{a.size}mb.csv")
    generate(a.size, a.out)


if __name__ == "__main__":
    main()
