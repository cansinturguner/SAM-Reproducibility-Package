# Phase 14 source and claim decisions

- The physical input is the frozen, aircraft-disjoint LocaRDS test partition.
- LocaRDS contains no transmitted SAM authenticator. Each selected observation
  is therefore bound to a deterministic synthetic 14-byte message surrogate.
- The surrogate is used only to exercise the integrated cryptographic and
  fusion software path. It is not described as an original ADS-B RF payload.
- HMAC verification represents post-disclosure TESLA message verification.
  The disclosure-schedule delay remains the separately measured Phase 9 result.
- A compact ECDSA P-256 trust record is verified once per fresh worker process
  and then cached. This models the local fast path, not a network or ledger.
- No attack/anomaly labels, classifier, precision, recall, F1, false-positive
  rate, or false-negative rate are produced.
- The full-A1 decision requires cryptographic, trust, and physical evidence.
  Unsupported receiver geometry yields INSUFFICIENT_EVIDENCE.

