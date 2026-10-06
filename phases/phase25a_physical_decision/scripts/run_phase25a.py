#!/usr/bin/env python3
"""Calibrate a leakage-controlled physical consistency decision and apply it to subset 1."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np

from physical_core import (
    EXPECTED_SELECTED_SHA256,
    aircraft_cluster_fraction_ci,
    aircraft_group,
    higher_quantile,
    load_biases,
    load_sensors,
    physical_inputs,
    residuals_for_claimed_position,
    row_score,
    sha256_file,
    truthy,
)


def summary(values):
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return {"n": 0}
    return {
        "n": int(x.size),
        "q50_ns": float(np.quantile(x, 0.50)),
        "q90_ns": float(np.quantile(x, 0.90)),
        "q95_ns": float(np.quantile(x, 0.95)),
        "q99_ns": float(np.quantile(x, 0.99)),
        "maximum_ns": float(np.max(x)),
    }


def classify(score, threshold):
    return "PHYSICALLY_CONSISTENT" if score <= threshold else "PHYSICALLY_CONFLICTING"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--sensors", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--model-output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--calibration-percent", type=int, default=70)
    p.add_argument("--target-benign-consistency", type=float, default=0.99)
    p.add_argument("--bootstrap-replicates", type=int, default=2000)
    p.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()
    if not 0.90 <= a.target_benign_consistency < 1.0:
        p.error("--target-benign-consistency must be in [0.90, 1.0)")
    if not 1 <= a.calibration_percent <= 99:
        p.error("--calibration-percent must be between 1 and 99")

    selected_hash = sha256_file(a.selected)
    if not a.skip_hash_check and selected_hash != a.expected_selected_sha256:
        raise SystemExit(f"Selected SHA-256 mismatch: {selected_hash}")
    sensors = load_sensors(a.sensors)
    biases = load_biases(a.calibration)
    input_hashes = {
        "selected": selected_hash,
        "sensors": sha256_file(a.sensors),
        "calibration": sha256_file(a.calibration),
    }

    start = time.perf_counter()
    validation_scores = []
    test_records = []
    counts = Counter()
    validation_aircraft, calibration_aircraft, test_aircraft = set(), set(), set()

    with gzip.open(a.selected, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts["rows_read"] += 1
            split = str(row.get("split", "")).strip().lower()
            aircraft = str(row.get("aircraft", "")).strip()
            if split == "development":
                group = aircraft_group(aircraft, a.seed, a.calibration_percent)
                (calibration_aircraft if group == "calibration" else validation_aircraft).add(aircraft)
                if group != "validation" or not truthy(row.get("eligible_ge4")):
                    continue
                counts["development_validation_original_ge4"] += 1
                inputs, reason = physical_inputs(row, sensors, biases, "goodMeasurements")
                if inputs is None:
                    counts[f"development_validation_unavailable_{reason}"] += 1
                    continue
                residuals = residuals_for_claimed_position(inputs, inputs["position"], sensors)
                validation_scores.append(row_score(residuals))
                counts["development_validation_physically_available"] += 1
            elif split == "test":
                test_aircraft.add(aircraft)
                if not truthy(row.get("eligible_ge4")):
                    continue
                counts["test_original_ge4"] += 1
                inputs, reason = physical_inputs(row, sensors, biases, "goodMeasurements")
                if inputs is None:
                    test_records.append((aircraft, None, reason))
                    continue
                residuals = residuals_for_claimed_position(inputs, inputs["position"], sensors)
                test_records.append((aircraft, row_score(residuals), None))

    if not validation_scores:
        raise SystemExit("No development-validation physical scores were produced")
    if not test_records:
        raise SystemExit("No subset-1 test records were found")
    if validation_aircraft & calibration_aircraft:
        raise SystemExit("Aircraft leakage between calibration and validation groups")
    if (validation_aircraft | calibration_aircraft) & test_aircraft:
        raise SystemExit("Aircraft leakage between development and test partitions")

    threshold = higher_quantile(validation_scores, a.target_benign_consistency)
    validation_states = Counter(classify(x, threshold) for x in validation_scores)
    test_states = Counter()
    test_scores = []
    unavailable_reasons = Counter()
    aircraft_conflicts = {}
    for aircraft, score, reason in test_records:
        if score is None:
            test_states["PHYSICAL_EVIDENCE_UNAVAILABLE"] += 1
            unavailable_reasons[reason] += 1
        else:
            state = classify(score, threshold)
            test_states[state] += 1
            test_scores.append(score)
            conflict, total = aircraft_conflicts.get(aircraft, (0, 0))
            aircraft_conflicts[aircraft] = (conflict + int(state == "PHYSICALLY_CONFLICTING"), total + 1)

    model = {
        "schema": "sam.phase25a.physical-decision-model.v1",
        "score": "median absolute calibrated direct-TDoA reference-pair residual per observation",
        "score_units": "nanoseconds",
        "decision_rule": "PHYSICALLY_CONSISTENT iff score <= threshold; otherwise PHYSICALLY_CONFLICTING",
        "threshold_ns": threshold,
        "threshold_quantile_method": "numpy higher empirical quantile",
        "target_benign_consistency": a.target_benign_consistency,
        "selection_partition": "Phase 3 development aircraft assigned to Phase 5B validation group only",
        "seed": a.seed,
        "calibration_percent": a.calibration_percent,
        "minimum_modeled_receivers": 4,
        "required_geometry_rank": 3,
        "input_sha256": input_hashes,
        "test_partition_used_for_threshold_selection": False,
        "subset2_used_for_threshold_selection": False,
    }

    available_test = len(test_scores)
    report = {
        "schema": "sam.phase25a.physical-decision-validation.v1",
        "scope": {
            "implemented": "leakage-controlled direct-TDoA physical decision calibration and subset-1 benign-reference evaluation",
            "not_implemented": ["operational or certification threshold", "real attack ground truth", "RF waveform experiment"],
        },
        "platform": {
            "system": platform.system(), "release": platform.release(), "machine": platform.machine(),
            "processor": platform.processor(), "python": platform.python_version(), "numpy": np.__version__,
            "logical_cpu_count": os.cpu_count(),
        },
        "inputs": {"paths": {"selected": str(a.selected), "sensors": str(a.sensors), "calibration": str(a.calibration)}, "sha256": input_hashes},
        "decision_model": model,
        "aircraft_partitions": {
            "development_calibration_aircraft": len(calibration_aircraft),
            "development_validation_aircraft": len(validation_aircraft),
            "test_aircraft": len(test_aircraft),
            "overlap": 0,
        },
        "development_validation": {
            "original_ge4_rows": counts["development_validation_original_ge4"],
            "physically_available_rows": len(validation_scores),
            "score_summary": summary(validation_scores),
            "states": dict(validation_states),
            "empirical_consistent_fraction_among_available": validation_states["PHYSICALLY_CONSISTENT"] / len(validation_scores),
        },
        "subset1_frozen_test": {
            "original_ge4_rows": counts["test_original_ge4"],
            "physically_available_rows": available_test,
            "physical_availability_fraction": available_test / counts["test_original_ge4"],
            "score_summary": summary(test_scores),
            "states": dict(test_states),
            "unavailable_reasons": dict(unavailable_reasons),
            "empirical_benign_reference_conflict_fraction_among_available": test_states["PHYSICALLY_CONFLICTING"] / available_test,
            "aircraft_cluster_conflict_fraction_ci95": aircraft_cluster_fraction_ci(aircraft_conflicts, a.bootstrap_replicates, a.seed),
            "full_policy_assurance_with_valid_crypto_and_trust": {
                "VERIFIED": test_states["PHYSICALLY_CONSISTENT"],
                "CONFLICTING": test_states["PHYSICALLY_CONFLICTING"],
                "INSUFFICIENT_EVIDENCE": test_states["PHYSICAL_EVIDENCE_UNAVAILABLE"],
            },
        },
        "runtime": {"wall_seconds": time.perf_counter() - start},
        "interpretation_limits": [
            "Trusted-aircraft metadata is used as a benign reference, not as attack-free ground truth.",
            "The empirical conflict fraction is not a certified operational false-alarm probability.",
            "The threshold is a reproducible prototype operating point selected without subset-1 test or subset-2 data.",
        ],
    }
    a.model_output.parent.mkdir(parents=True, exist_ok=True)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.model_output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"threshold_ns": threshold, "development_validation": report["development_validation"], "subset1_frozen_test": report["subset1_frozen_test"]}, indent=2))


if __name__ == "__main__":
    main()
