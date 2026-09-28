# Source and scope record

- HMAC-SHA3-256 with a 128-bit transmitted tag and a 512-bit root-key setting
  follows the parameterization reported in *Authentication feature for ADS-B
  using overlaid phase modulation* (ICNS 2026,
  DOI: 10.1109/ICNS69853.2026.11570333).
- ECDSA P-256/SHA-256 is measured as the asymmetric open-verification/bootstrap
  comparator associated with CABBA; it is not attributed to the SESAR
  symmetric prototype.
- Phase Overlay feasibility and legacy readability are literature evidence,
  not Phase 8 measurements. No RF, BER, coverage, or flight test is performed.
- The authenticated-input encoding, domain-separation values, and temporary
  key derivation in the script are declared experimental definitions rather
  than unpublished standard or SESAR implementation details.
- Modified-message and stale-counter cases are protocol correctness tests, not
  anomaly detection or attack-classification experiments.

