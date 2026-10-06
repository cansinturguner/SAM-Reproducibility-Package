#!/usr/bin/env python3
import json
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["schema"] == "sam.phase25c.injection-dataset-audit.v2"
assert r["source"]["doi"] == "10.17632/6fhw732ccz.1"
assert r["source"]["license"] == "CC BY 4.0"
data = r["files"]["dataset"]
assert data["rows"] > 0
assert len(data["sha256"]) == 64
assert r["suitability"]["automatic_integration_performed"] is False
checks = r["published_metadata_checks"]
assert checks["observed_predictor_feature_count"] == data["column_count"] - 1
if checks["predictor_feature_count_matches_17"]:
    assert checks["observed_predictor_feature_count"] == 17
if checks["total_columns_match_17_features_plus_label"]:
    assert data["column_count"] == 18 and data["label_column"] is not None
if r["published_metadata_checks"]["row_count_matches_22316"]:
    assert data["rows"] == 22316
if r["published_metadata_checks"]["observed_label_set_matches_0_1_2_3"]:
    assert set(data["label_counts"]) == {"0", "1", "2", "3"}
print("SAM Phase 25C report validation passed.")
