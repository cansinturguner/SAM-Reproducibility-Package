#!/usr/bin/env python3
import json
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["schema"] == "sam.phase16.communication-overhead.v1"
assert r["correctness"]["scenario_count"] == 36
assert r["correctness"]["all_breakdowns_sum"] is True
assert r["correctness"]["aircraft_scaling_does_not_change_per_aircraft_cost"] is True
assert len(r["correctness"]["scenario_sha256"]) == 64
assert len(r["scenarios"]) == 36
assert all(x["logical_security_bytes_per_message"] > 17 for x in r["scenarios"])
assert all(x["aggregate_logical_security_kbit_per_second"] > 0 for x in r["scenarios"])
assert r["canonical_configuration"]["policy"] == "P1_1s_single"
assert r["canonical_configuration"]["message_rate_per_second"] == 6.2
print("SAM Phase 16 report validation passed.")

