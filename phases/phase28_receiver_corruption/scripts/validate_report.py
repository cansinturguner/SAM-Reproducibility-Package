#!/usr/bin/env python3
"""Validate the full-data Phase 28 receiver-corruption report."""

import json
import math
import sys
from pathlib import Path


def fail(message):
    raise SystemExit("Validation failed: " + message)


if len(sys.argv) != 2:
    raise SystemExit("Usage: validate_report.py REPORT.json")

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("schema") != "sam.phase28.single-receiver-corruption.v1":
    fail("schema")
if not math.isclose(
    report["configuration"]["physical_threshold_ns"],
    306.64062122826,
    abs_tol=1e-9,
):
    fail("threshold")

baseline = report["baseline"]
expected = {
    "eligible_rows": 82_986,
    "available_rows": 78_358,
    "reference_pair_trials": 304_814,
    "PHYSICALLY_CONSISTENT": 77_309,
    "PHYSICALLY_CONFLICTING": 1_049,
    "PHYSICAL_EVIDENCE_UNAVAILABLE": 4_628,
}
for key, value in expected.items():
    if baseline.get(key) != value:
        fail(f"baseline {key}: {baseline.get(key)} != {value}")

signed = report["signed_offset_results"]
magnitudes = report["configuration"]["timestamp_offset_magnitudes_ns"]
expected_offsets = sorted([-value for value in magnitudes] + magnitudes)
if [item["timestamp_offset_ns"] for item in signed] != expected_offsets:
    fail("signed offsets")

anchor_trials = None
for item in signed:
    reference = item["decision_reference_corruption"]
    nonreference = item["single_nonreference_corruption"]
    anchor = item["calibration_reference_corruption"]
    if reference["trials"] != 78_358:
        fail("decision-reference trial count")
    if nonreference["trials"] != 304_814:
        fail("nonreference trial count")
    if anchor_trials is None:
        anchor_trials = anchor["trials"]
    if anchor["trials"] != anchor_trials or anchor_trials <= 0:
        fail("calibration-reference trial count")
    for result in (reference, nonreference, anchor):
        if result["result_consistent"] + result["result_conflicting"] != result["trials"]:
            fail("result-state total")
        if (
            result["baseline_consistent_trials"]
            + result["baseline_conflicting_trials"]
            != result["trials"]
        ):
            fail("baseline-state total")

coverage = report["calibration_reference_coverage"]
if coverage["rows_containing_calibration_reference"] != anchor_trials:
    fail("calibration-reference coverage")
if (
    coverage["as_decision_reference"] + coverage["as_nonreference"]
    != coverage["rows_containing_calibration_reference"]
):
    fail("calibration-reference role total")

if len(report["absolute_magnitude_summary"]) != len(magnitudes):
    fail("magnitude summary length")

print("SAM Phase 28 receiver-corruption validation passed.")

