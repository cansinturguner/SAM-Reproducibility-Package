# Phase 34 — Joint evidence-branch interaction replay

The Phase 27 reference replay intentionally used valid synthetic cryptographic
and trust evidence for every eligible real LocaRDS observation.  Consequently,
its full-policy result equaled the physical-only result.  Phase 34 removes that
experimental degeneracy.

For every eligible test observation, the script recomputes the frozen physical
state from the real LocaRDS receiver timestamps and then applies deterministic,
controlled cryptographic and trust perturbations.  It reports the full SAM
decision beside physical-only and cryptographic-only policy variants and counts
observation-level decision transitions.

The perturbations are controlled software states, not operational RF attacks or
prevalence estimates.  Their rates are scenario parameters selected to exercise
the interaction semantics.

Run on the full local data:

```bash
python phases/phase34_joint_branch_replay/scripts/run_phase34.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --decision-model phases/phase27_threshold_aware_integration/configs/phase25a_physical_decision_model.json \
  --report reports/sam_phase34_joint_branch_replay.json

python phases/phase34_joint_branch_replay/scripts/validate_report.py \
  reports/sam_phase34_joint_branch_replay.json
```

Run the bundled fixture self-test:

```bash
python phases/phase34_joint_branch_replay/scripts/self_test.py
```

