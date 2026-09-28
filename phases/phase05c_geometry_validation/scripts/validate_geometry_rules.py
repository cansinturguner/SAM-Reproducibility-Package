#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

C = 299_792_458.0
WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3
EXPECTED_SELECTED_SHA256 = "1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5"
RATIO_RULES = [("G0", 0.0), ("G1", 0.001), ("G2", 0.002), ("G3", 0.005)]
BASELINE_RULES = [("B0", 0.0), ("B1", 100.0), ("B2", 1000.0), ("B3", 5000.0)]


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


def load_calibration(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    params = {}
    for item in data.get("receiver_parameters", []):
        sid = str(item["sensor"])
        params[sid] = (
            float(item["bias_ns_at_time_center"]),
            float(item.get("drift_ns_per_hour", 0.0)),
        )
    if len(params) < 4:
        raise SystemExit("Calibration contains fewer than four receiver parameters")
    return data, params


def aircraft_is_validation(aircraft, seed, calibration_percent):
    token = f"{seed}|{aircraft}".encode()
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    return bucket >= calibration_percent


def parse_measurements(raw, modeled):
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            ts = finite_float(item[1])
            if sid in modeled and ts is not None:
                dedup.setdefault(sid, ts)
    return sorted(dedup.items())


def geometry(receiver_xyz):
    points = np.vstack(receiver_xyz)
    centered = points - points.mean(axis=0)
    singular = np.linalg.svd(centered, compute_uv=False)
    tol = singular[0] * max(centered.shape) * np.finfo(float).eps
    rank = int(np.sum(singular > tol))
    ratio = float(singular[-1] / singular[0]) if singular[0] > 0 else 0.0
    distances = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            distances.append(float(np.linalg.norm(points[i] - points[j])))
    return rank, ratio, min(distances), max(distances)


def summarize(values):
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
    }


def describe(values):
    x = np.asarray(values, dtype=float)
    if not x.size:
        return {"n": 0}
    return {
        "n": int(x.size),
        "q01": float(np.quantile(x, 0.01)),
        "q05": float(np.quantile(x, 0.05)),
        "q10": float(np.quantile(x, 0.10)),
        "q25": float(np.quantile(x, 0.25)),
        "q50": float(np.quantile(x, 0.50)),
        "q75": float(np.quantile(x, 0.75)),
        "q90": float(np.quantile(x, 0.90)),
        "q95": float(np.quantile(x, 0.95)),
        "q99": float(np.quantile(x, 0.99)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True, type=Path)
    ap.add_argument("--sensors", required=True, type=Path)
    ap.add_argument("--calibration", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=1103)
    ap.add_argument("--calibration-percent", type=int, default=70)
    ap.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    ap.add_argument("--skip-hash-check", action="store_true")
    args = ap.parse_args()

    selected_hash = sha256_file(args.selected)
    if not args.skip_hash_check and selected_hash != args.expected_selected_sha256:
        raise SystemExit(
            f"Selected input SHA-256 mismatch: expected {args.expected_selected_sha256}, got {selected_hash}"
        )
    sensors = load_good_sensors(args.sensors)
    calibration, parameters = load_calibration(args.calibration)
    if calibration.get("selected_model") != "bias_only":
        print("NOTE: applying the selected calibration model recorded in the file")
    time_center = float(calibration["time_center_seconds"])
    modeled = set(parameters) & set(sensors)
    counts = Counter()
    records = []
    validation_aircraft = set()

    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts["rows_read"] += 1
            if row["split"].strip().lower() != "development":
                continue
            counts["development_rows"] += 1
            aircraft = str(row["aircraft"]).strip()
            if not aircraft_is_validation(aircraft, args.seed, args.calibration_percent):
                continue
            counts["development_validation_rows"] += 1
            validation_aircraft.add(aircraft)
            if not truthy(row["eligible_ge4"]):
                continue
            counts["development_validation_original_ge4_rows"] += 1
            lat = finite_float(row["latitude"])
            lon = finite_float(row["longitude"])
            alt = finite_float(row["geoAltitude"])
            if alt is None:
                alt = finite_float(row["baroAltitude"])
            time_s = finite_float(row["timeAtServer"])
            if None in (lat, lon, alt, time_s):
                counts["missing_required_numeric"] += 1
                continue
            try:
                measurements = parse_measurements(row["goodMeasurements"], modeled)
            except (json.JSONDecodeError, TypeError):
                counts["measurement_parse_errors"] += 1
                continue
            if len(measurements) < 4:
                counts["fewer_than_4_modeled_receivers"] += 1
                continue
            xyz = [sensors[sid] for sid, _ in measurements]
            rank, ratio, min_baseline, max_baseline = geometry(xyz)
            if rank < 3:
                counts["modeled_geometry_rank_below_3"] += 1
                continue
            aircraft_xyz = geodetic_to_ecef(lat, lon, alt)
            delay_ns = {
                sid: float(np.linalg.norm(aircraft_xyz - sensors[sid]) / C * 1e9)
                for sid, _ in measurements
            }
            corrected = {}
            time_h = (time_s - time_center) / 3600.0
            for sid, timestamp in measurements:
                bias, drift = parameters[sid]
                corrected[sid] = timestamp - (bias + drift * time_h)
            ref = measurements[0][0]
            residuals = []
            for sid, _ in measurements[1:]:
                observed = corrected[sid] - corrected[ref]
                predicted = delay_ns[sid] - delay_ns[ref]
                residuals.append(observed - predicted)
            records.append({
                "ratio": ratio,
                "min_baseline_m": min_baseline,
                "max_baseline_m": max_baseline,
                "receiver_count": len(measurements),
                "residuals": residuals,
            })
            counts["usable_rank3_rows"] += 1
            counts["usable_pair_residuals"] += len(residuals)

    total_rows = len(records)
    rules = []
    for g_name, ratio_min in RATIO_RULES:
        for b_name, baseline_min in BASELINE_RULES:
            chosen = [
                r for r in records
                if r["ratio"] >= ratio_min and r["min_baseline_m"] >= baseline_min
            ]
            residuals = [e for r in chosen for e in r["residuals"]]
            rules.append({
                "rule": f"{g_name}+{b_name}",
                "geometry_ratio_min": ratio_min,
                "minimum_baseline_m": baseline_min,
                "rows_retained": len(chosen),
                "row_availability_vs_usable_rank3": len(chosen) / total_rows if total_rows else None,
                "pair_residuals": summarize(residuals),
            })

    report = {
        "phase": "SAM Phase 5C calibrated geometry validation",
        "scope": {
            "phase3_partition": "development only",
            "nested_partition": "Phase 5B validation aircraft only",
            "validation_aircraft": len(validation_aircraft),
            "test_partition_used": False,
            "clock_calibration_model": calibration.get("selected_model"),
        },
        "inputs": {
            "selected_path": str(args.selected),
            "selected_sha256": selected_hash,
            "sensors_path": str(args.sensors),
            "calibration_path": str(args.calibration),
            "modeled_receivers_with_coordinates": len(modeled),
        },
        "counts": dict(counts),
        "geometry_profile": {
            "ratio": describe([r["ratio"] for r in records]),
            "minimum_baseline_m": describe([r["min_baseline_m"] for r in records]),
            "maximum_baseline_m": describe([r["max_baseline_m"] for r in records]),
            "receiver_count": describe([r["receiver_count"] for r in records]),
        },
        "rules": rules,
        "decision_status": (
            "Candidate comparison only. The final geometry rule is not automatically selected."
        ),
        "security_label": "No attack or anomaly label is created.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
