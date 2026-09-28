#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: validate_report.py REPORT.json")
r = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert r["schema"] == "sam.phase20.concurrent-scalability.v1"
assert r["configuration"]["concurrency_levels"] == [1, 2, 4]
assert r["configuration"]["measured_repetitions_per_level"] >= 5
assert r["frozen_validation"]["per_worker_counts"]["test_original_ge4_rows"] == 82986
assert r["frozen_validation"]["per_worker_counts"]["physical_supported_rows"] == 78358
assert r["frozen_validation"]["per_worker_assurance_states"]["VERIFIED"] == 78358
assert r["frozen_validation"]["per_worker_assurance_states"]["INSUFFICIENT_EVIDENCE"] == 4628
assert len(r["scenarios"]) == 3
for s in r["scenarios"]:
    assert s["aggregate_throughput_observations_per_second"]["n"] >= 5
    assert s["aggregate_throughput_observations_per_second"]["median"] > 0
    assert s["speedup_vs_single_worker_median"] > 0
    assert s["parallel_efficiency"] > 0
print("SAM Phase 20 report validation passed.")
