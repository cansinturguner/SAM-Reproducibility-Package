# Source decisions and claim boundary

The cryptographic configuration is frozen from Phases 8-10: HMAC-SHA3-256
truncated to 128 bits, ECDSA P-256/SHA-256, a 128-bit interval key, monotonic
sequence acceptance, a signed compact aircraft-key record, and a 900-second
cache TTL.

The fusion rule is unchanged: any explicit conflict dominates; VERIFIED
requires verified cryptographic, physical, and trust evidence; otherwise the
result is INSUFFICIENT_EVIDENCE.

The cases test protocol conformance and controlled failure behavior. They do
not estimate prevalence, detection accuracy, false-positive/false-negative
rates, or resistance to every possible adversary. Physical evidence is a
controlled branch state rather than a new LocaRDS experiment.

