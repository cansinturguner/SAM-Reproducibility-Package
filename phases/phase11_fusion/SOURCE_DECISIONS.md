# Phase 11 scope record

The A0–A7 labels are preserved from the manuscript:

- A0 legacy baseline;
- A1 full SAM;
- A2 no cryptographic branch;
- A3 no physical branch;
- A4 no channel-quality assessment;
- A5 no overlap recovery;
- A6 trust service unavailable;
- A7 single-source decision.

The fusion policy implemented here is deterministic:

1. Any enabled evidence family reporting a contradiction produces
   `CONFLICTING`.
2. `VERIFIED` requires valid cryptographic/message evidence, a valid trust
   state, and physical corroboration.
3. Missing required evidence produces `INSUFFICIENT_EVIDENCE`.
4. Legacy-only operation is recorded separately as `LEGACY_UNASSURED`.
5. A7 intentionally relaxes the policy and can verify with one evidence family;
   this is evaluated as a policy change, not claimed as a security improvement.

This is a rule/correctness and computation-cost experiment. It does not create
attack labels, perform anomaly detection, or report precision/recall/F1.

