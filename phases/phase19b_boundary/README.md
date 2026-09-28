# SAM Phase 19B System Boundary Comparison

Phase 19B consolidates validated measurements from Phase 14, Phase 17 v2,
and Phase 19A. It does not rerun cryptography or LocaRDS processing. Its purpose
is to compare authentication baselines with the wider SAM cached path while
keeping unlike timing boundaries explicit.

## Run

From the `sam_phase1` project directory:

```bash
python ~/Downloads/sam_phase19b_system_boundary/scripts/run_phase19b.py \
  --phase14 reports/sam_phase14_integrated_pipeline.json \
  --phase17 reports/sam_phase17_integrated_trust_refresh_v2.json \
  --phase19a reports/sam_phase19a_authentication_baselines.json \
  --report reports/sam_phase19b_system_boundary.json \
  --seed 1103 \
  --bootstrap-replicates 10000
```

Validate:

```bash
python ~/Downloads/sam_phase19b_system_boundary/scripts/validate_report.py \
  reports/sam_phase19b_system_boundary.json
```

The report distinguishes measured quantities from derived amortized costs.
The 50-ms and 250-ms trust-refresh values are not per-message network delays:
they are four controlled refresh delays distributed over the 82,986-message
one-hour replay.

