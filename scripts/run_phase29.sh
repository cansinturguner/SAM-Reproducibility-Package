#!/usr/bin/env bash
set -euo pipefail

python phases/phase29_threshold_operating_point/scripts/self_test.py

python phases/phase29_threshold_operating_point/scripts/run_threshold_sensitivity.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model data/processed/locards_subset_1/phase25a_physical_decision_model.json \
  --phase25b-report reports/sam_phase25b_controlled_attack_sensitivity.json \
  --report reports/sam_phase29_threshold_operating_point.json \
  --csv reports/sam_phase29_threshold_operating_point.csv

python phases/phase29_threshold_operating_point/scripts/validate_report.py \
  reports/sam_phase29_threshold_operating_point.json
