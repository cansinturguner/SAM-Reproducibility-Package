#!/usr/bin/env python3
"""Small deterministic checks for Phase 29 helpers."""

import importlib.util
import math
from pathlib import Path

import numpy as np


path = Path(__file__).with_name("run_threshold_sensitivity.py")
spec = importlib.util.spec_from_file_location("phase29", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

values = np.asarray([1.0, 2.0, 3.0, 4.0])
assert module.higher_quantile(values, 0.50) == 3.0
assert module.aircraft_group("abc", 1103, 70) in {"calibration", "validation"}
lat, lon = module.destination(0.0, 0.0, 1000.0, math.pi / 2.0)
assert abs(lat) < 1e-6
assert 0.008 < lon < 0.010
assert math.isclose(
    module.deterministic_bearing(1103, "row-1", 100.0),
    module.deterministic_bearing(1103, "row-1", 100.0),
)

benign = np.asarray([1.0, 2.0, 5.0])
attacked = np.asarray([4.0, 1.0, 6.0])
result = module.paired_result(benign, attacked, 3.0)
assert math.isclose(result["attacked_conflict_fraction_all_available"], 2 / 3)
assert math.isclose(result["consistent_to_conflicting_fraction"], 1 / 2)
assert result["conflicting_to_consistent_fraction"] == 0.0
print("SAM Phase 29 self-test passed.")
