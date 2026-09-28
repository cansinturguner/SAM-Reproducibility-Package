#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bash phases/phase23_cabba_comparison/run_phase.sh
bash phases/phase24_rf_waveform_feasibility/run_phase.sh

echo "SAM Phases 23 and 24 completed and validated."
