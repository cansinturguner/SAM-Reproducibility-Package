# Audit boundaries

- Uses the same frozen subset-1 bias-only calibration and subset-2 eligibility
  rules as Phase 22.
- Does not change residuals using modulo, rollover correction, clipping, or
  outlier removal.
- `near_integer_second` is diagnostic classification only. It checks whether a
  residual is within a stated tolerance of a nonzero integer multiple of one
  second.
- Receiver-pair counts identify concentration; they do not assign fault or
  malicious intent.

