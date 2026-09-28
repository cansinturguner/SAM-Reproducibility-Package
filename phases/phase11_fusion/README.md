# SAM Phase 11 — Evidence Fusion and Partial A0–A7 Evaluation

This phase reads the frozen Phase 5D, 8, 9, and 10 JSON reports and validates
SAM's deterministic evidence-composition rules. It does not modify prior
reports.

Run from the existing project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
```

Run Phase 11:

```bash
python ~/Downloads/sam_phase11_evidence_fusion/scripts/run_fusion_experiment.py \
  --phase5d reports/locards_subset_1_frozen_test.json \
  --phase8 reports/sam_phase8_crypto.json \
  --phase9 reports/sam_phase9_tesla.json \
  --phase10 reports/sam_phase10_identity_trust.json \
  --report reports/sam_phase11_evidence_fusion.json \
  --iterations 100000 \
  --repetitions 5
```

Validate:

```bash
python ~/Downloads/sam_phase11_evidence_fusion/scripts/validate_report.py \
  reports/sam_phase11_evidence_fusion.json
```

Expected final line:

```text
SAM Phase 11 report validation passed.
```

Important: Phase 5D uses real LocaRDS observations, while Phases 8–10 use
synthetic cryptographic workloads and controlled trust states. Phase 11 tests
decision composition across those evidence summaries; it does not claim that
the same real ADS-B packets carried both evidence types.

A4 (channel-quality assessment) and A5 (overlap recovery) remain
`NOT_EVALUATED` because those components have not yet been implemented.

