#!/usr/bin/env bash
set -euo pipefail
python phases/phase33_sam_airtime/scripts/run_phase33.py \
  --report reports/sam_phase33_sam_airtime.json
python phases/phase33_sam_airtime/scripts/validate_report.py \
  reports/sam_phase33_sam_airtime.json
