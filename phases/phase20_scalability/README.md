# SAM Phase 20 Concurrent Scalability

This phase measures the throughput and resource scaling of the frozen integrated
SAM replay under 1, 2, and 4 concurrent single-threaded worker processes. Each
worker processes the same frozen LocaRDS test workload independently.

The experiment is a controlled Mac prototype stress test. It is not an aircraft-
count simulation, an operational receiver deployment, or certified-avionics
performance.

## Run

From the `sam_phase1` project directory with the frozen virtual environment active:

```bash
python ~/Downloads/sam_phase20_concurrent_scalability/scripts/run_phase20.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase20_concurrent_scalability.json \
  --seed 1103 \
  --concurrency 1 2 4 \
  --warmups 1 \
  --repetitions 5
```

Validate:

```bash
python ~/Downloads/sam_phase20_concurrent_scalability/scripts/validate_report.py \
  reports/sam_phase20_concurrent_scalability.json
```

