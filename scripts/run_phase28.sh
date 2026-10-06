#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
PHASE_DIR="phases/phase28_receiver_corruption"
PHASE27_DIR="phases/phase27_threshold_aware_integration"

"$PYTHON_BIN" "$PHASE_DIR/scripts/self_test.py"

"$PYTHON_BIN" "$PHASE_DIR/scripts/run_receiver_corruption.py" \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model "$PHASE27_DIR/configs/phase25a_physical_decision_model.json" \
  --report reports/sam_phase28_receiver_corruption.json

"$PYTHON_BIN" "$PHASE_DIR/scripts/validate_report.py" \
  reports/sam_phase28_receiver_corruption.json

