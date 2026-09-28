# SAM Experiment Environment Phase 1

This package establishes the reproducible Python environment and data-provenance checks for the SAM experiments targeting *Computer Networks*.

## Supported computer

- Apple MacBook Air M3
- 16 GB unified memory
- macOS on Apple Silicon
- Python 3.11 or 3.12

## 1. Create the environment

Open Terminal in this folder and run:

```bash
chmod +x setup_mac.sh
./setup_mac.sh
source .venv/bin/activate
```

The script creates a local virtual environment and installs only the packages required for Phase 1. It does not download research datasets.

## 2. Audit a CSV dataset

```bash
python scripts/audit_dataset.py /path/to/Dataset.csv --output reports/dataset_audit.json
```

The audit records the SHA-256 checksum, schema, time range, missingness, identifier counts, label distribution, duplicate counts, and whether the file resembles an OpenSky state-vector extract. It does not interpret unknown labels as attacks or anomalies.

## 3. Data-source policy

The authoritative source list is in `configs/data_sources.json`.

- OpenSky Weekly State Vectors: legacy traffic, density, controlled packet loss, and workload experiments.
- LocaRDS: receiver geometry and direct-TDoA physical verification.
- OpenSky Raw Data: message-ingest and physical-metadata experiments after schema inspection.
- Controlled 1090ES waveform generation: overlap-recovery experiments.
- Local CABBA/TESLA generator: authentication delay and security-overhead experiments.
- Local trust-service simulator: cache, expiry, revocation, and partition experiments.

## 4. Required provenance record

Every dataset used in reported results must have:

1. Dataset title and version
2. Creator or curator
3. DOI or authoritative URL
4. License or terms of use
5. Download date
6. Original filename
7. SHA-256 checksum
8. Applied filters and transformations
9. Script and configuration version

Unknown labels or undocumented derived fields must not be used in final experimental claims.

## Next phase

Phase 2 will download and prepare one LocaRDS subset and selected OpenSky state-vector hours. The exact files must be frozen in the experiment manifest before A0-A7 execution.
