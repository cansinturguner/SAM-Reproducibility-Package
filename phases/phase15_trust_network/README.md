# SAM Phase 15 — Trust-Service Network and Cache Experiment

This phase measures the SAM trust-service path over a real localhost TCP
client/server while adding controlled RTT, concurrency, signed-record
verification, cache use, and service-unavailable states.

Run from the existing SAM project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
```

Run:

```bash
python ~/Downloads/sam_phase15_trust_network/scripts/run_trust_network.py \
  --report reports/sam_phase15_trust_network.json \
  --seed 1103 \
  --rtt-ms 0,10,50,100,250 \
  --concurrency 1,8,32 \
  --requests-per-scenario 64 \
  --repetitions 5 \
  --cache-ttl-seconds 900
```

The test can take a few minutes because the 250-ms scenarios intentionally
wait. Keep the Mac connected to power and close heavy applications.

Validate:

```bash
python ~/Downloads/sam_phase15_trust_network/scripts/validate_report.py \
  reports/sam_phase15_trust_network.json
```

Expected final line:

```text
SAM Phase 15 report validation passed.
```

Send back the JSON summary printed by the run command.

