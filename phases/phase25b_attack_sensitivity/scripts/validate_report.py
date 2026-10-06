#!/usr/bin/env python3
import json
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["schema"] == "sam.phase25b.controlled-attack-sensitivity.v1"
assert r["methodological_source"]["doi"] == "10.3390/s21154992"
assert "adaptation only" in r["methodological_source"]["relationship"]
n = r["counts"]["physically_available_subset1_test_rows"]
assert n > 0
assert "0" in r["position_bias_sensitivity"] or "0.0" in r["position_bias_sensitivity"]
for row in r["position_bias_sensitivity"].values():
    assert row["available_rows"] == n
    assert row["PHYSICALLY_CONSISTENT"] + row["PHYSICALLY_CONFLICTING"] == n
    assert 0 <= row["conflict_sensitivity"] <= 1
s = r["fixed_ground_spoofer_fake_track"]
assert s["PHYSICALLY_CONSISTENT"] + s["PHYSICALLY_CONFLICTING"] == n
print("SAM Phase 25B report validation passed.")
