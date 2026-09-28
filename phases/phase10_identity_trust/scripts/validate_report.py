#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED_STATES = {
    "online_valid": "VERIFIED",
    "offline_valid_cache": "VERIFIED",
    "offline_cold_start": "INSUFFICIENT_EVIDENCE",
    "offline_expired_cache": "INSUFFICIENT_EVIDENCE",
    "online_revoked_record": "CONFLICTING",
}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase10.identity-trust.v1"
    config = report["configuration"]
    assert config["signature_algorithm"] == "ECDSA P-256 with SHA-256"
    assert config["hmac_tag_bits"] == 128
    assert config["interval_key_bits"] == 128
    for name, value in report["correctness"].items():
        assert value is True, f"correctness check failed: {name}={value!r}"
    actual = {
        scenario["name"]: scenario["assurance_state"]
        for scenario in report["trust_service_scenarios"]
    }
    assert actual == EXPECTED_STATES, f"unexpected assurance states: {actual!r}"
    sizes = report["logical_communication_bytes_excluding_rf_framing_and_fec"]
    assert sizes["compressed_aircraft_public_key"] == 33
    assert sizes["ca_signature"] == 64
    assert sizes["compact_ca_record_total"] == 97
    assert sizes["signed_b2_content_total"] == 80
    for metrics in report["timing_microseconds_per_operation"].values():
        assert metrics["n"] >= 2
        assert metrics["median"] > 0
        assert metrics["q95"] >= metrics["q05"]
    assert report["peak_rss_mib"] > 0
    print("SAM Phase 10 report validation passed.")


if __name__ == "__main__":
    main()

