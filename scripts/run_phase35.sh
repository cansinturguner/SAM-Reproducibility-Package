#!/usr/bin/env bash
set -euo pipefail
python phases/phase35_protocol_robustness/scripts/run_phase35.py \
  --report reports/sam_phase35_protocol_robustness.json
python phases/phase35_protocol_robustness/scripts/validate_report.py \
  reports/sam_phase35_protocol_robustness.json
