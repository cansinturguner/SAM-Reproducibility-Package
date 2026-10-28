# Phase 34 source decisions

1. The physical branch is recomputed with the frozen Phase 25A threshold and
   Phase 27 implementation. No threshold, receiver bias, or geometry rule is
   updated.
2. Cryptographic and trust perturbations are assigned by SHA-256 of the
   observation-bound canonical message, scenario label, evidence dimension,
   and seed. This makes assignments deterministic and independent of row order.
3. The 1% and 10% rates are controlled stress conditions, not estimates of
   operational attack or failure prevalence.
4. Conflict dominance is retained in the full SAM policy. Missing/pending/stale
   evidence yields insufficient evidence unless another branch conflicts.
5. The report stores aggregate counts only. It does not redistribute derived
   LocaRDS observation tables.

