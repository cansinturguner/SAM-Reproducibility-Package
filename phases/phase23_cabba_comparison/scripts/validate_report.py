#!/usr/bin/env python3
import json
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)

assert report["schema"] == "sam.phase23.cabba-comparison.v1"
assert report["provenance"]["original_author_code_used"] is False
assert all(report["correctness"].values())
assert report["configuration"]["cabba_published_parameters"]["tesla_interval_seconds"] == 5.0
assert report["configuration"]["cabba_published_parameters"]["type_A_mac_bits"] == 196
assert len(report["cabba_published_schedule_accounting"]) == 4
assert report["cabba_published_schedule_accounting"][-1]["TB2_seconds"] == 15.0
assert report["cabba_published_schedule_accounting"][-1]["TC_seconds"] == 30.0
assert report["protocol_latency_seconds"]["CABBA_nominal_next_interval_disclosure"] == 5.0
assert set(report["scheduled_receiver_compute_microseconds_per_message"]) == {
    "CABBA_scenario_4",
    "SAM_frozen_crypto_trust_fusion_schedule",
}
assert report["functional_coverage"]["CABBA_reproduction"]["phase_overlay_implemented_here"] is False
assert report["functional_coverage"]["SAM_comparator_row"]["physical_cross_sensor_corroboration"] is False
print("SAM Phase 23 CABBA comparison report validation passed.")
