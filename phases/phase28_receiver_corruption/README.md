# Phase 28 Single-Receiver and Reference-Receiver Corruption

This phase measures how the frozen 306.640621-ns physical decision responds
when one receiver timestamp is altered while the reported aircraft position,
all other receiver timestamps, receiver calibration, geometry rule, and
threshold remain unchanged.

Three targets are evaluated separately:

1. the observation-specific decision reference, defined by the frozen
   deterministic sensor-id ordering;
2. every nonreference receiver, corrupted one at a time;
3. receiver 134, the global calibration-reference sensor, whenever it occurs
   in an available observation.

Both positive and negative timestamp offsets are tested at absolute magnitudes
of 100, 250, 500, 750, 1,000, 2,000, 5,000, and 10,000 ns. Reporting both signs
prevents a favorable residual direction from being selected after inspection.

## Why the targets are separated

Changing the decision-reference timestamp shifts every reference-pair residual.
Changing one nonreference timestamp changes only one residual. Because the
physical score is a median, these cases can have materially different
sensitivity. Receiver 134 is reported separately because it anchors the frozen
clock-bias model and appears in the extreme-residual audit.

## Run

From the root of `SAM_Reproducibility_Package`:

```bash
bash scripts/run_phase28.sh
```

The output is:

```text
reports/sam_phase28_receiver_corruption.json
```

## Reported measures

- all-trial physical-conflict fraction;
- consistent-to-conflicting fraction among baseline-consistent trials;
- conflicting-to-consistent transition fraction;
- for nonreference corruption, the fraction of baseline-consistent
  observations in which any or every possible single target becomes
  conflicting;
- separate signed-offset and sign-combined absolute-magnitude summaries.

## Boundary

The offsets are controlled timestamp perturbations, not observed compromise
traces. Results characterize the frozen score's sensitivity to one altered
receiver. They do not estimate operational attack prevalence or detection
accuracy and do not cover correlated multi-receiver compromise, RF
manipulation, or receiver removal.

