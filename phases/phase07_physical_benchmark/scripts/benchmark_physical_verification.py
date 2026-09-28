#!/usr/bin/env python3
"""Benchmark the frozen SAM physical/cross-sensor verification workflow."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

C = 299_792_458.0
WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3
EXPECTED_SELECTED_SHA256 = "1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5"


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def finite_float(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def truthy(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def geodetic_to_ecef(lat_deg, lon_deg, height_m):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    return np.array([
        (n + height_m) * cos_lat * math.cos(lon),
        (n + height_m) * cos_lat * math.sin(lon),
        (n * (1.0 - WGS84_E2) + height_m) * sin_lat,
    ])


def load_good_sensors(path):
    sensors = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not truthy(row.get("good")):
                continue
            sid = str(row.get("serial", "")).strip()
            values = [finite_float(row.get(k)) for k in ("latitude", "longitude", "height")]
            if sid and all(v is not None for v in values):
                sensors[sid] = geodetic_to_ecef(*values)
    return sensors


def load_biases(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("selected_model") != "bias_only":
        raise SystemExit("Phase 7 requires the frozen Phase 5B bias_only model")
    biases = {}
    for item in data.get("receiver_parameters", []):
        if abs(float(item.get("drift_ns_per_hour", 0.0))) > 1e-12:
            raise SystemExit("Frozen bias_only calibration contains nonzero drift")
        biases[str(item["sensor"])] = float(item["bias_ns_at_time_center"])
    return biases


def parse_measurements(raw, modeled):
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            timestamp = finite_float(item[1])
            if sid in modeled and timestamp is not None:
                dedup.setdefault(sid, timestamp)
    return sorted(dedup.items())


def geometry_rank(points):
    x = np.vstack(points)
    singular = np.linalg.svd(x - x.mean(axis=0), compute_uv=False)
    tolerance = singular[0] * max(x.shape) * np.finfo(float).eps
    return int(np.sum(singular > tolerance))


def peak_rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def worker(args):
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    selected_hash = sha256_file(args.selected)
    if not args.skip_hash_check and selected_hash != args.expected_selected_sha256:
        raise SystemExit(f"Selected SHA-256 mismatch: expected {args.expected_selected_sha256}, got {selected_hash}")
    sensors = load_good_sensors(args.sensors)
    biases = load_biases(args.calibration)
    modeled = set(sensors) & set(biases)

    rows_read = test_rows = original_ge4 = usable_rows = pair_count = 0
    residuals = []
    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows_read += 1
            if row["split"].strip().lower() != "test":
                continue
            test_rows += 1
            if not truthy(row["eligible_ge4"]):
                continue
            original_ge4 += 1
            lat = finite_float(row["latitude"])
            lon = finite_float(row["longitude"])
            alt = finite_float(row["geoAltitude"])
            if alt is None:
                alt = finite_float(row["baroAltitude"])
            if None in (lat, lon, alt):
                continue
            try:
                measurements = parse_measurements(row["goodMeasurements"], modeled)
            except (json.JSONDecodeError, TypeError):
                continue
            if len(measurements) < 4:
                continue
            if geometry_rank([sensors[sid] for sid, _ in measurements]) != 3:
                continue
            aircraft_xyz = geodetic_to_ecef(lat, lon, alt)
            delay_ns = {
                sid: float(np.linalg.norm(aircraft_xyz - sensors[sid]) / C * 1e9)
                for sid, _ in measurements
            }
            corrected = {sid: timestamp - biases[sid] for sid, timestamp in measurements}
            ref = measurements[0][0]
            current = [
                (corrected[sid] - corrected[ref]) - (delay_ns[sid] - delay_ns[ref])
                for sid, _ in measurements[1:]
            ]
            residuals.extend(current)
            usable_rows += 1
            pair_count += len(current)

    absolute = np.abs(np.asarray(residuals, dtype=float))
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    result = {
        "counts": {
            "rows_read": rows_read,
            "test_rows": test_rows,
            "test_original_ge4_rows": original_ge4,
            "usable_test_rows": usable_rows,
            "pair_residuals": pair_count,
        },
        "validation": {
            "absolute_q50_ns": float(np.quantile(absolute, 0.50)),
            "absolute_q95_ns": float(np.quantile(absolute, 0.95)),
        },
        "timing": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "rows_read_per_second": rows_read / wall_seconds,
            "test_rows_per_second": test_rows / wall_seconds,
            "usable_rows_per_second": usable_rows / wall_seconds,
            "pair_residuals_per_second": pair_count / wall_seconds,
            "wall_microseconds_per_usable_row": wall_seconds * 1e6 / usable_rows,
        },
        "memory": {"peak_rss_mib": peak_rss_mib()},
    }
    print(json.dumps(result))


def numeric_summary(results, section, key):
    values = [float(item[section][key]) for item in results]
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "values": values,
    }


def run_child(args):
    command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--selected", str(args.selected), "--sensors", str(args.sensors),
        "--calibration", str(args.calibration),
        "--expected-selected-sha256", args.expected_selected_sha256,
    ]
    if args.skip_hash_check:
        command.append("--skip-hash-check")
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"})
    completed = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
    return json.loads(completed.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", required=True, type=Path)
    parser.add_argument("--sensors", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    parser.add_argument("--skip-hash-check", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if args.output is None:
        parser.error("--output is required")
    if args.repeats < 3:
        parser.error("--repeats must be at least 3")
    if args.warmups < 0:
        parser.error("--warmups cannot be negative")

    for _ in range(args.warmups):
        run_child(args)
    results = [run_child(args) for _ in range(args.repeats)]
    expected = results[0]["counts"]
    if any(item["counts"] != expected for item in results):
        raise SystemExit("Count mismatch between benchmark repetitions")
    if not args.skip_hash_check:
        for item in results:
            q50 = item["validation"]["absolute_q50_ns"]
            q95 = item["validation"]["absolute_q95_ns"]
            if abs(q50 - 64.98799972087727) > 1e-6 or abs(q95 - 227.07981870131601) > 1e-6:
                raise SystemExit("Frozen-result validation failed; benchmark output differs from Phase 5D")

    report = {
        "phase": "SAM Phase 7 frozen physical-verification benchmark",
        "scope": "End-to-end file hashing, input loading, test filtering, geometry checking, clock correction, and pair-residual computation; excludes bootstrap, attack detection, cryptography, ledger operations, and Phase 6 simulation.",
        "platform": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "processor": platform.processor(),
            "python": platform.python_version(), "numpy": np.__version__,
            "logical_cpu_count": os.cpu_count(),
        },
        "controls": {
            "warmups": args.warmups, "measured_repetitions": args.repeats,
            "fresh_subprocess_per_repetition": True,
            "blas_thread_environment": 1,
            "peak_memory_metric": "maximum resident set size of each fresh worker process",
        },
        "inputs": {
            "selected_sha256": sha256_file(args.selected),
            "sensors_sha256": sha256_file(args.sensors),
            "calibration_sha256": sha256_file(args.calibration),
        },
        "counts": expected,
        "validation": results[0]["validation"],
        "summaries": {
            "wall_seconds": numeric_summary(results, "timing", "wall_seconds"),
            "cpu_seconds": numeric_summary(results, "timing", "cpu_seconds"),
            "rows_read_per_second": numeric_summary(results, "timing", "rows_read_per_second"),
            "usable_rows_per_second": numeric_summary(results, "timing", "usable_rows_per_second"),
            "pair_residuals_per_second": numeric_summary(results, "timing", "pair_residuals_per_second"),
            "wall_microseconds_per_usable_row": numeric_summary(results, "timing", "wall_microseconds_per_usable_row"),
            "peak_rss_mib": numeric_summary(results, "memory", "peak_rss_mib"),
        },
        "repetitions": results,
        "interpretation_limits": [
            "Values characterize this Python implementation and machine, not certified avionics hardware.",
            "Peak RSS includes the Python interpreter, NumPy, input buffers, and retained residual array.",
            "Throughput is an offline end-to-end processing measurement and is not authentication delay.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "platform": report["platform"], "counts": expected, "summaries": report["summaries"]}, indent=2))


if __name__ == "__main__":
    main()
