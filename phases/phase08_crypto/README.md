# SAM Phase 8 — Cryptographic Verification

Run this phase from the existing `sam_phase1` project directory. Phase 1–7
files and results are not modified.

## 1. Activate the frozen environment

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
python --version
```

Python must be 3.11 or 3.12.

## 2. Install the one additional dependency

```bash
python -m pip install "cryptography>=42.0,<47.0"
```

## 3. Run Phase 8

```bash
python ~/Downloads/sam_phase8_crypto_verification/scripts/run_crypto_verification.py \
  --report reports/sam_phase8_crypto.json \
  --seed 1103 \
  --messages 10000 \
  --repetitions 5
```

## 4. Validate the report

```bash
python ~/Downloads/sam_phase8_crypto_verification/scripts/validate_report.py \
  reports/sam_phase8_crypto.json
```

Expected final line:

```text
SAM Phase 8 report validation passed.
```

This phase measures HMAC-SHA3-256/128 and ECDSA P-256 primitive costs. It does
not implement the Phase Overlay RF waveform, DO-260C/ED-102B framing, TESLA
delayed disclosure, certified airborne hardware, or full SAM evidence fusion.

