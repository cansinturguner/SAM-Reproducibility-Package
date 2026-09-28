#!/usr/bin/env python3
import json
import math
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")

with open(sys.argv[1], encoding="utf-8") as f:
    r = json.load(f)

assert r["schema"] == "sam.phase24.rf-waveform-feasibility.v2"
assert r["scope"]["gnu_radio_used"] is False
assert r["scope"]["sdr_hardware_used"] is False
assert r["scope"]["rf_transmission_performed"] is False
assert r["configuration"]["overlay_bits"] == 336
assert r["configuration"]["reference_bits"] == 12
assert r["configuration"]["security_bits"] == 204
assert r["configuration"]["parity_bits"] == 120
assert r["configuration"]["rs_code"] == "RS(54,34) over GF(64)"
assert r["configuration"]["rs_correction_radius_symbols"] == 10
assert r["correctness"]["gf64_field_cycle_has_63_nonzero_elements"]
assert r["correctness"]["rs_codeword_syndromes_zero"]
assert r["correctness"]["reedsolo_encoder_matches_internal_encoder"]
assert r["correctness"]["actual_decoder_corrects_deterministic_10_symbol_error_vector"]
assert r["correctness"]["noiseless_overlay_round_trip"]
assert r["correctness"]["ppm_waveform_structure"]

rows = r["ebno_results"]
assert len(rows) >= 3
assert [x["ebno_db"] for x in rows] == sorted(x["ebno_db"] for x in rows)
for x in rows:
    assert x["packets"] >= 1000
    assert x["overlay_bits_tested"] == x["packets"] * 324
    assert 0 <= x["raw_overlay_ber"] <= 1
    assert 0 <= x["raw_security_payload_ber"] <= 1
    assert 0 <= x["rs_bounded_distance_recoverable_fraction"] <= 1
    d = x["actual_rs_decoder"]
    assert d["correct_payload_packets"] + d["declared_failure_packets"] + d["miscorrected_payload_packets"] == x["packets"]
    assert d["correct_payload_packets"] >= x["rs_bounded_distance_recoverable_packets"]
    assert 0 <= d["correct_payload_fraction"] <= 1
    assert 0 <= d["declared_failure_fraction"] <= 1
    assert 0 <= d["miscorrection_fraction"] <= 1
    ci = x["raw_overlay_ber_ci95_exact"]
    assert 0 <= ci["low"] <= x["raw_overlay_ber"] <= ci["high"] <= 1

assert math.isclose(
    r["waveform_smoke_test"]["duration_microseconds"], 112.0,
    rel_tol=0, abs_tol=1e-12,
)
assert rows[-1]["packets"] == r["configuration"]["highest_ebno_packets"]
print("SAM Phase 24 RF waveform feasibility v2 report validation passed.")
