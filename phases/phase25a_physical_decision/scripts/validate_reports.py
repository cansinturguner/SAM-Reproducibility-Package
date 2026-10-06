#!/usr/bin/env python3
import json
import sys


if len(sys.argv) not in (3, 4):
    raise SystemExit("usage: validate_reports.py MODEL.json SUBSET1.json [SUBSET2.json]")

model = json.load(open(sys.argv[1], encoding="utf-8"))
primary = json.load(open(sys.argv[2], encoding="utf-8"))
assert model["schema"] == "sam.phase25a.physical-decision-model.v1"
assert primary["schema"] == "sam.phase25a.physical-decision-validation.v1"
assert model["test_partition_used_for_threshold_selection"] is False
assert model["subset2_used_for_threshold_selection"] is False
assert model["threshold_ns"] >= 0
assert primary["decision_model"] == model
assert primary["aircraft_partitions"]["overlap"] == 0
for part in (primary["development_validation"], primary["subset1_frozen_test"]):
    assert part["original_ge4_rows"] >= part["physically_available_rows"] > 0
states = primary["subset1_frozen_test"]["states"]
assert sum(states.values()) == primary["subset1_frozen_test"]["original_ge4_rows"]
assurance = primary["subset1_frozen_test"]["full_policy_assurance_with_valid_crypto_and_trust"]
assert assurance["VERIFIED"] == states.get("PHYSICALLY_CONSISTENT", 0)
assert assurance["CONFLICTING"] == states.get("PHYSICALLY_CONFLICTING", 0)
assert assurance["INSUFFICIENT_EVIDENCE"] == states.get("PHYSICAL_EVIDENCE_UNAVAILABLE", 0)

if len(sys.argv) == 4:
    external = json.load(open(sys.argv[3], encoding="utf-8"))
    assert external["schema"] == "sam.phase25a.subset2-transfer.v1"
    assert external["threshold_ns"] == model["threshold_ns"]
    c = external["counts"]
    assert c["trusted_good_ge4_rows"] == c.get("PHYSICALLY_CONSISTENT", 0) + c.get("PHYSICALLY_CONFLICTING", 0) + c.get("PHYSICAL_EVIDENCE_UNAVAILABLE", 0)

print("SAM Phase 25A report validation passed.")
