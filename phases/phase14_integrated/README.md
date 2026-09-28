# SAM Phase 14 — Integrated Message-Level Pipeline

This phase joins the real frozen LocaRDS physical branch with a deterministic
synthetic authenticator, cached trust verification, and the SAM fusion rule for
the same observation identifier. It measures the actual combined Python
pipeline rather than adding separately measured component times.

Run from the existing project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
python --version
```

Python must be 3.11 or 3.12. Phase 8 should already have installed the required
packages. If necessary:

```bash
python -m pip install -r ~/Downloads/sam_phase14_integrated_pipeline/requirements.txt
```

Run one warm-up and 30 measured fresh-process repetitions:

```bash
python ~/Downloads/sam_phase14_integrated_pipeline/scripts/run_integrated_pipeline.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase14_integrated_pipeline.json \
  --seed 1103 \
  --warmups 1 \
  --repetitions 30
```

Keep the Mac connected to power and close other compute-heavy applications.
The run may take several minutes.

Validate:

```bash
python ~/Downloads/sam_phase14_integrated_pipeline/scripts/validate_report.py \
  reports/sam_phase14_integrated_pipeline.json
```

Expected final line:

```text
SAM Phase 14 report validation passed.
```

Send back the JSON summary printed by the run command.

