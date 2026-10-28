#!/usr/bin/env bash
set -euo pipefail

python phases/phase34_joint_branch_replay/scripts/run_phase34.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model phases/phase27_threshold_aware_integration/configs/phase25a_physical_decision_model.json \
  --report reports/sam_phase34_joint_branch_replay.json

python phases/phase34_joint_branch_replay/scripts/validate_report.py \
  reports/sam_phase34_joint_branch_replay.json
