# Source decisions and claim boundary

The physical and cryptographic observation path is the frozen Phase 14 code.
Phase 17 adds a localhost TCP trust service, ECDSA P-256/SHA-256 verification at
each refresh, a 900-second cache, controlled application delay, and a scheduled
service outage at 1,800 seconds of the LocaRDS timeline.

The authenticator remains a deterministic 14-byte surrogate bound to each real
LocaRDS observation. The trust service is a compact prototype, not TLS, X.509,
a global aviation PKI, a permissioned ledger, or an operational network.
Controlled loopback delay is not a field latency measurement.

Version 2 ends timing before server shutdown and thread cleanup. After a
failed refresh it waits 60 seconds of dataset time before retrying; the cache
policy continues to yield `INSUFFICIENT_EVIDENCE` once the last valid record
has expired.

No attack/anomaly dataset or classifier is used.
