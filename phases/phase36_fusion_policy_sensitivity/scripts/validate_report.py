#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase36.fusion-policy-sensitivity.v1"
    assert all(report["correctness"].values())
    assert report["finite_state"]["combinations"] == 48
    if report["phase34_replay"] is not None:
        eligible = report["phase34_replay"]["eligible_rows"]
        for scenario in report["phase34_replay"]["scenarios"]:
            assert sum(scenario["strict_conflict_dominant"].values()) == eligible
            assert sum(scenario["corroborated_conflict"].values()) == eligible
    print("SAM Phase 36 fusion-policy sensitivity validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

