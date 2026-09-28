# SAM Phase 5D - Frozen Test Evaluation

This is the one-time test evaluation of the physical corroboration component.
The configuration is fixed in the script and cannot be tuned from command-line
arguments:

- timestamp unit: nanosecond;
- receiver clock model: Phase 5B `bias_only`;
- at least four receivers present in the calibration model;
- recomputed centered-ECEF receiver geometry rank equal to 3;
- no geometry-ratio threshold;
- no minimum-baseline threshold.

The script reads only rows whose Phase 3 split is `test`. It reports pairwise
calibrated TDoA residuals, row availability, receiver-count strata, and
aircraft-clustered bootstrap confidence intervals.

## Run once

```bash
source .venv/bin/activate

python ~/Downloads/sam_phase5d_frozen_test/scripts/run_frozen_test.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_frozen_test.json \
  --bootstrap-replicates 2000 \
  --bootstrap-seed 1103
```

For the nested extraction layout, use:

```text
data/raw/locards/subset_1/subset_1/set_1_sensors.csv
```

Display the main result:

```bash
python - <<'PY'
import json
r=json.load(open("reports/locards_subset_1_frozen_test.json"))
print(json.dumps({
  "frozen_configuration": r["frozen_configuration"],
  "counts": r["counts"],
  "availability": r["availability"],
  "pair_residuals": r["pair_residuals"],
  "row_residuals": r["row_residuals"],
  "aircraft_clustered_confidence_intervals": r["aircraft_clustered_confidence_intervals"],
  "by_receiver_count": r["by_receiver_count"],
}, indent=2))
PY
```

Send the complete displayed output for interpretation. Do not rerun with a
different physical-verification configuration.

No attack/anomaly labels or synthetic attacks are created.
