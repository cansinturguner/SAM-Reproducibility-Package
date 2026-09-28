#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase11.evidence-fusion.v1"
    assert report["fusion_truth_table_pass_fraction"] == 1.0
    assert all(row["passed"] for row in report["fusion_truth_table"])
    variants = {row["id"]: row for row in report["component_wise_A0_A7"]}
    assert set(variants) == {f"A{i}" for i in range(8)}
    assert variants["A0"]["output_for_valid_input"] == "LEGACY_UNASSURED"
    assert variants["A1"]["output_for_valid_input"] == "VERIFIED"
    assert variants["A2"]["output_for_valid_input"] == "INSUFFICIENT_EVIDENCE"
    assert variants["A3"]["output_for_valid_input"] == "INSUFFICIENT_EVIDENCE"
    assert variants["A4"]["evaluation_status"] == "NOT_EVALUATED"
    assert variants["A5"]["evaluation_status"] == "NOT_EVALUATED"
    assert variants["A6"]["valid_cache_output"] == "VERIFIED"
    assert variants["A6"]["cold_or_expired_cache_output"] == "INSUFFICIENT_EVIDENCE"
    assert variants["A7"]["crypto_only_output"] == "VERIFIED"
    assert variants["A7"]["physical_only_output"] == "VERIFIED"
    assert report["decision_time_microseconds"]["median"] > 0
    assert report["peak_rss_mib"] > 0
    assert report["source_evidence_summary"]["phase9_synthetic_tesla"]["messages_per_replicate"] == 3720
    print("SAM Phase 11 report validation passed.")


if __name__ == "__main__":
    main()

