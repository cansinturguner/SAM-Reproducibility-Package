#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import hmac
import json
import math
import os
import platform
import resource
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from phase14_core import (
    C, EXPECTED_SELECTED_SHA256, canonical_message, ecef, finite, fuse,
    load_biases, load_sensors, measurements, rank3, sha256_file, trust_bootstrap,
    truthy,
)


def distribution(values):
    x = np.asarray(values, dtype=float)
    return {
        "n": int(x.size),
        "mean": float(np.mean(x)),
        "median": float(np.quantile(x, 0.50)),
        "q90": float(np.quantile(x, 0.90)),
        "q95": float(np.quantile(x, 0.95)),
        "q99": float(np.quantile(x, 0.99)),
        "minimum": float(np.min(x)),
        "maximum": float(np.max(x)),
    }


def peak_mib():
    x = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return x / (1024 * 1024) if sys.platform == "darwin" else x / 1024


def load_eligible(path):
    rows = []
    counts = {"rows_read": 0, "test_rows": 0, "test_original_ge4_rows": 0}
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            counts["rows_read"] += 1
            if row["split"].strip().lower() != "test":
                continue
            counts["test_rows"] += 1
            if not truthy(row["eligible_ge4"]):
                continue
            counts["test_original_ge4_rows"] += 1
            rows.append(row)
    return rows, counts


def process_row(row, sensors, biases, modeled, root_key, record_residuals=False):
    total_start = time.perf_counter_ns()

    crypto_start = time.perf_counter_ns()
    msg = canonical_message(row)
    interval = int(float(row.get("timeAtServer") or 0.0))
    key = hmac.new(root_key, b"interval:" + interval.to_bytes(8, "big", signed=False), hashlib.sha3_256).digest()[:16]
    tag = hmac.new(key, msg, hashlib.sha3_256).digest()[:16]
    crypto = "VERIFIED" if hmac.compare_digest(tag, hmac.new(key, msg, hashlib.sha3_256).digest()[:16]) else "CONFLICTING"
    crypto_ns = time.perf_counter_ns() - crypto_start

    physical_start = time.perf_counter_ns()
    physical = "INSUFFICIENT_EVIDENCE"
    residuals = []
    lat, lon = finite(row["latitude"]), finite(row["longitude"])
    alt = finite(row["geoAltitude"])
    if alt is None:
        alt = finite(row["baroAltitude"])
    if None not in (lat, lon, alt):
        try:
            ms = measurements(row["goodMeasurements"], modeled)
        except (json.JSONDecodeError, TypeError):
            ms = []
        if len(ms) >= 4 and rank3([sensors[sid] for sid, _ in ms]):
            xyz = ecef(lat, lon, alt)
            delays = {sid: float(np.linalg.norm(xyz - sensors[sid]) / C * 1e9) for sid, _ in ms}
            corrected = {sid: ts - biases[sid] for sid, ts in ms}
            ref = ms[0][0]
            if record_residuals:
                residuals = [(corrected[sid] - corrected[ref]) - (delays[sid] - delays[ref]) for sid, _ in ms[1:]]
            physical = "VERIFIED"
    physical_ns = time.perf_counter_ns() - physical_start

    fusion_start = time.perf_counter_ns()
    state = fuse(crypto, physical, "VERIFIED")
    fusion_ns = time.perf_counter_ns() - fusion_start
    total_ns = time.perf_counter_ns() - total_start
    return crypto, physical, state, residuals, crypto_ns, physical_ns, fusion_ns, total_ns


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--sensors", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--warmup-rows", type=int, default=1000)
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()
    if a.warmup_rows < 0 or a.repetitions < 5:
        p.error("use non-negative warmup rows and at least five repetitions")
    if not a.skip_hash_check:
        got = sha256_file(a.selected)
        if got != a.expected_selected_sha256:
            raise SystemExit(
                f"Selected SHA-256 mismatch: expected {a.expected_selected_sha256}, got {got}"
            )

    rows, input_counts = load_eligible(a.selected)
    if len(rows) != 82986:
        raise SystemExit(f"Frozen eligible count mismatch: {len(rows)}")
    sensors = load_sensors(a.sensors)
    biases = load_biases(a.calibration)
    modeled = set(sensors) & set(biases)
    root_key, trust_ok = trust_bootstrap(a.seed)
    if not trust_ok:
        raise SystemExit("Cached trust bootstrap failed")

    for row in rows[: min(a.warmup_rows, len(rows))]:
        process_row(row, sensors, biases, modeled, root_key)

    pooled = {k: [] for k in ("crypto", "physical", "fusion", "total", "supported_total", "unsupported_total")}
    per_rep = []
    frozen_counts = None
    frozen_residuals = None
    for repetition in range(1, a.repetitions + 1):
        values = {k: [] for k in pooled}
        counts = {"crypto_verified": 0, "physical_supported": 0, "VERIFIED": 0, "INSUFFICIENT_EVIDENCE": 0, "CONFLICTING": 0}
        residuals = []
        wall_start = time.perf_counter()
        for row in rows:
            crypto, physical, state, row_residuals, c_ns, p_ns, f_ns, t_ns = process_row(
                row, sensors, biases, modeled, root_key, record_residuals=(repetition == 1)
            )
            counts["crypto_verified"] += crypto == "VERIFIED"
            counts["physical_supported"] += physical == "VERIFIED"
            counts[state] += 1
            if repetition == 1:
                residuals.extend(row_residuals)
            c_us, p_us, f_us, t_us = c_ns / 1000, p_ns / 1000, f_ns / 1000, t_ns / 1000
            values["crypto"].append(c_us)
            values["physical"].append(p_us)
            values["fusion"].append(f_us)
            values["total"].append(t_us)
            values["supported_total" if physical == "VERIFIED" else "unsupported_total"].append(t_us)
        wall = time.perf_counter() - wall_start
        if frozen_counts is None:
            frozen_counts = counts
            frozen_residuals = residuals
        elif counts != frozen_counts:
            raise SystemExit("Non-deterministic assurance counts across repetitions")
        for key in pooled:
            pooled[key].extend(values[key])
        per_rep.append({
            "repetition": repetition,
            "wall_seconds": wall,
            "kernel_observations_per_second": len(rows) / wall,
            "total_latency_microseconds": distribution(values["total"]),
            "crypto_latency_microseconds": distribution(values["crypto"]),
            "physical_latency_microseconds": distribution(values["physical"]),
            "fusion_latency_microseconds": distribution(values["fusion"]),
        })

    if frozen_counts["physical_supported"] != 78358 or frozen_counts["VERIFIED"] != 78358:
        raise SystemExit("Frozen Phase 14 assurance count mismatch")
    abs_residuals = np.abs(np.asarray(frozen_residuals, dtype=float))
    residual_q50 = float(np.quantile(abs_residuals, .5))
    residual_q95 = float(np.quantile(abs_residuals, .95))
    if not a.skip_hash_check and abs(residual_q50 - 64.98799972087727) > 1e-6:
        raise SystemExit("Frozen residual q50 mismatch")

    component_means = {k: statistics.fmean(pooled[k]) for k in ("crypto", "physical", "fusion")}
    component_sum = sum(component_means.values())
    report = {
        "schema": "sam.phase21.component-latency.v1",
        "scope": {
            "implemented": "message-granularity component and total kernel latency on the frozen integrated SAM path",
            "not_implemented": [
                "input decompression or CSV loading inside the timed kernel",
                "TESLA disclosure wait",
                "online trust refresh or network transport",
                "RF processing or certified airborne hardware",
            ],
        },
        "platform": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "processor": platform.processor(),
            "python": platform.python_version(), "numpy": np.__version__,
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": a.seed, "warmup_rows": min(a.warmup_rows, len(rows)),
            "measured_repetitions": a.repetitions,
            "eligible_rows_per_repetition": len(rows),
            "timing_clock": "time.perf_counter_ns",
            "trust_mode": "valid cached trust",
        },
        "input_counts": input_counts,
        "frozen_validation": {
            "counts": frozen_counts,
            "pair_residual_absolute_q50_ns": residual_q50,
            "pair_residual_absolute_q95_ns": residual_q95,
        },
        "pooled_latency_microseconds": {
            "crypto": distribution(pooled["crypto"]),
            "physical_direct_tdoa": distribution(pooled["physical"]),
            "fusion": distribution(pooled["fusion"]),
            "total_kernel": distribution(pooled["total"]),
            "total_when_physical_supported": distribution(pooled["supported_total"]),
            "total_when_physical_insufficient": distribution(pooled["unsupported_total"]),
        },
        "mean_component_share_of_timed_component_sum": {
            "crypto_fraction": component_means["crypto"] / component_sum,
            "physical_direct_tdoa_fraction": component_means["physical"] / component_sum,
            "fusion_fraction": component_means["fusion"] / component_sum,
            "note": "Shares use component means; timer and surrounding-loop overhead remain in total_kernel only.",
        },
        "per_repetition": per_rep,
        "peak_rss_mib": peak_mib(),
        "interpretation_limits": [
            "Input loading is outside the timed kernel, so Phase 21 complements the Phase 14 end-to-end replay timing.",
            "Timer calls add instrumentation overhead; total_kernel is the authoritative instrumented message interval.",
            "Cached trust excludes CA/B2 verification and online refresh from the per-message path.",
            "Tail values can include operating-system scheduling and Python runtime variation.",
            "Results characterize this Python/Mac prototype and not certified avionics hardware.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
