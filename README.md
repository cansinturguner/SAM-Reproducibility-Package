# SAM reproducibility package

This package reproduces the Security Assurance Model experiments reported in the manuscript. It contains Phases 1-24 and the Phase 22B residual-tail audit. Phases 23 and 24 provide an independent CABBA application-layer comparison and a software-only PPM/D8PSK waveform-feasibility simulation.

## Authors and repository

- Cansin Turguner, Istanbul University-Cerrahpasa, ORCID: https://orcid.org/0000-0002-1946-5276
- Muhammed Ali Aydin, Istanbul University-Cerrahpasa
- Source repository: https://github.com/cansinturguner/SAM-Reproducibility-Package
- Archived release DOI: pending Zenodo release

## Evidence boundary

- LocaRDS subset 1 and subset 2 provide real decoded ADS-B observations, receiver metadata, and reception timestamps.
- Cryptographic authenticators are deterministic synthetic surrogates bound to real observations because LocaRDS does not contain SAM security packets.
- Protocol, packet-loss, trust-state, and outage cases are controlled experiments.
- Phase 24 implements a bounded complex-baseband PPM/D8PSK and RS(54,34) simulation. It does not implement GNU Radio, SDR transmission, raw-IQ capture, commercial-receiver testing, or operational RF compatibility.
- The package does not implement an operational PKI, ledger consensus, certified avionics hardware, or an attack/anomaly classifier.
- Reported precision, recall, F1, false-positive, or false-negative values do not exist because no attack-labeled dataset or classifier is used.

## Recorded environment

- Hardware: 2024 MacBook Air, Apple M3, 16 GB unified memory
- Operating systems recorded by the reports: Darwin 25.5.0 for the original Phase 1-20 and Phase 22/22B runs; Darwin 27.0.0 for Phase 21, the matched Phase 14 repeat, Phase 23, and Phase 24; arm64 in both environments
- Python: 3.12.14
- NumPy: 2.5.3 for Phases 7 and 14-22
- cryptography: 45.0.7 for the cryptographic phases
- SciPy: 1.18.1 and reedsolo: 1.7.0 in the recorded Phase 24 run
- Logical CPUs: 8
- Experiment seed: 1103 unless a phase README states otherwise

Phase 22 does not consume `trusted_good_ge3.csv.gz`; it reads the original
subset-2 CSV files and applies the frozen subset-1 calibration and Phase 5D
reference report. The dynamically propagated selected-file SHA-256 used by
Phases 4-7, 14, 17, 20, and 21 is therefore not an input to Phase 22.

Use Python 3.11 or 3.12. The paper measurements were produced with Python 3.12.14. Install `requirements.txt` in a clean virtual environment. Packages whose exact runtime versions were recorded are pinned; other dependencies retain the tested compatibility ranges from Phase 1 because their exact Mac environment versions were not preserved in the supplied reports.

## Dataset

Download LocaRDS from:

- Dataset DOI: https://doi.org/10.5281/zenodo.4739276
- Dataset paper: https://doi.org/10.3390/s21165516

Required files:

```text
data/raw/locards/subset_1/set_1.csv
data/raw/locards/subset_1/set_1_sensors.csv
data/raw/locards/subset_1/set_1_aircraft.csv
data/raw/locards/subset_2/set_2.csv
data/raw/locards/subset_2/set_2_sensors.csv
data/raw/locards/subset_2/set_2_aircraft.csv
```

Recorded SHA-256 values:

| File | SHA-256 |
| --- | --- |
| subset 1 observations | `6295f7f04afeecd997c329dc0b12712f81723a2fe4d1a7b8b8ea01727eef0ccf` |
| subset 1 sensors | `998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b` |
| subset 1 aircraft | `62b5b48bd66783074b2c9de65a5edd4de8f9f579f1fc05f3aabb9cb49a5a1a03` |
| subset 2 observations | `5ff68c7e402caa183678c03f4d23ba45b63bc96fa1177f8ce7e4fb530c45dd58` |
| subset 2 sensors | `998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b` |
| subset 2 aircraft | `70156a0865e655f4fb470e5814fd153708ac9f97ef193b70ebf3f4a5d84e1893` |

The subset archives and CSV files are not redistributed in this package.

## License

The original source code and package documentation are released under the MIT License; see `LICENSE`. The LocaRDS dataset is not redistributed and remains governed by its own CC BY-SA 4.0 terms.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python phases/phase01_environment/scripts/verify_environment.py
```

Run all implemented phases from the package root:

```bash
bash scripts/run_all.sh
```

The script checks that required dataset files exist, creates `reports/` and processed-data directories, and stops on the first error. Each phase directory also contains its original README and source-decision notes. Report validators are invoked whenever the phase includes one.

Phases 23 and 24 do not require LocaRDS. They can also be run independently:

```bash
bash scripts/run_phases23_24.sh
```

## Phase map

| Package directory | Manuscript role |
| --- | --- |
| phase01_environment | Environment and provenance policy |
| phase02_dataset_audit | LocaRDS subset-1 audit |
| phase03_selection | Trusted-aircraft and good-receiver selection; aircraft-level split |
| phase04_geometry | Development-only receiver geometry profile |
| phase05a_timestamp | Timestamp-unit audit |
| phase05b_calibration | Receiver bias/drift calibration |
| phase05c_geometry_validation | Development-validation geometry selection |
| phase05d_frozen_test | Frozen aircraft-disjoint subset-1 test |
| phase06_receiver_loss | Controlled receiver-observation loss |
| phase07_physical_benchmark | Physical-path time and memory benchmark |
| phase08_crypto | HMAC and ECDSA primitive verification |
| phase09_tesla | Delayed disclosure and loss workload |
| phase10_identity_trust | Signed identity/trust records and cache states |
| phase11_fusion | Evidence-fusion truth table and partial A0-A7 |
| phase12_ablation | Receiver gating and TESLA-recovery ablations |
| phase13_consolidation | Phase 5D-12 consolidation |
| phase14_integrated | Co-executed observation-level SAM path |
| phase15_trust_network | TCP signed trust lookup and cache benchmark |
| phase16_overhead | Logical security-byte accounting |
| phase17_trust_refresh | Integrated refresh, cache, outage, and backoff |
| phase18_conformance | Controlled protocol-conformance vectors |
| phase19a_baselines | Same-workload authentication baselines |
| phase19b_boundary | Functional-boundary and bootstrap comparison |
| phase20_scalability | Concurrent independent replay scaling |
| phase21_component_latency | Integrated cryptographic, direct-TDoA, fusion, and total-kernel latency profile |
| phase22_external | Frozen subset-1 configuration on subset 2 |
| phase22b_tail | Raw subset-2 residual-tail audit |
| phase23_cabba_comparison | Independent CABBA application-layer reproduction and same-workload SAM comparison |
| phase24_rf_waveform_feasibility | PPM/D8PSK complex-baseband AWGN and RS(54,34) decoding feasibility |

## Reproducibility limits

The package reproduces the Python reference implementation. Runtime values vary with hardware, operating system, package build, background load, and storage. The package does not establish real-time or certified airborne performance. External validation uses a second released LocaRDS partition but the same published sensor-metadata source. Phase 23 does not use the CABBA authors' SDR code, and Phase 24 assumes perfect synchronization over complex AWGN. Neither phase establishes RTCA conformance or commercial-receiver compatibility.
