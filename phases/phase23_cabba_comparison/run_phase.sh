#!/usr/bin/env bash
set -euo pipefail

PHASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PHASE_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
mkdir -p reports

"$PYTHON_BIN" phases/phase23_cabba_comparison/scripts/run_phase23.py \
  --report reports/sam_phase23_cabba_comparison.json \
  --seed 1103 \
  --message-count 10000 \
  --repetitions 10 \
  --message-rate 6.2

"$PYTHON_BIN" phases/phase23_cabba_comparison/scripts/validate_report.py \
  reports/sam_phase23_cabba_comparison.json
