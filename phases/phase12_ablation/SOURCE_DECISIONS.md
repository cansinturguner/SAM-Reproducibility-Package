# Phase 12 scope record

## A4 — Receiver/geometry gating

Phase 5D defines the denominator as test rows originally eligible with at
least four good receivers, and the numerator as rows satisfying the frozen
modeled-receiver and rank rule. Phase 12 reports how many rows remain supported
and how many would be admitted without physical evidence if this gate were
removed. It does not label the excluded rows as malicious or anomalous.

## A5 — TESLA key-chain recovery

CABBA/TESLA permits a later disclosed key to authenticate earlier keys through
the one-way chain. Phase 12 compares this with a controlled variant in which a
message is authenticated only when its own B1 disclosure is received. Both
variants use identical message and B1 loss draws, enabling paired comparison.

The direct-only variant retains unresolved messages until the end of the
ten-minute simulation because no arbitrary eviction timeout is introduced.
Therefore its buffer result is an upper-bound behavior for this explicit
no-timeout policy, not a certified avionics buffer requirement.

The manuscript's earlier overlap-recovery A5 remains future SDR work because
LocaRDS does not provide raw I/Q samples.

