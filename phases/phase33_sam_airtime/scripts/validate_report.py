#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase33.reference-transport-airtime.v1"
    assert report["configuration"]["scenario_count"] == 36
    assert all(report["correctness"].values())
    canonical = report["canonical_configuration"]
    assert canonical["policy"] == "P1_1s_single"
    assert canonical["message_rate_per_second"] == 6.2
    assert canonical["aircraft_count"] == 200
    assert canonical["per_aircraft"]["surveillance_frames"] == 22320
    assert canonical["per_aircraft"]["b1_additional_frames"] == 3600
    assert canonical["per_aircraft"]["b2_additional_frames"] == 240
    assert canonical["per_aircraft"]["total_additional_frames"] == 3840
    fraction = canonical["per_aircraft"]["analytical_added_airtime_fraction_vs_surveillance"]
    assert abs(fraction - 3840 / 22320) < 1e-15
    print("SAM Phase 33 reference-transport airtime validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

