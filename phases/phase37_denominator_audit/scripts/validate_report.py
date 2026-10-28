#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

def main():
    if len(sys.argv)!=2: raise SystemExit("usage: validate_report.py REPORT.json")
    r=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert r["schema"]=="sam.phase37.denominator-audit.v1"
    for subset in ("subset1","subset2"):
        assert r["benign_reference_conflict_attribution"][subset]["conflicting_rows"]>=0
    base=r["position_bias_sensitivity"]["0.0"]
    assert abs(base["baseline_adjusted_gain"])<1e-15
    assert base["baseline_adjusted_gain_ci95"] is None
    assert 0<r["availability_denominators"]["subset1"]["end_to_end_yield_from_complete_test_partition"]<=1
    print("SAM Phase 37 denominator and artifact audit validation passed.")

if __name__=="__main__": main()

