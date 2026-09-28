#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert r["schema"] == "sam.phase21.component-latency.v1"
assert r["configuration"]["measured_repetitions"] >= 5
assert r["configuration"]["eligible_rows_per_repetition"] == 82986
c = r["frozen_validation"]["counts"]
assert c["crypto_verified"] == 82986
assert c["physical_supported"] == 78358
assert c["VERIFIED"] == 78358
assert c["INSUFFICIENT_EVIDENCE"] == 4628
assert c["CONFLICTING"] == 0
for name, d in r["pooled_latency_microseconds"].items():
    assert d["n"] > 0, name
    assert d["minimum"] <= d["median"] <= d["q95"] <= d["q99"] <= d["maximum"], name
s = r["mean_component_share_of_timed_component_sum"]
total = s["crypto_fraction"] + s["physical_direct_tdoa_fraction"] + s["fusion_fraction"]
assert abs(total - 1.0) < 1e-9
print("SAM Phase 21 report validation passed.")
