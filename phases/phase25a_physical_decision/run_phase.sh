#!/usr/bin/env bash
set -euo pipefail

PHASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PHASE_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
mkdir -p reports data/processed/locards_subset_1

"$PYTHON_BIN" "$PHASE_DIR/scripts/run_phase25a.py" \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --model-output data/processed/locards_subset_1/phase25a_physical_decision_model.json \
  --report reports/sam_phase25a_subset1_physical_decision.json \
  --seed 1103 --calibration-percent 70 --target-benign-consistency 0.99 --bootstrap-replicates 2000

"$PYTHON_BIN" "$PHASE_DIR/scripts/apply_subset2.py" \
  --observations data/raw/locards/subset_2/set_2.csv \
  --sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model data/processed/locards_subset_1/phase25a_physical_decision_model.json \
  --report reports/sam_phase25a_subset2_physical_decision.json \
  --seed 1103 --bootstrap-replicates 2000

"$PYTHON_BIN" "$PHASE_DIR/scripts/validate_reports.py" \
  data/processed/locards_subset_1/phase25a_physical_decision_model.json \
  reports/sam_phase25a_subset1_physical_decision.json \
  reports/sam_phase25a_subset2_physical_decision.json
