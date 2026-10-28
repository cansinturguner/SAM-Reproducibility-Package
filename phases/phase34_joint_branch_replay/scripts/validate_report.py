#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase34.joint-branch-replay.v1"
    assert report["configuration"]["scenario_count"] == 6
    assert report["population"]["eligible_rows"] > 0
    assert all(report["cross_scenario_checks"].values())
    names = {item["name"] for item in report["scenarios"]}
    assert names == {
        "S0_all_valid_reference",
        "S1_crypto_conflict_1pct",
        "S2_crypto_pending_10pct",
        "S3_trust_revoked_1pct",
        "S4_trust_stale_10pct",
        "S5_joint_controlled_interaction",
    }
    print("SAM Phase 34 joint branch replay validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

