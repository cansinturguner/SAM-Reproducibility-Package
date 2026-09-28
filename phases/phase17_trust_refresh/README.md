# SAM Phase 17 Integrated Trust Refresh Pipeline

This phase co-executes the frozen physical-verification logic, deterministic
message-bound HMAC verification, signed trust-record refresh over TCP, the
900-second cache policy, and SAM evidence fusion over the real LocaRDS test
timeline.

Run from `sam_phase1` with the existing virtual environment active:

```bash
python ~/Downloads/sam_phase17_v2_integrated_trust_refresh/scripts/run_phase17.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase17_integrated_trust_refresh.json \
  --seed 1103 \
  --repetitions 5 \
  --retry-interval-seconds 60
```

Then validate:

```bash
python ~/Downloads/sam_phase17_v2_integrated_trust_refresh/scripts/validate_report.py \
  reports/sam_phase17_integrated_trust_refresh.json
```

The experiment can take several minutes because each scenario replays the
complete aircraft-disjoint test partition. Send the printed JSON summary after
the validation passes.

This corrected v2 package ends the measured wall-clock interval before server
shutdown and applies a 60-second retry backoff after an unavailable trust
service response. It therefore avoids cleanup-time contamination and a
per-message retry storm.
