#!/usr/bin/env python3
"""SAM Phase 6: controlled receiver-observation loss on the frozen test protocol.

This is an availability/robustness experiment, not an attack or anomaly detector.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
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
            vals = [finite_float(row.get(k)) for k in ("latitude", "longitude", "height")]
            if sid and all(v is not None for v in vals):
                sensors[sid] = geodetic_to_ecef(*vals)
    return sensors


def load_biases(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("selected_model") != "bias_only":
        raise SystemExit("Phase 6 requires the frozen Phase 5B bias_only calibration")
    biases = {}
    for item in data.get("receiver_parameters", []):
        if abs(float(item.get("drift_ns_per_hour", 0.0))) > 1e-12:
            raise SystemExit("Frozen bias-only calibration contains nonzero drift")
        biases[str(item["sensor"])] = float(item["bias_ns_at_time_center"])
    return data, biases


def parse_measurements(raw, modeled):
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            ts = finite_float(item[1])
            if sid in modeled and ts is not None:
                dedup.setdefault(sid, ts)
    return sorted(dedup.items())


def rank3(points):
    x = np.vstack(points)
    s = np.linalg.svd(x - x.mean(axis=0), compute_uv=False)
    tol = s[0] * max(x.shape) * np.finfo(float).eps
    return int(np.sum(s > tol)) == 3


def residual_summary(values):
    x = np.asarray(values, dtype=float)
    if not x.size:
        return {"n": 0}
    ax = np.abs(x)
    cutoff = np.quantile(ax, 0.99)
    trimmed = x[ax <= cutoff]
    return {
        "n": int(x.size),
        "absolute_q50_ns": float(np.quantile(ax, 0.50)),
        "absolute_q95_ns": float(np.quantile(ax, 0.95)),
        "absolute_q99_ns": float(np.quantile(ax, 0.99)),
        "trimmed_99pct_rmse_ns": float(np.sqrt(np.mean(trimmed * trimmed))),
        "within_500ns_fraction": float(np.mean(ax <= 500.0)),
        "within_1000ns_fraction": float(np.mean(ax <= 1000.0)),
    }


def summarize_replicates(items, key):
    values = [i.get(key) for i in items]
    values = [v for v in values if v is not None and math.isfinite(float(v))]
    if not values:
        return {
            "mean": None,
            "median": None,
            "simulation_interval_95_low": None,
            "simulation_interval_95_high": None,
        }
    x = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "simulation_interval_95_low": float(np.quantile(x, 0.025)),
        "simulation_interval_95_high": float(np.quantile(x, 0.975)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True, type=Path)
    ap.add_argument("--sensors", required=True, type=Path)
    ap.add_argument("--calibration", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--loss-probabilities", default="0,0.1,0.2,0.3,0.4,0.5")
    ap.add_argument("--replicates", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1103)
    ap.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    ap.add_argument("--skip-hash-check", action="store_true")
    args = ap.parse_args()
    probabilities = [float(x) for x in args.loss_probabilities.split(",")]
    if any(p < 0 or p >= 1 for p in probabilities):
        raise SystemExit("Loss probabilities must be in [0, 1)")
    if args.replicates < 2:
        raise SystemExit("--replicates must be at least 2")

    selected_hash = sha256_file(args.selected)
    if not args.skip_hash_check and selected_hash != args.expected_selected_sha256:
        raise SystemExit(f"Selected input SHA-256 mismatch: expected {args.expected_selected_sha256}, got {selected_hash}")
    sensors = load_good_sensors(args.sensors)
    calibration, biases = load_biases(args.calibration)
    modeled = set(sensors) & set(biases)

    rows = []
    original_ge4 = 0
    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["split"].strip().lower() != "test" or not truthy(row["eligible_ge4"]):
                continue
            original_ge4 += 1
            lat, lon = finite_float(row["latitude"]), finite_float(row["longitude"])
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
            aircraft_xyz = geodetic_to_ecef(lat, lon, alt)
            record = []
            for sid, ts in measurements:
                delay = float(np.linalg.norm(aircraft_xyz - sensors[sid]) / C * 1e9)
                record.append((sid, ts - biases[sid], delay))
            rows.append(record)

    scenarios = []
    for p_index, probability in enumerate(probabilities):
        rep_count = 1 if probability == 0 else args.replicates
        replicate_results = []
        for rep in range(rep_count):
            rng = np.random.default_rng(np.random.SeedSequence([args.seed, p_index, rep]))
            usable = 0
            residuals = []
            for record in rows:
                kept = record if probability == 0 else [x for x, keep in zip(record, rng.random(len(record)) >= probability) if keep]
                if len(kept) < 4 or not rank3([sensors[x[0]] for x in kept]):
                    continue
                usable += 1
                ref_sid, ref_corrected, ref_delay = kept[0]
                residuals.extend((corrected - ref_corrected) - (delay - ref_delay) for _, corrected, delay in kept[1:])
            metrics = residual_summary(residuals)
            replicate_results.append({
                "replicate": rep,
                "usable_rows": usable,
                "availability_vs_original_ge4": usable / original_ge4 if original_ge4 else None,
                "availability_vs_precandidate_rows": usable / len(rows) if rows else None,
                **metrics,
            })
        scenario = {
            "independent_receiver_loss_probability": probability,
            "replicates": rep_count,
            "replicate_results": replicate_results,
        }
        for key in ("usable_rows", "availability_vs_original_ge4", "availability_vs_precandidate_rows", "absolute_q50_ns", "absolute_q95_ns", "trimmed_99pct_rmse_ns"):
            scenario[key] = summarize_replicates(replicate_results, key)
        scenarios.append(scenario)

    report = {
        "phase": "SAM Phase 6 controlled receiver-observation loss",
        "scope": "Frozen physical/cross-sensor verification only; no attack or anomaly labels are created.",
        "loss_model": "Each modeled receiver observation is removed independently with the stated probability, conditional on an observed LocaRDS test row.",
        "limitations": [
            "This is a controlled missing-observation sensitivity analysis, not a replay of measured packet-loss processes.",
            "Loss independence is an experimental assumption and does not model correlated receiver or network outages.",
            "Simulation intervals summarize repeated loss realizations; they are not aircraft-cluster confidence intervals.",
        ],
        "frozen_configuration": {
            "timestamp_unit": "nanosecond",
            "clock_model": "bias_only",
            "minimum_modeled_receivers": 4,
            "receiver_geometry_rank": 3,
            "geometry_ratio_minimum": None,
            "minimum_baseline_m": None,
        },
        "inputs": {
            "selected_sha256": selected_hash,
            "sensors_sha256": sha256_file(args.sensors),
            "calibration_sha256": sha256_file(args.calibration),
            "calibration_selected_model": calibration.get("selected_model"),
        },
        "counts": {
            "test_original_ge4_rows": original_ge4,
            "rows_with_at_least_4_modeled_receivers_before_loss": len(rows),
        },
        "seed": args.seed,
        "scenarios": scenarios,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": report["counts"], "scenarios": [{"loss": s["independent_receiver_loss_probability"], "availability": s["availability_vs_original_ge4"]} for s in scenarios]}, indent=2))


if __name__ == "__main__":
    main()
