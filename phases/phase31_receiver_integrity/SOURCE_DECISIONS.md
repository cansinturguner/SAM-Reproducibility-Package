# Source decisions

- Dataset: LocaRDS, DOI 10.5281/zenodo.4739276.
- Seed and aircraft split: inherited from the frozen Phase 25A model (seed 1103).
- Receiver clock calibration and geometry: unchanged frozen bias-only model, at least four modeled receivers, rank three.
- Guard score: maximum receiver-wise median absolute incident pair residual.
- Guard threshold: development-validation q99 using NumPy `higher`; no subset-1 test or subset-2 tuning.
- Controlled corruption: each available receiver shifted once in both signs for every configured magnitude.
- The guard reports inconsistency; it does not attribute malicious intent.
