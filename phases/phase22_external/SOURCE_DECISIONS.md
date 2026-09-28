# Source and claim decisions

- Source: LocaRDS release, Zenodo DOI 10.5281/zenodo.4739276.
- External data: `subset_2.zip`, official MD5
  `9e40dcb90cad589e9d7f3ffc2a1af753`.
- The subset-2 sensor table is byte-identical to the subset-1 sensor table used
  in the primary experiment (SHA-256
  `998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b`).
- The subset-1 bias-only receiver calibration is loaded unchanged.
- Subset 2 is not divided into development and test partitions. All eligible
  trusted-aircraft observations form the external-validation population.
- The denominator is trusted-aircraft rows with at least four receivers marked
  good in the released metadata. Physical support additionally requires four
  receivers represented by the frozen clock model and rank-three geometry.
- The HMAC input remains a deterministic synthetic surrogate bound to each real
  observation; subset 2 contains no transmitted SAM authenticator.
- Aircraft-cluster bootstrap intervals quantify external-set sampling variation.
- No attack labels, anomaly classifier, RF waveform, or certified hardware are
  introduced.

