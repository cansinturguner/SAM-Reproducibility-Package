# SAM Phase 5B - Receiver Clock Calibration

Phase 5B estimates receiver clock bias and optional linear drift from trusted
development aircraft. It then evaluates the fitted calibration on different
development aircraft.

## Leakage controls

- Only rows whose Phase 3 split is `development` are read into the model.
- Development aircraft are deterministically split 70/30 into calibration and
  validation groups.
- Aircraft identifiers cannot overlap between those groups.
- The Phase 3 test aircraft are not fitted or evaluated.

## Model

For receiver pair `i,j`, the raw residual in nanoseconds is modeled as:

```text
observed_TDoA - geometry_predicted_TDoA
  = (bias_i - bias_j) + (drift_i - drift_j) * time_hours + noise
```

Two models are fitted:

1. sensor bias only;
2. sensor bias plus linear drift.

Huber iteratively reweighted least squares limits the influence of rare extreme
timestamp errors. The drift model is selected only if it improves the
validation median absolute residual by at least both 5% and 5 ns, without
worsening the validation 95th percentile. Otherwise the simpler bias-only
model is retained.

## Requirements

```bash
source .venv/bin/activate
python -c "import numpy; print(numpy.__version__)"
```

## Run

```bash
python ~/Downloads/sam_phase5b_clock_calibration/scripts/calibrate_receiver_clocks.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --report reports/locards_subset_1_clock_calibration.json \
  --calibration-output data/processed/locards_subset_1/receiver_clock_calibration.json \
  --seed 1103 \
  --calibration-percent 70
```

If necessary, use the nested sensor-table path:

```text
data/raw/locards/subset_1/subset_1/set_1_sensors.csv
```

Display the report:

```bash
python -m json.tool reports/locards_subset_1_clock_calibration.json
```

Send the `split`, `network`, `bias_only`, `bias_and_drift`, and
`recommendation` sections for review.

No attack/anomaly labels or synthetic attacks are created.
