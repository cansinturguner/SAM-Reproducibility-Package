# SAM Phase 21 Component Latency Profile

Phase 21 instruments the frozen integrated SAM processing kernel at message
granularity. It reports p50, p95, and p99 latency for cryptographic message
processing, physical/direct-TDoA processing, fusion, and their measured total.

Input decompression and CSV loading are completed before the timed repetitions.
The results therefore complement, rather than replace, the Phase 14 end-to-end
replay measurement.

## Run

From the `SAM_Reproducibility_Package` root with the frozen virtual environment active:

```bash
python phases/phase21_component_latency/scripts/run_phase21.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase21_component_latency.json \
  --seed 1103 \
  --warmup-rows 1000 \
  --repetitions 5
```

Validate:

```bash
python phases/phase21_component_latency/scripts/validate_report.py \
  reports/sam_phase21_component_latency.json
```

If Phase 3 was regenerated, provide the SHA-256 recorded in its manifest with
`--expected-selected-sha256`. This preserves input verification when gzip
container metadata causes the regenerated archive hash to differ from the
original recorded archive.
