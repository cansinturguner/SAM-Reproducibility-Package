# Source and claim decisions

- The frozen Phase 14 helper functions and eligibility rules are reused.
- All 82,986 test observations originally eligible for four-receiver analysis
  are processed in every measured repetition.
- File decompression and CSV input loading occur outside the timed kernel.
- Cached trust is represented by the already verified trust state used by the
  Phase 14 fast path; CA and B2 verification are not repeated per message.
- Component timers are nested boundaries: crypto, physical, fusion, and total.
- Timer calls add instrumentation overhead. The total measured interval is the
  authoritative per-message kernel latency; component values diagnose relative
  cost rather than forming a separately benchmarked sum.
- No RF, network transport, TESLA disclosure wait, online trust refresh, or
  certified-hardware latency is claimed.

