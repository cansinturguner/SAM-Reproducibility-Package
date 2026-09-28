# SAM Phase 19A Authentication Baseline Comparison

Phase 19A compares authentication-related message processing on the same
deterministic 14-byte workload and the same Python/Mac platform. It is a
cryptographic microbenchmark, not a complete end-to-end comparison of the
physical SAM pipeline.

Compared methods:

- legacy unauthenticated message handling;
- pre-shared-key HMAC-SHA3-256/128;
- ECDSA P-256/SHA-256 per message;
- TESLA-style one-interval delayed HMAC verification;
- SAM post-disclosure HMAC, valid trust-cache lookup, and fusion decision.

Run from `sam_phase1` with the existing environment active:

```bash
python ~/Downloads/sam_phase19a_authentication_baselines/scripts/run_phase19a.py \
  --report reports/sam_phase19a_authentication_baselines.json \
  --seed 1103 \
  --message-count 10000 \
  --repetitions 10 \
  --message-rate 6.2
```

Validate:

```bash
python ~/Downloads/sam_phase19a_authentication_baselines/scripts/validate_report.py \
  reports/sam_phase19a_authentication_baselines.json
```

ECDSA verification dominates runtime, so the full experiment can take about a
minute. Send the printed JSON summary after validation.

