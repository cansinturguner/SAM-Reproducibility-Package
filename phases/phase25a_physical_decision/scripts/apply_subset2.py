#!/usr/bin/env python3
"""Apply the frozen Phase 25A physical decision to LocaRDS subset 2."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np

from physical_core import aircraft_cluster_fraction_ci, load_biases, load_sensors, physical_inputs, residuals_for_claimed_position, row_score, sha256_file, truthy


EXPECTED = {
    "observations": "5ff68c7e402caa183678c03f4d23ba45b63bc96fa1177f8ce7e4fb530c45dd58",
    "sensors": "998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b",
    "aircraft": "70156a0865e655f4fb470e5814fd153708ac9f97ef193b70ebf3f4a5d84e1893",
}


def load_trusted(path):
    out = set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if truthy(row.get("trusted")):
                out.add(str(row.get("aircraft", "")).strip())
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", type=Path, required=True)
    p.add_argument("--sensors", type=Path, required=True)
    p.add_argument("--aircraft", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--decision-model", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--bootstrap-replicates", type=int, default=2000)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()

    hashes = {k: sha256_file(getattr(a, k)) for k in ("observations", "sensors", "aircraft", "calibration")}
    if not a.skip_hash_check:
        for key, expected in EXPECTED.items():
            if hashes[key] != expected:
                raise SystemExit(f"Unexpected subset-2 {key} SHA-256: {hashes[key]}")
    model = json.loads(a.decision_model.read_text(encoding="utf-8"))
    if model.get("schema") != "sam.phase25a.physical-decision-model.v1":
        raise SystemExit("Unexpected Phase 25A decision-model schema")
    if model.get("test_partition_used_for_threshold_selection") is not False or model.get("subset2_used_for_threshold_selection") is not False:
        raise SystemExit("Decision model does not preserve the required leakage boundary")
    threshold = float(model["threshold_ns"])
    hashes["decision_model"] = sha256_file(a.decision_model)

    trusted = load_trusted(a.aircraft)
    good_sensors = load_sensors(a.sensors)
    biases = load_biases(a.calibration)
    counts, scores = Counter(), []
    aircraft_conflicts = {}
    unavailable = Counter()
    start = time.perf_counter()
    with a.observations.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            counts["rows_read"] += 1
            if str(row.get("aircraft", "")).strip() not in trusted:
                continue
            counts["trusted_rows"] += 1
            try:
                good_measurements = json.loads(row.get("measurements", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            good_ids = {str(x[0]).strip() for x in good_measurements if isinstance(x, list) and len(x) >= 2 and str(x[0]).strip() in good_sensors}
            if len(good_ids) < 4:
                continue
            counts["trusted_good_ge4_rows"] += 1
            inputs, reason = physical_inputs(row, good_sensors, biases, "measurements")
            if inputs is None:
                counts["PHYSICAL_EVIDENCE_UNAVAILABLE"] += 1
                unavailable[reason] += 1
                continue
            score = row_score(residuals_for_claimed_position(inputs, inputs["position"], good_sensors))
            scores.append(score)
            if score <= threshold:
                counts["PHYSICALLY_CONSISTENT"] += 1
                is_conflict = 0
            else:
                counts["PHYSICALLY_CONFLICTING"] += 1
                is_conflict = 1
            aircraft = str(row.get("aircraft", "")).strip()
            conflict, total = aircraft_conflicts.get(aircraft, (0, 0))
            aircraft_conflicts[aircraft] = (conflict + is_conflict, total + 1)

    eligible = counts["trusted_good_ge4_rows"]
    available = len(scores)
    report = {
        "schema": "sam.phase25a.subset2-transfer.v1",
        "scope": "frozen Phase 25A physical decision applied to LocaRDS subset 2 without retuning",
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": platform.python_version(), "numpy": np.__version__},
        "inputs": {"sha256": hashes, "dataset_doi": "10.5281/zenodo.4739276"},
        "threshold_ns": threshold,
        "counts": dict(counts),
        "unavailable_reasons": dict(unavailable),
        "physical_availability_fraction": available / eligible if eligible else None,
        "empirical_benign_reference_conflict_fraction_among_available": counts["PHYSICALLY_CONFLICTING"] / available if available else None,
        "aircraft_cluster_conflict_fraction_ci95": aircraft_cluster_fraction_ci(aircraft_conflicts, a.bootstrap_replicates, a.seed),
        "full_policy_assurance_with_valid_crypto_and_trust": {
            "VERIFIED": counts["PHYSICALLY_CONSISTENT"],
            "CONFLICTING": counts["PHYSICALLY_CONFLICTING"],
            "INSUFFICIENT_EVIDENCE": counts["PHYSICAL_EVIDENCE_UNAVAILABLE"],
        },
        "runtime": {"wall_seconds": time.perf_counter() - start},
        "interpretation_limits": [
            "This is cross-partition transfer validation, not validation on an independent sensor network.",
            "Subset 2 did not update the threshold, receiver clock model, or geometry rule.",
            "Trusted-aircraft metadata is a benign reference filter and not attack-free ground truth.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
