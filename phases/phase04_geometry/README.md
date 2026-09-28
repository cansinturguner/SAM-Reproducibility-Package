# SAM Phase 4 — Receiver Geometry Profiling

This phase profiles receiver geometry using only the **development** partition
created in Phase 3. It does not inspect the test partition when producing
threshold-selection statistics, and it does not create attack or anomaly
labels.

## Input

`data/processed/locards_subset_1/trusted_good_ge3.csv.gz`

The input SHA-256 is verified by default against the Phase 3 value:

`1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5`

## Run

```bash
source .venv/bin/activate
python ~/Downloads/sam_phase4_geometry/scripts/profile_receiver_geometry.py \
  --input data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --output reports/locards_subset_1_geometry_development.json
```

Then display the report:

```bash
python -m json.tool reports/locards_subset_1_geometry_development.json
```

Send the resulting `counts`, `distributions`, and `candidate_retention`
sections for review. A geometry rule will be selected from development data and
frozen before it is evaluated on the test partition.

## What this phase does not do

- It does not estimate aircraft positions.
- It does not claim that raw timestamps or signal values have undocumented units.
- It does not choose a final geometry threshold.
- It does not inspect test-distribution quantiles.
- It does not create attacks, anomalies, or detection labels.
