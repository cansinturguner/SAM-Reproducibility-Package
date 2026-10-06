#!/usr/bin/env python3
"""Evaluate controlled position-bias and fixed-ground-spoofer sensitivity."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import platform
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

CORE = Path(__file__).resolve().parents[2] / "phase25a_physical_decision" / "scripts"
sys.path.insert(0, str(CORE))
from physical_core import (  # noqa: E402
    C,
    EXPECTED_SELECTED_SHA256,
    destination_point,
    deterministic_bearing,
    ecef,
    ecef_to_geodetic,
    load_biases,
    load_sensors,
    physical_inputs,
    residuals_for_claimed_position,
    row_score,
    sha256_file,
    truthy,
)


DEFAULT_BIASES_M = [0, 100, 250, 400, 500, 750, 1000, 2000, 5000, 10000]


def parse_distances(text):
    values = sorted({float(x.strip()) for x in text.split(",") if x.strip()})
    if not values or values[0] < 0:
        raise argparse.ArgumentTypeError("distances must be non-negative")
    if 0.0 not in values:
        values.insert(0, 0.0)
    return values


def fixed_spoofer_residuals(inputs, sensors, spoofer_xyz):
    """Preserve each row's nominal residual vector but move its emitter to one fixed ground point."""
    measurements = inputs["measurements"]
    claimed_xyz = ecef(*inputs["position"])
    corrected = inputs["corrected"]
    claimed_delay = {sid: float(np.linalg.norm(claimed_xyz - sensors[sid]) / C * 1e9) for sid, _ in measurements}
    spoofer_delay = {sid: float(np.linalg.norm(spoofer_xyz - sensors[sid]) / C * 1e9) for sid, _ in measurements}
    ref = measurements[0][0]
    preserved_noise = {
        sid: (corrected[sid] - corrected[ref]) - (claimed_delay[sid] - claimed_delay[ref])
        for sid, _ in measurements[1:]
    }
    return np.asarray([
        (spoofer_delay[sid] - spoofer_delay[ref]) + preserved_noise[sid]
        - (claimed_delay[sid] - claimed_delay[ref])
        for sid, _ in measurements[1:]
    ], dtype=float)


def summarize(counter, denominator):
    return {
        "available_rows": denominator,
        "PHYSICALLY_CONSISTENT": counter["PHYSICALLY_CONSISTENT"],
        "PHYSICALLY_CONFLICTING": counter["PHYSICALLY_CONFLICTING"],
        "conflict_sensitivity": counter["PHYSICALLY_CONFLICTING"] / denominator if denominator else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--sensors", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--decision-model", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--position-bias-m", type=parse_distances, default=DEFAULT_BIASES_M)
    p.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()

    selected_hash = sha256_file(a.selected)
    if not a.skip_hash_check and selected_hash != a.expected_selected_sha256:
        raise SystemExit(f"Selected SHA-256 mismatch: {selected_hash}")
    model = json.loads(a.decision_model.read_text(encoding="utf-8"))
    if model.get("schema") != "sam.phase25a.physical-decision-model.v1":
        raise SystemExit("Unexpected Phase 25A decision-model schema")
    threshold = float(model["threshold_ns"])
    sensors = load_sensors(a.sensors)
    biases = load_biases(a.calibration)
    modeled_xyz = np.vstack([sensors[sid] for sid in sorted(set(sensors) & set(biases))])
    centroid_lat, centroid_lon, _ = ecef_to_geodetic(modeled_xyz.mean(axis=0))
    spoofer_xyz = ecef(centroid_lat, centroid_lon, 0.0)

    bias_counts = {d: Counter() for d in a.position_bias_m}
    spoofer_counts = Counter()
    unavailable = Counter()
    available = 0
    start = time.perf_counter()

    with gzip.open(a.selected, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if str(row.get("split", "")).strip().lower() != "test" or not truthy(row.get("eligible_ge4")):
                continue
            inputs, reason = physical_inputs(row, sensors, biases, "goodMeasurements")
            if inputs is None:
                unavailable[reason] += 1
                continue
            available += 1
            lat, lon, alt = inputs["position"]
            row_id = str(row.get("id", f"row-{available}"))
            for distance in a.position_bias_m:
                bearing = deterministic_bearing(a.seed, row_id, distance)
                shifted_lat, shifted_lon = destination_point(lat, lon, distance, bearing)
                residuals = residuals_for_claimed_position(inputs, (shifted_lat, shifted_lon, alt), sensors)
                state = "PHYSICALLY_CONSISTENT" if row_score(residuals) <= threshold else "PHYSICALLY_CONFLICTING"
                bias_counts[distance][state] += 1
            spoofer_score = row_score(fixed_spoofer_residuals(inputs, sensors, spoofer_xyz))
            spoofer_state = "PHYSICALLY_CONSISTENT" if spoofer_score <= threshold else "PHYSICALLY_CONFLICTING"
            spoofer_counts[spoofer_state] += 1

    report = {
        "schema": "sam.phase25b.controlled-attack-sensitivity.v1",
        "scope": {
            "implemented": "independent SAM adaptation of published position-bias and fixed-ground-spoofer threat models",
            "not_implemented": ["Leonardi-Sirbu EKF or T1/T2 reproduction", "real attack capture", "RF transmission", "operational detection certification"],
        },
        "methodological_source": {
            "citation": "M. Leonardi and G. Sirbu, Sensors 21(15), 4992, 2021",
            "doi": "10.3390/s21154992",
            "relationship": "attack-scenario adaptation only; detector and results are not reproduced",
        },
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "processor": platform.processor(), "python": platform.python_version(), "numpy": np.__version__, "logical_cpu_count": os.cpu_count()},
        "inputs": {
            "sha256": {
                "selected": selected_hash,
                "sensors": sha256_file(a.sensors),
                "calibration": sha256_file(a.calibration),
                "decision_model": sha256_file(a.decision_model),
            }
        },
        "configuration": {
            "seed": a.seed,
            "threshold_ns": threshold,
            "score": model["score"],
            "position_bias_m": a.position_bias_m,
            "bias_direction": "deterministic SHA-256-derived bearing per row and distance",
            "fixed_ground_spoofer": {"latitude_deg": centroid_lat, "longitude_deg": centroid_lon, "height_m": 0.0, "definition": "geodetic projection of frozen modeled-receiver ECEF centroid"},
        },
        "counts": {"physically_available_subset1_test_rows": available, "unavailable_reasons": dict(unavailable)},
        "position_bias_sensitivity": {str(d): summarize(bias_counts[d], available) for d in a.position_bias_m},
        "fixed_ground_spoofer_fake_track": summarize(spoofer_counts, available),
        "runtime": {"wall_seconds": time.perf_counter() - start},
        "interpretation_limits": [
            "The zero-bias row is the empirical benign-reference conflict fraction under the frozen threshold.",
            "Nonzero position offsets are controlled synthetic perturbations and not captured attacks.",
            "Conflict sensitivity is not labeled real-world attack-detection accuracy.",
            "The fixed-ground-spoofer experiment synthesizes arrival-time differences while preserving each row's nominal residual vector; it is not an RF waveform simulation.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"threshold_ns": threshold, "position_bias_sensitivity": report["position_bias_sensitivity"], "fixed_ground_spoofer_fake_track": report["fixed_ground_spoofer_fake_track"]}, indent=2))


if __name__ == "__main__":
    main()

