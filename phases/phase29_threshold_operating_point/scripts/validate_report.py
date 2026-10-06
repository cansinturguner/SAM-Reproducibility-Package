#!/usr/bin/env python3
"""Validate the structural and frozen-point invariants of Phase 29."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))

    require(report.get("schema") == "sam.phase29.threshold-operating-point-sensitivity.v1", "schema mismatch")
    points = report.get("operating_points", [])
    require(len(points) >= 5, "too few operating points")
    thresholds = [float(point["threshold_ns"]) for point in points]
    require(thresholds == sorted(thresholds), "thresholds are not monotonic")
    frozen = [point for point in points if point.get("is_frozen_operating_point")]
    require(len(frozen) == 1, "expected exactly one frozen operating point")
    frozen = frozen[0]
    require(math.isclose(float(frozen["threshold_ns"]), 306.64062122826, rel_tol=0.0, abs_tol=1e-9), "frozen threshold mismatch")
    require(int(report["counts"]["development_validation_original_ge4"]) == 13430, "development-validation count mismatch")
    require(int(report["counts"]["development_validation_available"]) == 13240, "development-validation availability mismatch")
    require(int(report["counts"]["subset1_test_original_ge4"]) == 82986, "test count mismatch")
    require(int(report["counts"]["subset1_test_available"]) == 78358, "test availability mismatch")
    benign = frozen["subset1_benign_reference"]
    require(int(benign["conflicting_rows"]) == 1049, "frozen benign-conflict count mismatch")
    require(int(benign["consistent_rows"]) == 77309, "frozen benign-consistent count mismatch")

    crosscheck = report.get("phase25b_frozen_point_crosscheck")
    if crosscheck is not None:
        require(bool(crosscheck.get("all_match")), "Phase 25B frozen-point cross-check failed")

    for point in points:
        benign_fraction = float(point["subset1_benign_reference"]["conflict_fraction"])
        require(0.0 <= benign_fraction <= 1.0, "invalid benign conflict fraction")
        for result in point["position_bias"].values():
            for key in ("attacked_conflict_fraction_all_available", "consistent_to_conflicting_fraction"):
                value = result[key]
                require(value is None or 0.0 <= float(value) <= 1.0, f"invalid {key}")

    print("SAM Phase 29 threshold operating-point validation passed.")


if __name__ == "__main__":
    main()
