# SAM Phase 22 External Validation on LocaRDS Subset 2

This phase applies the frozen subset-1 receiver clock model and assurance policy
to LocaRDS subset 2 without recalibration or threshold selection.

## Prepare subset 2

From the `sam_phase1` project directory:

```bash
mkdir -p data/raw/locards/subset_2
unzip -j ~/Downloads/subset_2.zip -d data/raw/locards/subset_2
```

The expected files are `set_2.csv`, `set_2_sensors.csv`,
`set_2_aircraft.csv`, and `LICENSE.txt`.

## Run

```bash
python ~/Downloads/sam_phase22_external_validation/scripts/run_phase22.py \
  --observations data/raw/locards/subset_2/set_2.csv \
  --sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --primary reports/locards_subset_1_frozen_test.json \
  --report reports/sam_phase22_external_validation.json \
  --seed 1103 \
  --bootstrap-replicates 2000
```

Validate:

```bash
python ~/Downloads/sam_phase22_external_validation/scripts/validate_report.py \
  reports/sam_phase22_external_validation.json
```

No subset-2 result is used to change the frozen clock model, receiver rule,
cryptographic configuration, trust state, or fusion policy.

## Provenance and platform boundary

Phase 22 reads the released subset-2 observation, sensor, and aircraft CSV
files together with the frozen subset-1 receiver calibration and Phase 5D
reference report. It does not read `trusted_good_ge3.csv.gz`, so the selected
subset-1 gzip-file hash used by other phases is not part of this phase's input
boundary. The reported Phase 22 results were produced on Darwin 25.5.0; they
must not be relabeled with the Darwin 27.0.0 environment used later for Phase
21 and the matched Phase 14 platform-control repeat.
