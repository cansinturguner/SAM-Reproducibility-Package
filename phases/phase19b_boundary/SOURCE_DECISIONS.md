# Phase 19B source and claim decisions

- Authentication-only values come directly from the validated Phase 19A report.
- The SAM cached-path value comes directly from the validated Phase 14 integrated
  replay and therefore includes the real LocaRDS physical/TDoA path, deterministic
  HMAC, cached trust state, and fusion.
- Trust refresh counts and controlled delays come from the validated Phase 17 v2
  report.
- Per-message trust-delay increments are deterministic derivations:
  `refresh_successes * added_delay / eligible_rows`.
- Bootstrap intervals resample the recorded repetition values. They quantify
  prototype run-to-run variation only.
- No CABBA reproduction, RF-channel experiment, certified-hardware measurement,
  ledger-consensus experiment, or operational-WAN measurement is claimed.
- Methods do not provide identical functions. Functional coverage is reported
  beside timing to prevent a smaller authentication-only number from being
  interpreted as a complete-system result.

