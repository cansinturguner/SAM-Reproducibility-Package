#!/usr/bin/env python3
"""Validate internal consistency and conservative claim boundaries."""

import json
import math
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"Validation failed: {message}")


if len(sys.argv) != 2:
    raise SystemExit("Usage: validate_report.py REPORT.json")

r = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if r.get("schema") != "sam.phase13.final-consolidation.v1":
    fail("unexpected schema")
if set(r.get("input_reports", {})) != {"phase5d", "phase6", "phase7", "phase8", "phase9", "phase10", "phase11", "phase12"}:
    fail("input report set is incomplete")
for name, item in r["input_reports"].items():
    if item["size_bytes"] <= 0 or len(item["sha256"]) != 64:
        fail(f"invalid source record for {name}")
if r["evidence_provenance"]["message_level_join_performed"] is not False:
    fail("message-level join must remain false")
physical = r["frozen_results"]["physical_cross_sensor"]
expected = physical["usable_test_rows"] / physical["original_test_ge4_rows"]
if not math.isclose(expected, physical["availability"], rel_tol=0, abs_tol=1e-12):
    fail("physical availability is inconsistent")
if r["frozen_results"]["fusion"]["truth_table_pass_fraction"] != 1.0:
    fail("fusion truth table did not fully pass")
if not r["frozen_results"]["cryptographic_primitives"]["negative_protocol_checks_passed"]:
    fail("cryptographic protocol checks did not all pass")
variants = r["final_A0_A7"]
if [x["id"] for x in variants] != [f"A{i}" for i in range(8)]:
    fail("A0-A7 ordering or completeness is invalid")
if variants[4]["variant"] != "No receiver/geometry gating":
    fail("A4 definition regressed")
if variants[5]["variant"] != "No TESLA key-chain recovery":
    fail("A5 definition regressed")
for forbidden in ("precision", "recall", "false-positive", "false-negative"):
    if forbidden not in " ".join(r["claim_boundaries"]).lower():
        fail(f"missing explicit {forbidden} boundary")
print("SAM Phase 13 report validation passed.")
