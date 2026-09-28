# SAM Phase 7 — Physical-verification computational benchmark

This phase measures the actual end-to-end computational cost of the frozen physical/cross-sensor verification workflow. It creates no attack or anomaly labels.

## Run

From the `sam_phase1` directory with the Python 3.12 virtual environment active:

```bash
python ~/Downloads/sam_phase7_benchmark/scripts/benchmark_physical_verification.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_phase7_benchmark.json \
  --warmups 1 \
  --repeats 5
```

The benchmark may take several minutes because every measured repetition reads and verifies the full selected dataset in a fresh process. Keep the Mac connected to power, close heavy applications, and do not run other compute-intensive tasks during measurement.

## Return the summary

```bash
python - <<'PY'
import json
r = json.load(open("reports/locards_subset_1_phase7_benchmark.json"))
print(json.dumps({
    "platform": r["platform"],
    "counts": r["counts"],
    "validation": r["validation"],
    "summaries": r["summaries"],
    "interpretation_limits": r["interpretation_limits"]
}, indent=2))
PY
```

Send the printed JSON and retain the full report unchanged.
