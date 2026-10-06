#!/usr/bin/env bash
set -euo pipefail

PHASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PHASE_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DATA_DIR="${PHASE25C_DATA_DIR:-$ROOT_DIR/data/external/mendeley_adsb_injection}"

cd "$ROOT_DIR"
mkdir -p reports

if [[ ! -f "$DATA_DIR/Dataset.csv" ]]; then
  echo "Missing $DATA_DIR/Dataset.csv" >&2
  echo "Download version 1 from https://doi.org/10.17632/6fhw732ccz.1" >&2
  exit 2
fi

EXTRA=()
if [[ -f "$DATA_DIR/Receiver messages.csv" ]]; then
  EXTRA+=(--receiver-messages-csv "$DATA_DIR/Receiver messages.csv")
fi

"$PYTHON_BIN" "$PHASE_DIR/scripts/audit_phase25c.py" \
  --dataset-csv "$DATA_DIR/Dataset.csv" \
  "${EXTRA[@]}" \
  --report reports/sam_phase25c_injection_dataset_audit.json

"$PYTHON_BIN" "$PHASE_DIR/scripts/validate_report.py" \
  reports/sam_phase25c_injection_dataset_audit.json
