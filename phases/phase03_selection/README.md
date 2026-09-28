# SAM Phase 3 LocaRDS Candidate Selection

This package creates the frozen candidate pool for physical verification. It does not run TDoA, choose a decision threshold, or report security performance.

## Run

From the existing `sam_phase1` folder:

```bash
source .venv/bin/activate
python /path/to/sam_phase3_selection/scripts/select_locards_candidates.py \
  --root data/raw/locards/subset_1 \
  --phase2-report reports/locards_subset_1_audit.json \
  --output-dir data/processed/locards_subset_1 \
  --manifest reports/locards_subset_1_selection_manifest.json \
  --chunk-size 100000 \
  --development-percent 30 \
  --split-seed 1103
```

## Outputs

- `trusted_good_ge3.csv.gz`: trusted-aircraft observations received by at least three distinct `good` sensors.
- `locards_subset_1_selection_manifest.json`: source identity, rules, counts, split assignments, output checksum, and unclassified timestamp statistics.

Rows with at least four good receivers are marked by `eligible_ge4=true` in the same compressed CSV file. Development/test assignment is deterministic and aircraft-disjoint. The raw receiver timestamp and signal fields are retained without assigning undocumented units.
