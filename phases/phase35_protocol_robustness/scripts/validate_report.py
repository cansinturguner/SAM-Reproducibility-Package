#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase35.protocol-robustness.v1"
    assert all(report["correctness"].values())
    assert len(report["burst_loss"]) == 3
    assert len(report["late_packet_and_clock_uncertainty"]) == 16
    assert all(report["downgrade_routing"]["checks"].values())
    print("SAM Phase 35 protocol robustness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

