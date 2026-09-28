# SAM Phase 5C - Calibrated Geometry Validation

This phase applies the frozen Phase 5B receiver clock calibration to the
aircraft held out as **validation aircraft within the Phase 3 development
partition**. The Phase 3 test aircraft remain unused.

Receiver geometry is recomputed from the receivers that are actually present
in the frozen clock-calibration model. Sixteen candidate rules are compared:

- geometry ratio: no threshold, 0.001, 0.002, 0.005;
- minimum receiver baseline: no threshold, 100 m, 1 km, 5 km.

The report contains availability and calibrated TDoA residual summaries. It
does not automatically declare a final rule.

## Run

```bash
source .venv/bin/activate

python ~/Downloads/sam_phase5c_geometry_validation/scripts/validate_geometry_rules.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_geometry_validation.json \
  --seed 1103 \
  --calibration-percent 70
```

For the nested extraction layout, use:

```text
data/raw/locards/subset_1/subset_1/set_1_sensors.csv
```

Display the compact decision table:

```bash
python - <<'PY'
import json
r=json.load(open("reports/locards_subset_1_geometry_validation.json"))
print(json.dumps({
  "scope": r["scope"],
  "counts": r["counts"],
  "geometry_profile": r["geometry_profile"],
  "rules": r["rules"],
}, indent=2))
PY
```

Send those four sections for review.

No attack/anomaly labels or synthetic attacks are created.
