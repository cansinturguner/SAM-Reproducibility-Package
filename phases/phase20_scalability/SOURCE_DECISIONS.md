# Source and claim decisions

- The worker is the frozen Phase 14 integrated pipeline implementation.
- Every worker independently performs LocaRDS input replay, direct-TDoA physical
  processing, deterministic HMAC verification, cached trust, and fusion.
- Native numerical libraries are restricted to one thread per worker so the
  requested process concurrency remains interpretable.
- Aggregate throughput is total eligible observations divided by batch wall time.
- Speedup is aggregate throughput divided by the single-worker median throughput.
- Parallel efficiency is speedup divided by worker count.
- Summed worker peak RSS is a conservative process-level memory aggregate, not a
  direct measurement of whole-system physical memory pressure.
- No aircraft-count, RF-channel, operational-network, or certified-hardware claim
  is made.

