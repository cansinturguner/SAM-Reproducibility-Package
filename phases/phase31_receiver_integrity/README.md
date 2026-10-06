# Phase 31 — Reference-independent receiver integrity

This phase freezes a receiver-integrity guard on LocaRDS subset-1 development-validation aircraft. For every available observation it computes each receiver's median absolute calibrated pair residual and uses the maximum receiver score as the observation score. No single receiver is designated as the decision reference.

The threshold is the higher empirical q99 selected only on development-validation aircraft. The frozen guard is then evaluated on the aircraft-disjoint subset-1 test, transferred unchanged to subset 2, and stressed with signed single-receiver timestamp shifts.

The output event files are inputs to Phase 32. Trusted-aircraft metadata is treated as a benign reference filter, not attack-free ground truth. Subset 2 shares the published LocaRDS sensor infrastructure with subset 1.
