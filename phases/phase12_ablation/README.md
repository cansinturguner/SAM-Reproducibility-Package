# SAM Phase 12 — Gating and TESLA-Recovery Ablation

This phase completes the revised A4 and A5 evaluations without adding anomaly
detection:

- **A4:** receiver-availability and geometry gating, using the frozen real
  LocaRDS Phase 5D counts;
- **A5:** direct B1 disclosure versus TESLA key-chain recovery, using the same
  deterministic loss realizations as Phase 9.

Run from the existing SAM project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
```

Run:

```bash
python ~/Downloads/sam_phase12_gating_tesla_ablation/scripts/run_gating_tesla_ablation.py \
  --phase5d reports/locards_subset_1_frozen_test.json \
  --phase9 reports/sam_phase9_tesla.json \
  --report reports/sam_phase12_gating_tesla_ablation.json
```

Validate:

```bash
python ~/Downloads/sam_phase12_gating_tesla_ablation/scripts/validate_report.py \
  reports/sam_phase12_gating_tesla_ablation.json
```

Expected final line:

```text
SAM Phase 12 report validation passed.
```

No raw-I/Q overlap recovery, attack/anomaly classifier, or physical result for
unsupported receiver geometries is introduced.

