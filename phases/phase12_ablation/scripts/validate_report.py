#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase12.gating-tesla-ablation.v1"
    a4 = report["A4_receiver_geometry_gating"]
    assert a4["real_locards_test_original_ge4_rows"] == 82986
    assert a4["rows_supported_by_frozen_modeled_receiver_and_rank_rule"] == 78358
    assert a4["rows_without_sufficient_frozen_physical_support"] == 4628
    assert 0 < a4["unsupported_fraction"] < 1
    a5 = report["A5_tesla_chain_recovery"]
    assert a5["maximum_phase9_reproduction_absolute_error"] < 1e-12
    scenarios = a5["scenarios"]
    assert scenarios[0]["independent_type_a_and_b1_loss_probability"] == 0.0
    assert scenarios[0]["paired_chain_minus_direct_availability"]["mean"] == 0.0
    for scenario in scenarios:
        direct = scenario["direct_b1_only"]["authentication_availability_vs_received"]["mean"]
        recovered = scenario["tesla_chain_recovery"]["authentication_availability_vs_received"]["mean"]
        assert recovered + 1e-15 >= direct
        assert scenario["paired_unresolved_message_reduction"]["mean"] >= 0
    assert report["benchmark"]["wall_seconds"] > 0
    assert report["benchmark"]["peak_rss_mib"] > 0
    print("SAM Phase 12 report validation passed.")


if __name__ == "__main__":
    main()

