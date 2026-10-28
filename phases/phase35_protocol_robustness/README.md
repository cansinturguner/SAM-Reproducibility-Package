# Phase 35 — TESLA timing, burst-loss, wrap, and downgrade robustness

Phase 35 exercises protocol conditions not covered by the independent-loss
experiment:

- Gilbert-Elliott burst loss with key-chain recovery;
- controlled packet delay and receiver clock-uncertainty bounds;
- the 8-bit sequence field at its per-interval boundary and across interval
  reset;
- secure-capability pinning under legacy-path routing and downgrade attempts.

All workloads are deterministic software experiments. They do not reproduce an
RF propagation process or estimate operational event prevalence.

```bash
python phases/phase35_protocol_robustness/scripts/run_phase35.py \
  --report reports/sam_phase35_protocol_robustness.json
python phases/phase35_protocol_robustness/scripts/validate_report.py \
  reports/sam_phase35_protocol_robustness.json
```

