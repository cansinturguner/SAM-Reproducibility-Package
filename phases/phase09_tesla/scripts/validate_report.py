#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase9.tesla-delayed-auth.v1"
    config = report["configuration"]
    assert config["key_bits"] == 128
    assert config["transmitted_tag_bits"] == 128
    assert config["sequence_bits"] == 8
    assert config["disclosure_delay_intervals"] == 1
    expected_messages = int(
        (
            Decimal(str(config["duration_seconds"]))
            * Decimal(str(config["message_rate_per_second"]))
        ).to_integral_value(rounding=ROUND_FLOOR)
    )
    assert config["transmitted_messages_per_replicate"] == expected_messages, (
        "workload count mismatch: "
        f"expected {expected_messages}, got "
        f"{config['transmitted_messages_per_replicate']}"
    )
    for name, value in report["correctness"].items():
        assert value is True, f"correctness check failed: {name}={value!r}"
    scenarios = report["scenarios"]
    assert scenarios and scenarios[0]["independent_type_a_and_b1_loss_probability"] == 0.0
    assert scenarios[0]["authentication_availability_vs_transmitted"]["mean"] == 1.0
    previous = 1.0
    for scenario in scenarios:
        availability = scenario["authentication_availability_vs_transmitted"]["mean"]
        assert 0.0 <= availability <= 1.0
        assert availability <= previous + 0.01
        previous = availability
    assert report["benchmark"]["total_wall_seconds"] > 0
    assert report["benchmark"]["peak_rss_mib"] > 0
    print("SAM Phase 9 report validation passed.")


if __name__ == "__main__":
    main()
