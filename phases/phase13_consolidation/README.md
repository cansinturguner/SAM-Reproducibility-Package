# SAM Phase 13 — Final A0–A7 Consolidation

This phase consolidates the frozen Phase 5D–12 reports into one traceable
experimental summary. It performs no new attack/anomaly experiment and does
not join the LocaRDS and cryptographic observations at message level.

Run from the existing SAM project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
```

Generate the report:

```bash
python ~/Downloads/sam_phase13_final_consolidation/scripts/consolidate_results.py \
  --phase5d reports/locards_subset_1_frozen_test.json \
  --phase6 reports/locards_subset_1_receiver_loss.json \
  --phase7 reports/locards_subset_1_phase7_benchmark.json \
  --phase8 reports/sam_phase8_crypto.json \
  --phase9 reports/sam_phase9_tesla.json \
  --phase10 reports/sam_phase10_identity_trust.json \
  --phase11 reports/sam_phase11_evidence_fusion.json \
  --phase12 reports/sam_phase12_gating_tesla_ablation.json \
  --report reports/sam_phase13_final_consolidation.json
```

Validate it:

```bash
python ~/Downloads/sam_phase13_final_consolidation/scripts/validate_report.py \
  reports/sam_phase13_final_consolidation.json
```

Expected final line:

```text
SAM Phase 13 report validation passed.
```

Send the printed report summary back. Keep all source reports unchanged.

