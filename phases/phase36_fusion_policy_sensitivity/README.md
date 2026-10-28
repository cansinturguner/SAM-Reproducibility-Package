# Phase 36 — Fusion-policy sensitivity

Phase 36 compares the implemented conflict-dominant SAM policy with a bounded
alternative.  The alternative retains immediate revocation dominance but
requires two non-revocation evidence conflicts before returning CONFLICTING; a
single cryptographic or physical conflict is held as INSUFFICIENT_EVIDENCE.

The alternative is not proposed as a replacement.  It exposes the policy
trade-off: fewer single-branch conflicts at the cost of weaker response to a
compromised or faulty single evidence source.

The script evaluates all 48 finite evidence combinations and, when supplied
with a Phase 34 report, applies both policies to the same controlled joint
replay distribution.

```bash
python phases/phase36_fusion_policy_sensitivity/scripts/run_phase36.py \
  --phase34-report reports/sam_phase34_joint_branch_replay.json \
  --report reports/sam_phase36_fusion_policy_sensitivity.json
python phases/phase36_fusion_policy_sensitivity/scripts/validate_report.py \
  reports/sam_phase36_fusion_policy_sensitivity.json
```

