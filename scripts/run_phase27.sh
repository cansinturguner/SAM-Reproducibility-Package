#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
PHASE_DIR="phases/phase27_threshold_aware_integration"

"$PYTHON_BIN" "$PHASE_DIR/scripts/self_test.py"

"$PYTHON_BIN" "$PHASE_DIR/scripts/run_integrated.py" \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model "$PHASE_DIR/configs/phase25a_physical_decision_model.json" \
  --warmups 1 \
  --repetitions 30 \
  --report reports/sam_phase27a_threshold_aware_integrated.json

"$PYTHON_BIN" "$PHASE_DIR/scripts/run_outage.py" \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model "$PHASE_DIR/configs/phase25a_physical_decision_model.json" \
  --repetitions 5 \
  --cache-ttl-seconds 900 \
  --retry-interval-seconds 60 \
  --report reports/sam_phase27b_threshold_aware_outage.json

"$PYTHON_BIN" "$PHASE_DIR/scripts/validate_reports.py" \
  reports/sam_phase27a_threshold_aware_integrated.json \
  reports/sam_phase27b_threshold_aware_outage.json

