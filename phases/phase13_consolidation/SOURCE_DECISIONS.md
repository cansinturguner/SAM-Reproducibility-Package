# Source and claim decisions

- Phase 5D, Phase 6 and Phase 7 are the real-data physical/cross-sensor branch
  based on LocaRDS subset 1.
- Phase 8–10 and the Phase 12 TESLA ablation are synthetic protocol workloads
  and deterministic protocol/state tests.
- Phase 11 evaluates evidence-fusion rules over branch summaries; it is not a
  per-message multimodal experiment.
- Phase 12 replaces the earlier unsuitable A4/A5 labels. A4 is now receiver and
  geometry gating. A5 is now removal of TESLA key-chain recovery. Raw-I/Q
  overlap recovery remains future work.
- Compute latency and TESLA disclosure delay are reported separately.
- Communication values are logical payload/authenticator sizes. RF framing,
  FEC, repetition and scheduling overhead are excluded.
- No attack/anomaly dataset, classifier, precision, recall, F1, false-positive
  rate or false-negative rate is claimed.
- The implementation is a Python prototype on the recorded Mac platform, not
  certified airborne avionics.

