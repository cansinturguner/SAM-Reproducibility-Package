# Phase 10 source and scope decisions

The CABBA paper defines:

- Type B2 as a TESLA interval key plus the aircraft signature of that key;
- Type C as the aircraft public key plus a CA signature of that public key;
- ECDSA with 128-bit security strength, a 256-bit public-key value, and a
  512-bit signature;
- authentication only after the signed interval key and trusted aircraft key
  have both been validated.

Phase 10 implements those trust relationships with ECDSA P-256/SHA-256. The
software uses standard compressed SEC1 public-key serialization (33 bytes) and
fixed-width `r || s` signatures (64 bytes). Therefore, its compact CA record is
97 bytes and its signed B2 content is 80 bytes before any RF framing or FEC.
These software serialization sizes are not presented as DO-260C/ED-102B
packet formats.

SAM-specific experimental rules:

- a signed registry record acts as the permissioned trust-service object;
- a valid cached record may support offline verification until its TTL expires;
- missing or expired trust evidence yields `INSUFFICIENT_EVIDENCE`;
- a cryptographically valid but revoked identity yields `CONFLICTING`;
- only valid identity, B2 signature, and message HMAC evidence yields
  `VERIFIED`.

No blockchain consensus or ledger write is placed in the real-time message
path. A permissioned ledger could distribute registry snapshots later, but it
is not needed to test these deterministic assurance rules.

