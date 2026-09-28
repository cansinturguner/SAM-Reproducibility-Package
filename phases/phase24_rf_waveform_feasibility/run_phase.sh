#!/usr/bin/env bash
set -euo pipefail

PHASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PHASE_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
mkdir -p reports

"$PYTHON_BIN" phases/phase24_rf_waveform_feasibility/scripts/run_phase24.py \
  --report reports/sam_phase24_rf_waveform_feasibility_v2.json \
  --seed 1103 \
  --packets-per-ebno 10000 \
  --highest-ebno-packets 20000 \
  --ebno-db 8 10 12 14 15 16 18

"$PYTHON_BIN" phases/phase24_rf_waveform_feasibility/scripts/validate_report.py \
  reports/sam_phase24_rf_waveform_feasibility_v2.json
