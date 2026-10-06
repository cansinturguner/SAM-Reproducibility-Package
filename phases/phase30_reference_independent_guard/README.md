# Phase 30 — Reference-Independent Single-Receiver Guard

Phase 28 showed that the frozen reference-based median score is sensitive when
the decision reference is corrupted but can miss one corrupted nonreference
receiver. Phase 30 evaluates a pre-specified reference-independent guard.

For each receiver, the candidate takes the median absolute pair residual against
all other receivers. The observation score is the maximum receiver-wise median.
Its threshold is the higher empirical 99th percentile selected only from the
development-validation aircraft. The frozen subset-1 test is not used to select
the threshold.

The report compares the existing score, the candidate guard, and a conservative
OR-combination. Controlled shifts of both signs are applied to exactly one
receiver at 100–10,000 ns. Results are separated for the current decision
reference and nonreference receivers. This is a candidate evaluation, not an
automatic change to the frozen SAM policy.

Run from the package root:

```bash
bash scripts/run_phase30.sh
```

Output: `reports/sam_phase30_reference_independent_receiver_guard.json`
