#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_report.py REPORT.json")
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert report["schema"] == "sam.phase8.crypto-benchmark.v1"
    assert report["configuration"]["transmitted_hmac_tag_bits"] == 128
    assert report["configuration"]["root_key_bits"] == 512
    assert report["configuration"]["ecdsa_curve"] == "NIST P-256/secp256r1"
    for value in report["correctness"].values():
        assert value is True
    for metrics in report["timing_microseconds_per_message"].values():
        assert metrics["n"] >= 2
        assert metrics["median"] > 0
        assert metrics["q95"] >= metrics["q05"]
    print("SAM Phase 8 report validation passed.")


if __name__ == "__main__":
    main()

