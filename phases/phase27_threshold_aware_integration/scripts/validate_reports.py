#!/usr/bin/env python3
"""Validate Phase 27A and 27B full-data reports."""

import json
import math
import sys
from pathlib import Path


def fail(message: str):
    raise SystemExit("Validation failed: " + message)


if len(sys.argv) != 3:
    raise SystemExit("Usage: validate_reports.py INTEGRATED.json OUTAGE.json")

integrated = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
outage = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

if integrated.get("schema") != "sam.phase27a.threshold-aware-integrated.v1":
    fail("integrated schema")
if outage.get("schema") != "sam.phase27b.threshold-aware-trust-outage.v2":
    fail("outage schema")

counts = integrated["counts"]
expected = {
    "eligible_rows": 82_986,
    "hmac_verified": 82_986,
    "PHYSICALLY_CONSISTENT": 77_309,
    "PHYSICALLY_CONFLICTING": 1_049,
    "PHYSICAL_EVIDENCE_UNAVAILABLE": 4_628,
    "VERIFIED": 77_309,
    "CONFLICTING": 1_049,
    "INSUFFICIENT_EVIDENCE": 4_628,
}
for key, value in expected.items():
    if counts.get(key) != value:
        fail(f"integrated {key}: {counts.get(key)} != {value}")
if not math.isclose(
    integrated["configuration"]["physical_threshold_ns"],
    306.64062122826,
    abs_tol=1e-9,
):
    fail("threshold")
if integrated["configuration"]["measured_fresh_process_repetitions"] < 5:
    fail("integrated repetitions")

if len(outage["scenarios"]) != 5:
    fail("outage scenario count")
if not all(outage["correctness"].values()):
    fail("outage correctness flags")
for scenario in outage["scenarios"]:
    scenario_counts = scenario["counts"]
    if scenario_counts["eligible_rows"] != 82_986:
        fail(f"{scenario['name']} eligible count")
    if scenario_counts["PHYSICALLY_CONSISTENT"] != 77_309:
        fail(f"{scenario['name']} consistent count")
    if scenario_counts["PHYSICALLY_CONFLICTING"] != 1_049:
        fail(f"{scenario['name']} conflict count")
    if scenario_counts["PHYSICAL_EVIDENCE_UNAVAILABLE"] != 4_628:
        fail(f"{scenario['name']} unavailable count")
    if (
        scenario_counts["VERIFIED"]
        + scenario_counts["CONFLICTING"]
        + scenario_counts["INSUFFICIENT_EVIDENCE"]
        != 82_986
    ):
        fail(f"{scenario['name']} final-state total")
    if scenario["outage_at_seconds"] is not None:
        if (
            scenario_counts["pre_outage_rows"]
            + scenario_counts["post_outage_rows"]
            != 82_986
        ):
            fail(f"{scenario['name']} outage partition total")
        if (
            scenario_counts["post_outage_trust_valid"]
            + scenario_counts["post_outage_trust_stale_or_absent"]
            != scenario_counts["post_outage_rows"]
        ):
            fail(f"{scenario['name']} post-outage trust total")
        if (
            scenario_counts["post_outage_VERIFIED"]
            + scenario_counts["post_outage_CONFLICTING"]
            + scenario_counts["post_outage_INSUFFICIENT_EVIDENCE"]
            != scenario_counts["post_outage_rows"]
        ):
            fail(f"{scenario['name']} post-outage state total")

offset = next(
    scenario for scenario in outage["scenarios"]
    if scenario["name"] == "outage_offset_2250s"
)
if offset["counts"]["post_outage_trust_valid"] <= 0:
    fail("offset outage has no post-outage valid-cache rows")
if (
    offset["post_outage_cache_observation"][
        "observed_valid_cache_span_after_outage_seconds"
    ]
    <= 0
):
    fail("offset outage has no observed cache-grace span")
if offset["counts"]["post_outage_trust_stale_or_absent"] <= 0:
    fail("offset outage never reaches stale trust")

print("SAM Phase 27 threshold-aware integrated/outage validation passed.")

