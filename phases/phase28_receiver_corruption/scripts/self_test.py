#!/usr/bin/env python3
"""Check the corruption mechanics without loading LocaRDS."""

import importlib.util
import os
from pathlib import Path

import numpy as np

default_phase27 = (
    Path(__file__).resolve().parents[2]
    / "phase27_threshold_aware_integration"
    / "scripts"
)
if not default_phase27.exists():
    workspace_root = Path(__file__).resolve().parents[4]
    os.environ.setdefault(
        "SAM_PHASE27_SCRIPTS",
        str(
            workspace_root
            / "Phase27_Threshold_Aware"
            / "phases"
            / "phase27_threshold_aware_integration"
            / "scripts"
        ),
    )

module_path = Path(__file__).with_name("run_receiver_corruption.py")
spec = importlib.util.spec_from_file_location("phase28", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
core = module.core

threshold = 306.64062122826
residuals = np.asarray([0.0, 0.0, 0.0])

reference_score = module.shifted_score_ns(residuals, 1000.0, None)
single_nonreference_score = module.shifted_score_ns(residuals, 1000.0, 0)

assert reference_score == 1000.0
assert single_nonreference_score == 0.0
assert core.classify_score(reference_score, threshold) == core.PHYSICALLY_CONFLICTING
assert core.classify_score(single_nonreference_score, threshold) == core.PHYSICALLY_CONSISTENT

accumulator = module.new_accumulator()
module.update_accumulator(
    accumulator, core.PHYSICALLY_CONSISTENT, core.PHYSICALLY_CONFLICTING
)
finalized = module.finalize_accumulator(accumulator)
assert finalized["consistent_to_conflicting"] == 1
assert finalized["consistent_to_conflicting_fraction"] == 1.0

print("SAM Phase 28 receiver-corruption self-test passed.")
