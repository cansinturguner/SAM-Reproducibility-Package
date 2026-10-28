#!/usr/bin/env bash
set -euo pipefail

bash scripts/run_phase33.sh
bash scripts/run_phase34.sh
bash scripts/run_phase35.sh
bash scripts/run_phase36.sh
bash scripts/run_phase37.sh

if [[ -f reports/sam_phase31_development_events.csv.gz \
   && -f reports/sam_phase31_subset1_events.csv.gz \
   && -f reports/sam_phase31_subset2_events.csv.gz ]]; then
  python phases/phase32_track_persistence/scripts/run_phase32.py \
    --development-events reports/sam_phase31_development_events.csv.gz \
    --subset1-events reports/sam_phase31_subset1_events.csv.gz \
    --subset2-events reports/sam_phase31_subset2_events.csv.gz \
    --report reports/sam_phase32_track_persistence_v3.json
  python phases/phase32_track_persistence/scripts/validate_report.py \
    reports/sam_phase32_track_persistence_v3.json
else
  echo "Phase 31 event files not found; Phase 32 v3 rerun skipped." >&2
fi

