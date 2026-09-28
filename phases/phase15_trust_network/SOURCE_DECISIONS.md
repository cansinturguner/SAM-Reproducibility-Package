# Source and claim decisions

- This experiment uses a real TCP loopback client/server and adds controlled
  application-level delay to emulate RTT values.
- It does not measure an operational WAN, TLS, a permissioned blockchain,
  consensus, ledger writes, or certified airborne hardware.
- The server returns one compact ECDSA P-256 CA-signed aircraft-key record.
  Clients verify the signature after every online response.
- Connections are persistent within each concurrent worker. Reported wire
  sizes describe the JSON-line prototype, not an aviation standard format.
- Offline states are deterministic policy tests: valid cache is VERIFIED;
  cold/expired cache is INSUFFICIENT_EVIDENCE; revoked online state is
  CONFLICTING.
- No attack/anomaly labels or detection metrics are produced.

