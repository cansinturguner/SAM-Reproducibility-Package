#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert r["schema"] == "sam.phase22.external-validation.v1"
assert r["configuration"]["clock_model"] == "frozen subset-1 bias_only"
assert r["configuration"]["minimum_modeled_receivers"] == 4
assert r["configuration"]["receiver_geometry_rank"] == 3
assert r["inputs"]["sha256"]["observations"] == "5ff68c7e402caa183678c03f4d23ba45b63bc96fa1177f8ce7e4fb530c45dd58"
assert r["inputs"]["sha256"]["sensors"] == "998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b"
assert r["counts"]["rows_read"] == 6535444
assert r["counts"]["external_eligible_good_ge4_rows"] > 0
assert r["counts"]["hmac_verified_rows"] == r["counts"]["external_eligible_good_ge4_rows"]
assert r["counts"]["VERIFIED"] == r["counts"]["physical_supported_rows"]
assert r["counts"]["CONFLICTING"] == 0
assert 0 <= r["availability"]["fraction"] <= 1
assert r["pair_residuals"]["n"] > 0
ci = r["aircraft_clustered_confidence_intervals"]["availability_weighted_by_rows"]
assert ci["ci95_low"] <= ci["estimate"] <= ci["ci95_high"]
print("SAM Phase 22 external-validation report passed.")
