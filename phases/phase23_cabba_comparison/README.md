# SAM Phase 23 CABBA Comparison

This phase independently reimplements the published CABBA application-layer
authentication workflow and compares it with the frozen SAM cryptographic,
cached-trust, and fusion stage on the same deterministic message workload and
machine.

The package is not the CABBA authors' original code. It follows the published
Type A, B1, B2, and C packet roles, the 128-bit interval key, the 196-bit Type A
MAC limit, the 8-bit sequence number, the 512-bit ECDSA signature, the five-
second TESLA interval, and the four timing scenarios reported in the CABBA
paper. The paper specifies HMAC but does not identify a concrete digest in the
available protocol description. This reproduction therefore records
HMAC-SHA-256 as an explicit implementation choice rather than attributing it
to the authors.

The source paper is internally inconsistent about the most bandwidth-efficient
Scenario 4 timing. Table 3 lists `TB2=15 s` and `TC=30 s`; nearby prose says B2
is sent every other five-second interval, while later uncertainty tables use
`TB2=TC=30 s`. This reproduction uses the explicit Table 3 schedule for its
accounting and records the discrepancy rather than silently reconciling it.

## Scope

Implemented:

- CABBA Type A post-disclosure HMAC generation and verification;
- 128-bit reverse key chain and next-interval disclosure;
- Type B1 key-chain validation;
- Type B2 P-256 signed-key verification;
- Type C CA-signed aircraft-key verification;
- published Scenario 1-4 scheduling and analytical packet/airtime accounting;
- scheduled receiver-compute measurements using CABBA Scenario 4 and the
  frozen SAM Phase 19A key schedule;
- deterministic negative protocol vectors;
- same-process CABBA versus SAM cryptographic-stage timing.

Not implemented:

- D8PSK phase-overlay waveform generation or demodulation;
- RS(54,34), RF framing, BER, Eb/N0, or receiver compatibility tests;
- the CABBA authors' unavailable custom SDR scripts;
- complete X.509 or operational aviation PKI;
- SAM direct-TDoA processing in the authentication-only comparison row;
- certified airborne hardware.

## Placement

Install this directory as:

```text
SAM_Reproducibility_Package/phases/phase23_cabba_comparison/
```

Do not keep the former `sam_phase23_cabba_comparison` directory name inside the
reproducibility package.

## Run

From the `SAM_Reproducibility_Package` root, with its virtual environment
active:

```bash
python3 -m pip install -r phases/phase23_cabba_comparison/requirements.txt

python3 phases/phase23_cabba_comparison/scripts/run_phase23.py \
  --report reports/sam_phase23_cabba_comparison.json \
  --seed 1103 \
  --message-count 10000 \
  --repetitions 10 \
  --message-rate 6.2

python3 phases/phase23_cabba_comparison/scripts/validate_report.py \
  reports/sam_phase23_cabba_comparison.json
```

Equivalent wrapper:

```bash
bash phases/phase23_cabba_comparison/run_phase.sh
```

Do not add numerical values to the manuscript until the validator passes on
the recorded experiment machine.
