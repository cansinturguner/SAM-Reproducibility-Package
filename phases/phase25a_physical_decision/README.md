# SAM Phase 25A — Physical Decision Validation

Phase 25A converts the previously descriptive direct-TDoA residual into an
explicit, leakage-controlled physical decision. Receiver/geometry gating and
physical consistency are different decisions:

- unsupported receiver count or geometry: `PHYSICAL_EVIDENCE_UNAVAILABLE`;
- available score at or below the frozen threshold: `PHYSICALLY_CONSISTENT`;
- available score above the frozen threshold: `PHYSICALLY_CONFLICTING`.

The observation score is the median absolute calibrated direct-TDoA
reference-pair residual. The threshold is the higher empirical quantile that
targets 99% benign consistency on development-validation aircraft only. The
subset-1 test and subset 2 are excluded from threshold selection.

## Run

From the package root, after Phases 3 and 5B have produced their artifacts:

```bash
bash phases/phase25a_physical_decision/run_phase.sh
```

The wrapper first calibrates the threshold, applies it once to the frozen
subset-1 test, applies the unchanged model to subset 2, and validates all three
JSON artifacts.

The reported benign-reference conflict fraction is not a certified false-alarm
probability. LocaRDS trusted-aircraft metadata is a provenance filter, not a
guarantee that every timestamp or report is error free.
