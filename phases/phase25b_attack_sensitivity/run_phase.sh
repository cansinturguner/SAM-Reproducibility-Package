#!/usr/bin/env bash
set -euo pipefail

PHASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PHASE_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
mkdir -p reports

"$PYTHON_BIN" "$PHASE_DIR/scripts/run_phase25b.py" \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model data/processed/locards_subset_1/phase25a_physical_decision_model.json \
  --report reports/sam_phase25b_controlled_attack_sensitivity.json \
  --seed 1103 --position-bias-m 0,100,250,400,500,750,1000,2000,5000,10000

"$PYTHON_BIN" "$PHASE_DIR/scripts/validate_report.py" \
  reports/sam_phase25b_controlled_attack_sensitivity.json
