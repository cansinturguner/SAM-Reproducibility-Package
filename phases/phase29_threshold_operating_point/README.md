# SAM Phase 29 — Threshold Operating-Point Sensitivity

Phase 29 evaluates whether the frozen 306.640621 ns physical-consistency
threshold represents a defensible operating point.

## Leakage control

Candidate thresholds are the higher empirical quantiles corresponding to
95%, 97.5%, 99%, 99.5%, and 99.9% benign consistency. They are computed only
from Phase 5B development-validation aircraft. The subset-1 test observations
and controlled perturbations do not select or tune a threshold.

## Reported trade-offs

For every development-defined threshold the experiment reports:

- development-validation consistency;
- held-out subset-1 benign-reference conflict fraction and aircraft-cluster
  bootstrap interval;
- controlled position-bias conflict fraction;
- the fraction of previously consistent rows changing to conflict;
- reverse transitions where a perturbation cancels an existing residual;
- the fixed-ground-spoofer result.

The 99% point must reproduce the Phase 25A threshold and benign counts. When
the Phase 25B report is supplied, all frozen-point controlled-attack counts
must also match Phase 25B. Position-bias bearings use the exact Phase 25B
SHA-256 input convention: `seed|row_id|distance_m` with distance formatted to
six decimal places and the first eight digest bytes mapped to `[0, 2*pi)`.

## Interpretation

This is sensitivity analysis, not post-hoc threshold optimization. A lower
threshold may increase controlled-perturbation sensitivity while also
increasing benign-reference conflicts. A higher threshold may reduce benign
conflicts while weakening sensitivity. No point is called optimal without an
externally justified operational loss function.

The controlled position offsets are not captured attacks, and trusted-aircraft
metadata is not guaranteed attack-free ground truth.
