# SAM reproducibility package

This repository reproduces the software experiments reported for the Security Assurance Model (SAM). Version 1.2.0 covers Phases 1–37 and archives the machine-readable reports behind the manuscript results of Phases 21 and 23–37, together with a documented cross-platform rerun check. Phases 25–32 introduce a development-selected physical-consistency threshold, controlled attack sensitivity, formal assurance-logic verification, threshold-aware integration and outage behavior, receiver-corruption safeguards, operating-point sensitivity, receiver-integrity analysis, and track-level persistence. Phases 33–37 add an explicit reference transport with analytical airtime, a joint evidence-branch replay, TESLA burst-loss, timing, sequence, and downgrade robustness, a fusion-policy sensitivity analysis, and a denominator, artifact, and position-bias audit.

## Authors and repository

- Cansin Turguner, Istanbul University-Cerrahpasa, ORCID: https://orcid.org/0000-0002-1946-5276
- Muhammed Ali Aydin, Istanbul University-Cerrahpasa
- Source repository: https://github.com/cansinturguner/SAM-Reproducibility-Package
- Archived software version DOI (v1.2.0): https://doi.org/10.5281/zenodo.23727987
- Archived software concept DOI: https://doi.org/10.5281/zenodo.23023229

The concept DOI resolves to the most recent Zenodo release. Release-specific DOIs remain available for immutable version citation.

The GitHub `main` branch may contain a later development version than the most recent Zenodo archive. Cite the release-specific DOI above when referring to version 1.2.0, and use the concept DOI for the latest archived version.

## Evidence boundary

- LocaRDS subsets 1 and 2 provide real decoded ADS-B observations, receiver metadata, and reception timestamps.
- The two LocaRDS subsets share the same published sensor-metadata source. Their comparison is therefore cross-partition transfer validation, not validation on an independent sensor network.
- Cryptographic authenticators are deterministic synthetic surrogates bound to real observations because LocaRDS does not contain transmitted SAM security packets.
- Protocol, packet-loss, trust-state, service-outage, position-bias, receiver-corruption, and track-persistence cases are controlled software experiments.
- The physical-decision threshold is selected only from development data and then applied without retuning to the subset-1 test and subset-2 transfer partitions.
- Phase 25C audits a separately published labeled injection dataset. The detected fields do not support direct-TDoA evaluation, so that dataset is not automatically integrated into the SAM physical branch and is not redistributed here.
- Phase 24 implements a bounded complex-baseband PPM/D8PSK and RS(54,34) simulation. It does not implement GNU Radio, SDR transmission, raw-IQ capture, commercial-receiver testing, or operational RF compatibility.
- The package does not implement an operational PKI, ledger consensus, certified avionics hardware, or an attack/anomaly classifier.
- The reported conflict and sensitivity fractions are empirical results under the stated reference and controlled perturbation models. They are not operational attack prevalence estimates.

## Recorded environment

- Hardware: 2024 MacBook Air, Apple M3, 16 GB unified memory
- Operating system: Darwin 27.0.0, arm64, as recorded by the individual reports
- Python: 3.12.14
- NumPy: 2.5.3 for the later integrated and decision experiments
- cryptography: 45.0.7 for the cryptographic phases
- SciPy: 1.18.1 and reedsolo: 1.7.0 for the recorded Phase 24 run
- Logical CPUs: 8
- Experiment seed: 1103 unless a phase README states otherwise

An independent cross-platform rerun executed the Phase 1–32 workflows, excluding the Phase 27B offset-outage scenario, without source changes under WSL2/Linux on x86-64 hardware with Python 3.13.10, NumPy 2.5.3, and 32 logical processors. It reproduced the deterministic thresholds, assurance counts, controlled-perturbation outcomes, the earlier boundary-aligned outage result, finite-state checks, and persistence selection. The Phase 27B offset-outage scenario with explicit post-outage accounting, the Phase 32 v3 persistence metrics, and Phases 33–37 were run only in the primary Mac environment. Absolute timing values changed, as expected for a different runtime and processor architecture. The compact machine-readable summary is provided in `reports/sam_cross_platform_validation_wsl2_python313.json`; the large rerun workspace, LocaRDS-derived intermediate tables, and duplicated platform-specific reports are not redistributed.

Use Python 3.12 for the reference environment. The manuscript measurements were produced with Python 3.12.14; the independent cross-platform check completed with Python 3.13.10. Install `requirements.txt` in a clean virtual environment. Individual phase READMEs record additional dependencies and execution boundaries.

## Dataset

Download LocaRDS from:

- Dataset DOI: https://doi.org/10.5281/zenodo.4739276
- Dataset paper: https://doi.org/10.3390/s21165516

Place the released files at:

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

Phase 3 writes the selected subset-1 rows to `data/processed/locards_subset_1/trusted_good_ge3.csv.gz`. Because gzip stores a creation timestamp in its header, the SHA-256 of this compressed file differs between runs even when its content is identical; `scripts/run_all.sh` therefore reads the hash of the newly written file from `reports/locards_subset_1_selection_manifest.json` and passes it to the later phases. The selected content is identified by the SHA-256 of the uncompressed CSV, `2514a1b4a4dfdff936e610d2e01943c5ae883cc3edc51c7204a8502378a07d9b`, which can be checked with `gunzip -c data/processed/locards_subset_1/trusted_good_ge3.csv.gz | shasum -a 256`. When a phase is run on its own, pass the hash recorded in the selection manifest with `--expected-selected-sha256`.

The LocaRDS archives and CSV files are not redistributed. Phase 31 event tables are generated locally from LocaRDS and are likewise not included. Phase 32 consumes those locally generated event tables. Small files under phase-specific `test_fixture` or `test_output` directories are synthetic unit-test fixtures, not extracts from the LocaRDS release.

Phase 25C expects the independently obtained labeled dataset files at:

```text
data/external/Dataset.csv
data/external/Receiver messages.csv
```

These third-party files are not redistributed. Phase 25C is a metadata and suitability audit; it does not evaluate the SAM direct-TDoA branch on that dataset.

## License

The SAM source code and package documentation are released under the MIT License; see `LICENSE`. LocaRDS and any separately obtained third-party datasets remain governed by their original licenses.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python phases/phase01_environment/scripts/verify_environment.py
```

The original workflow through Phase 24 remains available as:

```bash
bash scripts/run_all.sh
```

Phases 23 and 24 do not require LocaRDS and can be run independently:

```bash
bash scripts/run_phases23_24.sh
```

The added experiments should be run in numerical order. Root launchers are supplied for Phases 26–30:

```bash
bash scripts/run_phase26.sh
bash scripts/run_phase27.sh
bash scripts/run_phase28.sh
bash scripts/run_phase29.sh
bash scripts/run_phase30.sh
```

Phases 25A–25C, 31, and 32 provide phase-specific instructions in their own README files. Run Phase 31 before Phase 32 because the latter evaluates persistence over the locally generated Phase 31 event tables. Each phase also provides a validator or self-test where applicable.

Phases 33–37 and the Phase 32 v3 persistence report are produced by one launcher, after Phases 25–32:

```bash
bash scripts/run_phases33_37.sh
```

Phases 33, 35, and 36 do not read LocaRDS. Phases 34 and 37 require the LocaRDS files and the processed subset-1 selection and calibration files. The Phase 32 v3 step runs only when the locally generated Phase 31 event tables are present.

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
| phase11_fusion | Evidence-fusion truth table and partial A0–A7 evaluation |
| phase12_ablation | Receiver gating and TESLA-recovery ablations |
| phase13_consolidation | Phase 5D–12 consolidation |
| phase14_integrated | Co-executed observation-level SAM path |
| phase15_trust_network | TCP signed trust lookup and cache benchmark |
| phase16_overhead | Logical security-byte accounting |
| phase17_trust_refresh | Integrated refresh, cache, outage, and backoff |
| phase18_conformance | Controlled protocol-conformance vectors |
| phase19a_baselines | Same-workload authentication baselines |
| phase19b_boundary | Functional-boundary and bootstrap comparison |
| phase20_scalability | Concurrent independent replay scaling |
| phase21_component_latency | Integrated cryptographic, direct-TDoA, fusion, and total-kernel latency profile |
| phase22_external | Frozen subset-1 configuration applied to subset 2 without retuning |
| phase22b_tail | Raw subset-2 residual-tail audit |
| phase23_cabba_comparison | Independent CABBA application-layer reproduction and same-workload SAM comparison |
| phase24_rf_waveform_feasibility | PPM/D8PSK complex-baseband AWGN and RS(54,34) decoding feasibility |
| phase25a_physical_decision | Development-selected physical threshold and benign-reference conflict measurement |
| phase25b_attack_sensitivity | Controlled position-bias and fixed-ground-spoofer sensitivity |
| phase25c_injection_dataset_audit | Published labeled-dataset metadata and direct-TDoA suitability audit |
| phase26_formal_assurance_logic | Exhaustive finite-state policy and transition verification |
| phase27_threshold_aware_integration | Threshold-aware integrated replay plus aligned and offset trust-outage scenarios with explicit post-outage cache accounting |
| phase28_receiver_corruption | Single-receiver and reference-receiver corruption sensitivity |
| phase29_threshold_operating_point | Threshold operating-point sensitivity |
| phase30_reference_independent_guard | Reference-independent receiver-integrity guard |
| phase31_receiver_integrity | Receiver-integrity event characterization across development and transfer partitions |
| phase32_track_persistence | Track-level persistence evaluation using Phase 31 events (v3 report) |
| phase33_sam_airtime | SAM reference transport and analytical added airtime |
| phase34_joint_branch_replay | Joint cryptographic, trust, and physical branch replay |
| phase35_protocol_robustness | TESLA burst loss, timing boundary, sequence boundary, and downgrade routing |
| phase36_fusion_policy_sensitivity | Strict versus corroborated-conflict fusion policy |
| phase37_denominator_audit | Physical-evidence denominators, conflict-tail attribution, and baseline-adjusted position-bias sensitivity |

The frozen Phase 31 receiver-integrity model is included as `reports/sam_phase31_receiver_integrity_model.json`. The larger Phase 31 event tables are intentionally regenerated locally and are not redistributed.

## Archived reports

The `reports/` directory contains one primary-platform report for every phase from 2 to 37, together with the cross-platform summary. All reports were recorded on the hardware and software listed under Recorded environment and reference the same selected subset-1 input file (`trusted_good_ge3.csv.gz`, SHA-256 `b4782ef1f7f33c3155bbcad6b4d170b0b03917e54f04ee447ea94d935ce458ec`; uncompressed content SHA-256 `2514a1b4a4dfdff936e610d2e01943c5ae883cc3edc51c7204a8502378a07d9b`).

- Phases 4–20, 22, and 22B were executed with `scripts/run_all.sh` from Phase 4 onward, reusing the recorded Phase 2 audit, the Phase 3 selection manifest, and the selected input file. Their deterministic outputs reproduce the earlier runs, and the receiver-clock calibration file they produce is byte-identical to the one consumed by Phases 25–37.
- The reports for Phases 21 and 23–37 are the original recorded runs. A rerun of Phases 21, 23, and 24 reproduced every non-timing field.
- The Phase 32 report is `sam_phase32_track_persistence_v3.json`.
- Phases 11–14, 17, and 19B precede the development-selected physical threshold of Phase 25A. Their assurance counts therefore contain no PHYSICALLY_CONFLICTING outcome (for example, 78,358 VERIFIED rows in Phase 14), and their integrated-path timing excludes the threshold decision. The threshold-aware assurance counts and the 46.779-microsecond complete-path median are reported by Phase 27A. In particular, the `SAM cached integrated path` row of the Phase 19B comparison is the Phase 14 pre-threshold pipeline and is not the threshold-aware SAM path.

Timing and memory values vary from run to run; a rerun reproduces the deterministic results but not the exact timing values recorded here.

## Reproducibility limits

The package reproduces a Python reference implementation. Runtime values vary with hardware, operating system, package build, background load, and storage. The cross-platform rerun confirms deterministic computational reproducibility but does not make timing portable across platforms. The results do not establish real-time or certified airborne performance. The subset-2 experiment is a cross-partition transfer test within the same published receiver infrastructure, not independent-field validation. Controlled perturbations are synthetic and do not provide operational RF attack ground truth. LocaRDS does not contain SAM authenticators co-captured with the original broadcasts. Phase 23 does not use the CABBA authors' SDR code, and Phase 24 assumes perfect synchronization over complex AWGN. The package therefore does not establish RTCA conformance, commercial-receiver compatibility, or deployment readiness.
