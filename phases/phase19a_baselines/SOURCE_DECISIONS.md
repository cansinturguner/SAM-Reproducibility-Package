# Source decisions and comparison boundary

All methods receive the same deterministic 10,000-message workload. Keys,
tags, and signatures are generated before the timed verification loop.

The TESLA-style baseline implements the same one-interval post-disclosure HMAC
verification primitive used in the SAM prototype. It is not claimed to be a
complete reproduction of CABBA or another published system. The SAM row adds a
valid cached-trust state and deterministic fusion decision but excludes direct
TDoA computation. Phase 19B will compare complete pipelines using real LocaRDS
observations.

Communication values are logical authenticator and key-object sizes. They are
not RF framing, FEC, BER, or 1090-MHz channel occupancy. Legacy handling makes
no authentication claim, so accepting a modified message is reported as an
absence of assurance rather than a failed detector.

