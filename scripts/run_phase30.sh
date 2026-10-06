#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-python}"
DIR="phases/phase30_reference_independent_guard"
"$PYTHON_BIN" "$DIR/scripts/self_test.py"
"$PYTHON_BIN" "$DIR/scripts/run_reference_independent_guard.py" \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model data/processed/locards_subset_1/phase25a_physical_decision_model.json \
  --report reports/sam_phase30_reference_independent_receiver_guard.json
"$PYTHON_BIN" "$DIR/scripts/validate_report.py" reports/sam_phase30_reference_independent_receiver_guard.json
