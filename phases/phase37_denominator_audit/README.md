# Phase 37 — Denominator, artifact, and sensitivity audit

Phase 37 performs three linked reanalyses with the frozen physical model:

1. reports physical-decision yield both conditionally among originally eligible
   rows and over the complete frozen test partition;
2. decomposes benign-reference conflicts by receiver 134 involvement and
   residuals near nonzero integer-second offsets;
3. reports position-bias conflict fractions, benign-baseline-adjusted gains, and
   aircraft-cluster bootstrap intervals.

The integer-second proximity audit uses a declared 10-microsecond tolerance and
does not correct, wrap, or delete any timestamp.

```bash
python phases/phase37_denominator_audit/scripts/run_phase37.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --subset1-sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --subset2-observations data/raw/locards/subset_2/set_2.csv \
  --subset2-sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --subset2-aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model phases/phase27_threshold_aware_integration/configs/phase25a_physical_decision_model.json \
  --report reports/sam_phase37_denominator_audit.json
```

