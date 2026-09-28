# SAM Phase 24 RF Waveform Feasibility (v2)

This phase adds a software-only physical-layer feasibility experiment for the
published CABBA D8PSK overlay. It is deliberately separate from the frozen SAM
results and from the Phase 23 application-layer CABBA comparison.

## Implemented

- deterministic 1090ES-style 112-bit PPM envelope generation;
- differential 8-PSK complex-baseband overlay;
- the published 336-bit overlay accounting: 12 reference bits, 204 security
  bits, and 120 parity bits;
- systematic RS(54,34) encoding over 6-bit symbols using a recorded
  implementation choice for the GF(64) primitive polynomial;
- hard-decision D8PSK reception over an AWGN channel;
- raw overlay BER, raw security-payload BER, and the fraction of packets whose
  symbol-error count is within the RS(54,34) correction radius;
- an actual GF(64) RS decoder, with correct payload, declared failure, and
  miscorrection reported separately;
- exact binomial confidence intervals and a deterministic waveform smoke test;
- a machine-readable JSON report and independent validator.

## Not implemented

- GNU Radio flowgraphs or GNU Radio scheduler measurements;
- over-the-air transmission, HackRF/USRP integration, antennas, or RF front-end
  effects;
- 1090ES preamble acquisition, carrier/timing recovery, multipath, Doppler,
  interference, clipping, oscillator error, or receiver AGC;
- a bit-exact reproduction of the RTCA MOPS encoder/interleaver;
- commercial ADS-B receiver compatibility testing;
- the CABBA authors' unavailable custom scripts.

The GF(64) primitive polynomial `x^6 + x + 1`, generator-root convention, bit
mapping, and differential phase mapping are explicit implementation choices.
They must not be attributed to the CABBA authors or RTCA without an authoritative
bit-level specification.

## Placement

Install this directory as:

```text
SAM_Reproducibility_Package/phases/phase24_rf_waveform_feasibility/
```

Do not keep the former `sam_phase24_rf_waveform_feasibility` directory name
inside the reproducibility package.

## Run

From the `SAM_Reproducibility_Package` root, with its virtual environment
active:

```bash
python3 -m pip install -r phases/phase24_rf_waveform_feasibility/requirements.txt

python3 phases/phase24_rf_waveform_feasibility/scripts/run_phase24.py \
  --report reports/sam_phase24_rf_waveform_feasibility_v2.json \
  --seed 1103 \
  --packets-per-ebno 10000 \
  --highest-ebno-packets 20000 \
  --ebno-db 8 10 12 14 15 16 18

python3 phases/phase24_rf_waveform_feasibility/scripts/validate_report.py \
  reports/sam_phase24_rf_waveform_feasibility_v2.json
```

Equivalent wrapper:

```bash
bash phases/phase24_rf_waveform_feasibility/run_phase.sh
```

Do not add numerical values to the manuscript until the report passes validation
on the recorded experiment machine. A zero observed error count is not proof of
zero BER; use the reported confidence upper bound.

## GNU Radio continuation

The next step, if GNU Radio and suitable SDR hardware are available, is a
separate controlled loopback experiment. Begin with file or cabled/attenuated
loopback. Do not radiate test traffic in the operational 1090 MHz aviation band.
The intended flow is documented in `GNU_RADIO_NEXT.md`.
