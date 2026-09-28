# SAM Phase 6 — Controlled receiver-observation loss

This phase measures how the already frozen physical/cross-sensor verification rule behaves when receiver observations are removed. It does **not** create attacks, anomaly labels, or detection claims.

## Run from the SAM Phase 1 project directory

Keep the Python 3.12 virtual environment active, unzip this package, and run:

```bash
python ~/Downloads/sam_phase6_receiver_loss/scripts/evaluate_receiver_loss.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_receiver_loss.json \
  --loss-probabilities 0,0.1,0.2,0.3,0.4,0.5 \
  --replicates 30 \
  --seed 1103
```

The script checks the frozen selected-data SHA-256 by default. Do not use `--skip-hash-check` for the real experiment.

## What to send back

After completion, run:

```bash
python - <<'PY'
import json
r = json.load(open("reports/locards_subset_1_receiver_loss.json"))
print(json.dumps({
    "counts": r["counts"],
    "loss_model": r["loss_model"],
    "scenarios": [{
        "loss": x["independent_receiver_loss_probability"],
        "availability": x["availability_vs_original_ge4"],
        "q50_ns": x["absolute_q50_ns"],
        "q95_ns": x["absolute_q95_ns"],
        "trimmed_rmse_ns": x["trimmed_99pct_rmse_ns"]
    } for x in r["scenarios"]]
}, indent=2))
PY
```

Send the printed JSON. Keep the full report unchanged for the paper artifact.
