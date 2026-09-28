#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
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


def parse_measurements(raw, sensors):
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            ts = finite_float(item[1])
            if sid in sensors and ts is not None:
                dedup.setdefault(sid, ts)
    return sorted(dedup.items())


def aircraft_group(aircraft, seed, calibration_percent):
    token = f"{seed}|{aircraft}".encode()
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    return "calibration" if bucket < calibration_percent else "validation"


def build_equations(path, sensors, seed, calibration_percent):
    eq = {"calibration": [], "validation": []}
    aircraft_sets = {"calibration": set(), "validation": set()}
    counts = Counter()
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "split", "eligible_ge4", "aircraft", "timeAtServer", "latitude",
            "longitude", "geoAltitude", "baroAltitude", "goodMeasurements"
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise SystemExit(f"Missing columns: {', '.join(missing)}")
        for row in reader:
            counts["rows_read"] += 1
            if row["split"].strip().lower() != "development":
                continue
            counts["development_rows"] += 1
            if not truthy(row["eligible_ge4"]):
                continue
            counts["development_ge4_rows"] += 1
            aircraft = str(row["aircraft"]).strip()
            group = aircraft_group(aircraft, seed, calibration_percent)
            aircraft_sets[group].add(aircraft)
            lat = finite_float(row["latitude"])
            lon = finite_float(row["longitude"])
            alt = finite_float(row["geoAltitude"])
            if alt is None:
                alt = finite_float(row["baroAltitude"])
            time_s = finite_float(row["timeAtServer"])
            if None in (lat, lon, alt, time_s):
                counts["rows_missing_required_numeric"] += 1
                continue
            try:
                measurements = parse_measurements(row["goodMeasurements"], sensors)
            except (json.JSONDecodeError, TypeError):
                counts["measurement_parse_errors"] += 1
                continue
            if len(measurements) < 4:
                counts["rows_fewer_than_4_loaded_good_sensors"] += 1
                continue
            aircraft_xyz = geodetic_to_ecef(lat, lon, alt)
            delays_ns = {
                sid: np.linalg.norm(aircraft_xyz - sensors[sid]) / C * 1e9
                for sid, _ in measurements
            }
            ref_sid, ref_ts = measurements[0]
            for sid, ts in measurements[1:]:
                residual_ns = (ts - ref_ts) - (delays_ns[sid] - delays_ns[ref_sid])
                eq[group].append((ref_sid, sid, time_s, residual_ns))
            counts[f"{group}_usable_rows"] += 1
    return eq, aircraft_sets, counts


def largest_connected_component(equations, minimum_sensor_observations):
    degree = Counter()
    adjacency = defaultdict(set)
    for a, b, _, _ in equations:
        degree[a] += 1
        degree[b] += 1
    allowed = {s for s, n in degree.items() if n >= minimum_sensor_observations}
    for a, b, _, _ in equations:
        if a in allowed and b in allowed:
            adjacency[a].add(b)
            adjacency[b].add(a)
    components, seen = [], set()
    for start in sorted(allowed):
        if start in seen:
            continue
        comp, queue = set(), deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            comp.add(node)
            for nxt in adjacency[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(comp)
    if not components:
        raise SystemExit("No connected receiver component satisfies the observation requirement")
    component = max(components, key=lambda c: (len(c), sum(degree[s] for s in c)))
    reference = max(component, key=lambda s: (degree[s], s))
    return component, reference, degree, components


def matrix_for(equations, component, reference, include_drift, time_center_s):
    sensors = sorted(component - {reference})
    index = {sid: i for i, sid in enumerate(sensors)}
    width = len(sensors) * (2 if include_drift else 1)
    kept = [e for e in equations if e[0] in component and e[1] in component]
    x = np.zeros((len(kept), width), dtype=np.float64)
    y = np.empty(len(kept), dtype=np.float64)
    for r, (a, b, time_s, residual_ns) in enumerate(kept):
        time_h = (time_s - time_center_s) / 3600.0
        for sid, sign in ((a, -1.0), (b, 1.0)):
            if sid == reference:
                continue
            col = index[sid]
            x[r, col] += sign
            if include_drift:
                x[r, len(sensors) + col] += sign * time_h
        y[r] = residual_ns
    return x, y, sensors


def robust_fit(x, y, iterations=6, huber_k=1.5):
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    trace = []
    for iteration in range(iterations):
        residual = y - x @ beta
        center = np.median(residual)
        mad = np.median(np.abs(residual - center))
        scale = max(1.4826 * mad, 1e-9)
        cutoff = huber_k * scale
        weights = np.ones_like(residual)
        mask = np.abs(residual - center) > cutoff
        weights[mask] = cutoff / np.abs(residual[mask] - center)
        root_w = np.sqrt(weights)
        beta, *_ = np.linalg.lstsq(x * root_w[:, None], y * root_w, rcond=None)
        trace.append({
            "iteration": iteration + 1,
            "robust_scale_ns": float(scale),
            "downweighted_fraction": float(mask.mean()),
        })
    return beta, trace


def summary(values):
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return {"n": 0}
    abs_x = np.abs(x)
    return {
        "n": int(x.size),
        "signed_median_ns": float(np.median(x)),
        "absolute_q50_ns": float(np.quantile(abs_x, 0.50)),
        "absolute_q90_ns": float(np.quantile(abs_x, 0.90)),
        "absolute_q95_ns": float(np.quantile(abs_x, 0.95)),
        "absolute_q99_ns": float(np.quantile(abs_x, 0.99)),
        "rmse_ns": float(np.sqrt(np.mean(x * x))),
        "within_500ns_fraction": float(np.mean(abs_x <= 500.0)),
        "within_1000ns_fraction": float(np.mean(abs_x <= 1000.0)),
    }


def evaluate_model(name, calibration_eq, validation_eq, component, reference, include_drift, time_center_s):
    x_cal, y_cal, sensors = matrix_for(
        calibration_eq, component, reference, include_drift, time_center_s
    )
    x_val, y_val, _ = matrix_for(
        validation_eq, component, reference, include_drift, time_center_s
    )
    beta, trace = robust_fit(x_cal, y_cal)
    cal_after = y_cal - x_cal @ beta
    val_after = y_val - x_val @ beta
    n = len(sensors)
    parameters = [{
        "sensor": reference,
        "bias_ns_at_time_center": 0.0,
        "drift_ns_per_hour": 0.0,
        "is_reference": True,
    }]
    for i, sid in enumerate(sensors):
        parameters.append({
            "sensor": sid,
            "bias_ns_at_time_center": float(beta[i]),
            "drift_ns_per_hour": float(beta[n + i]) if include_drift else 0.0,
            "is_reference": False,
        })
    parameters.sort(key=lambda z: z["sensor"])
    return {
        "model": name,
        "include_linear_drift": include_drift,
        "parameter_count": int(beta.size),
        "fit_trace": trace,
        "calibration_before": summary(y_cal),
        "calibration_after": summary(cal_after),
        "validation_before": summary(y_val),
        "validation_after": summary(val_after),
        "receiver_parameters": parameters,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True, type=Path)
    ap.add_argument("--sensors", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--calibration-output", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=1103)
    ap.add_argument("--calibration-percent", type=int, default=70)
    ap.add_argument("--minimum-sensor-observations", type=int, default=50)
    ap.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    ap.add_argument("--skip-hash-check", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.calibration_percent <= 99:
        raise SystemExit("--calibration-percent must be between 1 and 99")

    selected_hash = sha256_file(args.selected)
    if not args.skip_hash_check and selected_hash != args.expected_selected_sha256:
        raise SystemExit(
            f"Selected input SHA-256 mismatch: expected {args.expected_selected_sha256}, got {selected_hash}"
        )
    sensors = load_good_sensors(args.sensors)
    equations, aircraft_sets, counts = build_equations(
        args.selected, sensors, args.seed, args.calibration_percent
    )
    overlap = aircraft_sets["calibration"] & aircraft_sets["validation"]
    if overlap:
        raise SystemExit("Aircraft leakage detected between calibration and validation")
    component, reference, degree, components = largest_connected_component(
        equations["calibration"], args.minimum_sensor_observations
    )
    all_times = [e[2] for e in equations["calibration"] if e[0] in component and e[1] in component]
    time_center_s = float(np.median(all_times))

    bias_only = evaluate_model(
        "bias_only", equations["calibration"], equations["validation"],
        component, reference, False, time_center_s
    )
    bias_drift = evaluate_model(
        "bias_and_linear_drift", equations["calibration"], equations["validation"],
        component, reference, True, time_center_s
    )
    b = bias_only["validation_after"]["absolute_q50_ns"]
    d = bias_drift["validation_after"]["absolute_q50_ns"]
    b95 = bias_only["validation_after"]["absolute_q95_ns"]
    d95 = bias_drift["validation_after"]["absolute_q95_ns"]
    required_improvement_ns = max(5.0, 0.05 * b)
    drift_supported = (b - d >= required_improvement_ns) and (d95 <= b95)
    recommended = "bias_and_linear_drift" if drift_supported else "bias_only"
    chosen = bias_drift if recommended == "bias_and_linear_drift" else bias_only

    report = {
        "phase": "SAM Phase 5B receiver clock calibration",
        "inputs": {
            "selected_path": str(args.selected),
            "selected_sha256": selected_hash,
            "sensors_path": str(args.sensors),
            "good_sensors_loaded": len(sensors),
        },
        "split": {
            "unit": "aircraft identifier",
            "method": "deterministic SHA-256 bucket within Phase 3 development aircraft",
            "seed": args.seed,
            "calibration_percent_target": args.calibration_percent,
            "calibration_aircraft": len(aircraft_sets["calibration"]),
            "validation_aircraft": len(aircraft_sets["validation"]),
            "aircraft_overlap": len(overlap),
        },
        "counts": dict(counts),
        "network": {
            "minimum_sensor_observations": args.minimum_sensor_observations,
            "connected_components_after_filter": len(components),
            "modeled_component_sensors": len(component),
            "reference_sensor": reference,
            "time_center_seconds": time_center_s,
            "sensor_equation_counts": {s: degree[s] for s in sorted(component)},
        },
        "bias_only": bias_only,
        "bias_and_drift": bias_drift,
        "recommendation": {
            "selected_by": (
                "drift requires at least max(5 ns, 5%) validation-median improvement "
                "and must not worsen validation q95"
            ),
            "model": recommended,
            "bias_only_validation_median_absolute_ns": b,
            "bias_and_drift_validation_median_absolute_ns": d,
            "bias_only_validation_q95_absolute_ns": b95,
            "bias_and_drift_validation_q95_absolute_ns": d95,
            "required_median_improvement_ns": required_improvement_ns,
            "drift_supported": drift_supported,
            "test_partition_used": False,
        },
        "security_label": "No attack or anomaly label is created.",
    }
    calibration = {
        "source_phase": "SAM Phase 5B",
        "selected_model": recommended,
        "reference_sensor": reference,
        "time_center_seconds": time_center_s,
        "timestamp_unit": "nanosecond (empirically supported in Phase 5A)",
        "receiver_parameters": chosen["receiver_parameters"],
        "scope": "fitted on Phase 3 development aircraft only",
        "selected_input_sha256": selected_hash,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.calibration_output.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.calibration_output.write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
