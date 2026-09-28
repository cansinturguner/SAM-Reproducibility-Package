#!/usr/bin/env python3
import json
import sys
from pathlib import Path

p = Path(sys.argv[1]) if len(sys.argv) == 2 else None
if p is None:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.loads(p.read_text(encoding="utf-8"))
assert r["schema"] == "sam.phase19b.system-boundary-comparison.v1"
rows = {x["method"]: x for x in r["comparison"]}
assert len(rows) == 5
sam = rows["SAM cached integrated path"]
assert sam["physical_support"]["eligible_rows"] == 82986
assert sam["physical_support"]["supported_rows"] == 78358
assert sam["functional_coverage"]["physical_cross_sensor"] is True
assert rows["TESLA-style post-disclosure HMAC"]["functional_coverage"]["physical_cross_sensor"] is False
assert rows["Legacy unauthenticated"]["functional_coverage"]["message_authentication"] is False
assert len(r["trust_refresh_amortization"]) == 3
for x in r["comparison"]:
    ci = x["bootstrap_ci95_microseconds"]
    assert ci["ci95_low"] <= ci["estimate"] <= ci["ci95_high"]
print("SAM Phase 19B report validation passed.")
