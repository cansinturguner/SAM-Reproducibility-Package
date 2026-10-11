# Phase 27 Threshold-Aware Integrated and Outage Replay

This phase closes the boundary left by the earlier integrated and trust-outage
experiments. The physical branch now makes the frozen Phase 25A decision inside
the co-executed SAM path:

- `PHYSICALLY_CONSISTENT` when the per-observation score is at or below
  306.64062122826 ns;
- `PHYSICALLY_CONFLICTING` when the available score is above the threshold;
- `PHYSICAL_EVIDENCE_UNAVAILABLE` when the frozen receiver or geometry rule is
  not satisfied.

Conflict remains dominant during trust-service outage. Therefore a physical
conflict stays `CONFLICTING` even after cached trust expires. Missing trust and
otherwise consistent or unavailable physical evidence produce
`INSUFFICIENT_EVIDENCE`.

## Inputs

Run from the root of `SAM_Reproducibility_Package`. The phase expects:

```text
data/processed/locards_subset_1/trusted_good_ge3.csv.gz
data/processed/locards_subset_1/receiver_clock_calibration.json
data/raw/locards/subset_1/set_1_sensors.csv
```

The frozen Phase 25A model is included under `configs/`. Its recorded SHA-256
digests are checked before the full run.

## Run

```bash
bash scripts/run_phase27.sh
```

The script creates:

```text
reports/sam_phase27a_threshold_aware_integrated.json
reports/sam_phase27b_threshold_aware_outage.json
```

Phase 27A uses one warm-up and 30 measured fresh-process repetitions. Phase 27B
uses five repetitions of each online-delay and scheduled-outage scenario. It
retains the boundary-aligned outage at 1,800 s and adds an offset outage at
2,250 s, after the approximately 1,800-s refresh. The report counts pre-outage
and post-outage trust states separately, so pre-outage valid rows cannot be
misinterpreted as offline cache continuity.

## Interpretation boundary

The experiment uses real LocaRDS observations with a deterministic synthetic
authenticator. It evaluates software composition, physical decision semantics,
cache expiry, scheduled service loss, and the observed post-outage cache-grace
interval in the offset scenario. It does not estimate operational
attack prevalence, RF performance, production PKI behavior, or certified
airborne execution.

