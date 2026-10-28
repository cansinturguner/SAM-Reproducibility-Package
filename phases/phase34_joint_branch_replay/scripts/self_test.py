#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    fixture = REPO_ROOT / "phases" / "phase25a_physical_decision" / "test_fixture"
    with tempfile.TemporaryDirectory() as directory:
        model = Path(directory) / "model.json"
        model.write_text(
            json.dumps(
                {
                    "schema": "sam.phase25a.physical-decision-model.v1",
                    "score": "median absolute calibrated direct-TDoA reference-pair residual per observation",
                    "score_units": "nanoseconds",
                    "threshold_ns": 306.64062122826,
                    "minimum_modeled_receivers": 4,
                    "required_geometry_rank": 3,
                    "input_sha256": {},
                }
            ),
            encoding="utf-8",
        )
        report = Path(directory) / "report.json"
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("run_phase34.py")),
                "--selected", str(fixture / "selected.csv.gz"),
                "--sensors", str(fixture / "sensors.csv"),
                "--calibration", str(fixture / "calibration.json"),
                "--decision-model", str(model),
                "--report", str(report),
                "--skip-hash-check",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name("validate_report.py")), str(report)],
            check=True,
        )
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["population"]["eligible_rows"] == 80
    print("SAM Phase 34 fixture self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

