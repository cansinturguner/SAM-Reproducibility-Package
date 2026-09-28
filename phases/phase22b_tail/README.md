# SAM Phase 22B Subset 2 Residual Tail Audit

This audit investigates the large subset-2 residual tail without modifying,
wrapping, trimming, or correcting any observation. It reports threshold
fractions, receiver-pair concentrations, and residuals close to integer-second
offsets.

Run from the `sam_phase1` project directory:

```bash
python ~/Downloads/sam_phase22b_tail_audit/scripts/run_phase22b.py \
  --observations data/raw/locards/subset_2/set_2.csv \
  --sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase22b_tail_audit.json
```

Validate:

```bash
python ~/Downloads/sam_phase22b_tail_audit/scripts/validate_report.py \
  reports/sam_phase22b_tail_audit.json
```

