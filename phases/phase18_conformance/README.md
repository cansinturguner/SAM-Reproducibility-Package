# SAM Phase 18 Integrated Protocol Conformance Tests

Phase 18 verifies that the implemented SAM decision path produces the specified
assurance state for valid, modified, replayed, missing, expired, revoked, and
conflicting protocol evidence. These are controlled protocol test vectors, not
an attack/anomaly dataset and not a classifier evaluation.

Run from the `sam_phase1` directory with the existing virtual environment:

```bash
python ~/Downloads/sam_phase18_protocol_conformance/scripts/run_phase18.py \
  --report reports/sam_phase18_protocol_conformance.json \
  --seed 1103 \
  --iterations 10000 \
  --repetitions 5
```

Validate:

```bash
python ~/Downloads/sam_phase18_protocol_conformance/scripts/validate_report.py \
  reports/sam_phase18_protocol_conformance.json
```

Expected final line:

```text
SAM Phase 18 report validation passed.
```

