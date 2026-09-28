# SAM Phase 9 — TESLA Delayed Authentication

This phase evaluates a CABBA-aligned TESLA key chain, delayed key disclosure,
message buffering, independent packet loss, authentication availability,
authentication delay, processing time, and peak memory. It does not modify
Phase 1–8 results.

Run from the existing SAM project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
python --version
```

Python must be 3.11 or 3.12. No additional package is required.

Run Phase 9:

```bash
python ~/Downloads/sam_phase9_tesla_delayed_auth/scripts/run_tesla_experiment.py \
  --report reports/sam_phase9_tesla.json \
  --seed 1103 \
  --duration-seconds 600 \
  --interval-seconds 1 \
  --message-rate 6.2 \
  --replicates 200 \
  --loss-probabilities 0,0.1,0.2,0.3,0.4,0.5
```

Validate the report:

```bash
python ~/Downloads/sam_phase9_tesla_delayed_auth/scripts/validate_report.py \
  reports/sam_phase9_tesla.json
```

Expected final line:

```text
SAM Phase 9 report validation passed.
```

The loss model is a controlled availability stress test, not an attack or
anomaly detector. The experiment uses deterministic synthetic 14-byte message
workloads and does not implement RF modulation, FEC, certificates, B2/C packet
scheduling, or certified airborne hardware.

