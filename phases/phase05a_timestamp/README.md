# SAM Phase 5A - LocaRDS Timestamp Consistency Audit

This phase tests candidate interpretations of the raw LocaRDS receiver
timestamp field against propagation-time differences predicted from the known
aircraft and receiver coordinates.

It does **not**:

- assume a timestamp unit in advance;
- estimate a new aircraft position;
- select a security threshold;
- inspect attack/anomaly labels;
- use test rows.

## Inputs

- Phase 3 selected file:
  `data/processed/locards_subset_1/trusted_good_ge3.csv.gz`
- LocaRDS sensor table:
  `data/raw/locards/subset_1/set_1_sensors.csv`

The script checks the known Phase 3 SHA-256 by default.

## Run

```bash
source .venv/bin/activate

python ~/Downloads/sam_phase5a_timestamp_audit/scripts/audit_timestamp_semantics.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --output reports/locards_subset_1_timestamp_audit.json \
  --sample-permille 200 \
  --seed 1103
```

If your extraction created an extra `subset_1` directory, point `--sensors`
to:

```text
data/raw/locards/subset_1/subset_1/set_1_sensors.csv
```

Display the report:

```bash
python -m json.tool reports/locards_subset_1_timestamp_audit.json
```

Send the `counts`, `raw_timestamp_profile`, `candidate_interpretations`,
and `pair_residual_profile_for_best_candidate` sections for review.

## Interpretation

For each sampled development row with at least four good receivers, the script
computes the expected TDoA from the published aircraft coordinates and sensor
coordinates. It then compares this value with receiver timestamp differences
under multiple candidate unit conversions, both with and without a 60-second
circular wrap.

The candidate with the smallest residual is reported as an empirical
candidate, not as a documentation claim. A Direct-TDoA experiment will not
start until the result is technically plausible and cross-checked.
