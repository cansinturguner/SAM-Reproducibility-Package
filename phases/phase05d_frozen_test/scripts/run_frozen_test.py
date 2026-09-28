#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
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


def load_frozen_calibration(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("selected_model") != "bias_only":
        raise SystemExit("Frozen Phase 5D requires the Phase 5B bias_only model")
    params = {}
    for item in data.get("receiver_parameters", []):
        drift = float(item.get("drift_ns_per_hour", 0.0))
        if abs(drift) > 1e-12:
            raise SystemExit("Frozen bias_only calibration unexpectedly contains nonzero drift")
        params[str(item["sensor"])] = float(item["bias_ns_at_time_center"])
    if len(params) < 4:
        raise SystemExit("Calibration contains fewer than four receiver biases")
    return data, params


def parse_measurements(raw, modeled):
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            ts = finite_float(item[1])
            if sid in modeled and ts is not None:
                dedup.setdefault(sid, ts)
    return sorted(dedup.items())


def geometry_rank(receiver_xyz):
    points = np.vstack(receiver_xyz)
    singular = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
    tol = singular[0] * max(points.shape) * np.finfo(float).eps
    return int(np.sum(singular > tol))


def residual_summary(values):
    x = np.asarray(values, dtype=float)
    if not x.size:
        return {"n": 0}
    ax = np.abs(x)
    cutoff = np.quantile(ax, 0.99)
    trimmed = x[ax <= cutoff]
    return {
        "n": int(x.size),
        "signed_median_ns": float(np.median(x)),
        "absolute_q50_ns": float(np.quantile(ax, 0.50)),
        "absolute_q90_ns": float(np.quantile(ax, 0.90)),
        "absolute_q95_ns": float(np.quantile(ax, 0.95)),
        "absolute_q99_ns": float(np.quantile(ax, 0.99)),
        "raw_rmse_ns": float(np.sqrt(np.mean(x * x))),
        "trimmed_99pct_rmse_ns": float(np.sqrt(np.mean(trimmed * trimmed))),
        "within_500ns_fraction": float(np.mean(ax <= 500.0)),
        "within_1000ns_fraction": float(np.mean(ax <= 1000.0)),
        "over_10us_fraction": float(np.mean(ax > 10_000.0)),
        "over_100us_fraction": float(np.mean(ax > 100_000.0)),
        "over_1ms_fraction": float(np.mean(ax > 1_000_000.0)),
    }


def scalar_summary(values):
    x = np.asarray(values, dtype=float)
    if not x.size:
        return {"n": 0}
    return {
        "n": int(x.size),
        "q05": float(np.quantile(x, 0.05)),
        "q50": float(np.quantile(x, 0.50)),
        "q95": float(np.quantile(x, 0.95)),
        "mean": float(np.mean(x)),
    }


def ci(values):
    x = np.asarray(values, dtype=float)
    return {
        "estimate": float(np.median(x)),
        "ci95_low": float(np.quantile(x, 0.025)),
        "ci95_high": float(np.quantile(x, 0.975)),
    }


def clustered_bootstrap(aircraft_stats, replicates, seed):
    ids = sorted(aircraft_stats)
    rng = np.random.default_rng(seed)
    availability, medians, q95s = [], [], []
    for _ in range(replicates):
        sampled = rng.choice(ids, size=len(ids), replace=True)
        orig = sum(aircraft_stats[a]["original_ge4"] for a in sampled)
        usable = sum(aircraft_stats[a]["usable"] for a in sampled)
        availability.append(usable / orig if orig else np.nan)
        aircraft_medians = [
            aircraft_stats[a]["median_abs_ns"] for a in sampled
            if aircraft_stats[a].get("median_abs_ns") is not None
        ]
        aircraft_q95 = [
            aircraft_stats[a]["q95_abs_ns"] for a in sampled
            if aircraft_stats[a].get("q95_abs_ns") is not None
        ]
        medians.append(float(np.median(aircraft_medians)))
        q95s.append(float(np.median(aircraft_q95)))
    return {
        "method": "aircraft-cluster bootstrap with replacement",
        "replicates": replicates,
        "seed": seed,
        "availability_weighted_by_rows": ci(availability),
        "median_of_aircraft_level_median_absolute_residual_ns": ci(medians),
        "median_of_aircraft_level_q95_absolute_residual_ns": ci(q95s),
    }


def receiver_band(n):
    return str(n) if n <= 7 else "8+"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True, type=Path)
    ap.add_argument("--sensors", required=True, type=Path)
    ap.add_argument("--calibration", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--bootstrap-replicates", type=int, default=2000)
    ap.add_argument("--bootstrap-seed", type=int, default=1103)
    ap.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    ap.add_argument("--skip-hash-check", action="store_true")
    args = ap.parse_args()
    if args.bootstrap_replicates < 100:
        raise SystemExit("--bootstrap-replicates must be at least 100")

    selected_hash = sha256_file(args.selected)
    if not args.skip_hash_check and selected_hash != args.expected_selected_sha256:
        raise SystemExit(
            f"Selected input SHA-256 mismatch: expected {args.expected_selected_sha256}, got {selected_hash}"
        )
    calibration_hash = sha256_file(args.calibration)
    sensors = load_good_sensors(args.sensors)
    calibration, biases = load_frozen_calibration(args.calibration)
    modeled = set(biases) & set(sensors)

    counts = Counter()
    pair_residuals = []
    row_median_abs = []
    aircraft_raw = defaultdict(lambda: {"original_ge4": 0, "usable": 0, "residuals": []})
    by_receiver = defaultdict(list)
    test_aircraft = set()

    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts["rows_read"] += 1
            if row["split"].strip().lower() != "test":
                continue
            counts["test_rows"] += 1
            aircraft = str(row["aircraft"]).strip()
            test_aircraft.add(aircraft)
            if not truthy(row["eligible_ge4"]):
                continue
            counts["test_original_ge4_rows"] += 1
            aircraft_raw[aircraft]["original_ge4"] += 1
            lat = finite_float(row["latitude"])
            lon = finite_float(row["longitude"])
            alt = finite_float(row["geoAltitude"])
            if alt is None:
                alt = finite_float(row["baroAltitude"])
            if None in (lat, lon, alt):
                counts["missing_required_position"] += 1
                continue
            try:
                measurements = parse_measurements(row["goodMeasurements"], modeled)
            except (json.JSONDecodeError, TypeError):
                counts["measurement_parse_errors"] += 1
                continue
            if len(measurements) < 4:
                counts["fewer_than_4_modeled_receivers"] += 1
                continue
            if geometry_rank([sensors[sid] for sid, _ in measurements]) != 3:
                counts["modeled_geometry_rank_not_3"] += 1
                continue
            aircraft_xyz = geodetic_to_ecef(lat, lon, alt)
            delay_ns = {
                sid: float(np.linalg.norm(aircraft_xyz - sensors[sid]) / C * 1e9)
                for sid, _ in measurements
            }
            corrected = {sid: ts - biases[sid] for sid, ts in measurements}
            ref = measurements[0][0]
            residuals = [
                (corrected[sid] - corrected[ref]) - (delay_ns[sid] - delay_ns[ref])
                for sid, _ in measurements[1:]
            ]
            counts["usable_test_rows"] += 1
            counts["usable_pair_residuals"] += len(residuals)
            aircraft_raw[aircraft]["usable"] += 1
            aircraft_raw[aircraft]["residuals"].extend(residuals)
            pair_residuals.extend(residuals)
            row_median_abs.append(float(np.median(np.abs(residuals))))
            by_receiver[receiver_band(len(measurements))].extend(residuals)

    if not pair_residuals:
        raise SystemExit("No usable frozen-test rows were found")

    aircraft_stats = {}
    for aircraft in sorted(test_aircraft):
        raw = aircraft_raw[aircraft]
        ax = np.abs(raw["residuals"])
        aircraft_stats[aircraft] = {
            "original_ge4": raw["original_ge4"],
            "usable": raw["usable"],
            "median_abs_ns": float(np.median(ax)) if len(ax) else None,
            "q95_abs_ns": float(np.quantile(ax, 0.95)) if len(ax) else None,
        }

    original = counts["test_original_ge4_rows"]
    usable = counts["usable_test_rows"]
    report = {
        "phase": "SAM Phase 5D frozen physical-corroboration test",
        "frozen_configuration": {
            "timestamp_unit": "nanosecond",
            "clock_model": "bias_only",
            "minimum_modeled_receivers": 4,
            "receiver_geometry_rank": 3,
            "geometry_ratio_minimum": None,
            "minimum_baseline_m": None,
            "configuration_source": "Phase 5B calibration and Phase 5C G0+B0 selection",
        },
        "inputs": {
            "selected_path": str(args.selected),
            "selected_sha256": selected_hash,
            "sensors_path": str(args.sensors),
            "calibration_path": str(args.calibration),
            "calibration_sha256": calibration_hash,
            "modeled_receivers_with_coordinates": len(modeled),
        },
        "counts": {
            **dict(counts),
            "unique_test_aircraft": len(test_aircraft),
        },
        "availability": {
            "denominator": "Phase 3 test rows originally eligible_ge4",
            "numerator": "rows satisfying the frozen modeled-receiver and rank rule",
            "fraction": usable / original if original else None,
        },
        "pair_residuals": residual_summary(pair_residuals),
        "row_residuals": {
            "metric": "within-row median absolute calibrated pair residual (ns)",
            **scalar_summary(row_median_abs),
        },
        "aircraft_clustered_confidence_intervals": clustered_bootstrap(
            aircraft_stats, args.bootstrap_replicates, args.bootstrap_seed
        ),
        "by_receiver_count": {
            band: residual_summary(vals)
            for band, vals in sorted(by_receiver.items(), key=lambda z: (z[0] == "8+", z[0]))
        },
        "interpretation_limits": [
            "This is a frozen one-time test evaluation; no threshold is tuned here.",
            "Large residuals are reported as measurement-quality outcomes, not attack labels.",
            "Raw RMSE is retained but is highly sensitive to rare extreme timestamps.",
            "The 99%-trimmed RMSE is explicitly labeled and does not replace the raw RMSE.",
        ],
        "security_label": "No attack or anomaly label is created.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
