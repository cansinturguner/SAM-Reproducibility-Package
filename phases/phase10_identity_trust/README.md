# SAM Phase 10 — Identity, Signed B2 Keys, and Trust-Service Degradation

This phase implements and benchmarks:

- an ECDSA P-256 CA signature over an aircraft public-key record;
- an ECDSA P-256 aircraft signature over TESLA interval keys (B2 role);
- verification of the CA record, B2 key, and a representative HMAC;
- online, valid-cache, cold-offline, expired-cache, and revoked-record modes;
- deterministic `VERIFIED`, `INSUFFICIENT_EVIDENCE`, and `CONFLICTING`
  assurance states.

It does not modify Phase 1–9 results.

Run from the existing project root:

```bash
cd ~/Downloads/sam_phase1
source .venv/bin/activate
python --version
```

Phase 8 already installed `cryptography`. If needed:

```bash
python -m pip install "cryptography>=42.0,<47.0"
```

Run:

```bash
python ~/Downloads/sam_phase10_identity_trust/scripts/run_identity_trust_experiment.py \
  --report reports/sam_phase10_identity_trust.json \
  --seed 1103 \
  --iterations 10000 \
  --repetitions 5 \
  --cache-ttl-seconds 900
```

Validate:

```bash
python ~/Downloads/sam_phase10_identity_trust/scripts/validate_report.py \
  reports/sam_phase10_identity_trust.json
```

Expected final line:

```text
SAM Phase 10 report validation passed.
```

This is a message-layer prototype on a MacBook. It is not an X.509
implementation, permissioned blockchain benchmark, Phase Overlay RF test, or
certified airborne implementation.

