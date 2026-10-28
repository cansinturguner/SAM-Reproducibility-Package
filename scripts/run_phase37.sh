#!/usr/bin/env bash
set -euo pipefail
python phases/phase37_denominator_audit/scripts/run_phase37.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --subset1-sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --subset2-observations data/raw/locards/subset_2/set_2.csv \
  --subset2-sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --subset2-aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model phases/phase27_threshold_aware_integration/configs/phase25a_physical_decision_model.json \
  --report reports/sam_phase37_denominator_audit.json
python phases/phase37_denominator_audit/scripts/validate_report.py reports/sam_phase37_denominator_audit.json
