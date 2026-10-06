# SAM Phase 25C — Injection Dataset Suitability Audit

This phase audits the downloaded **ADS-B Message Injection Attacks Dataset**,
DOI `10.17632/6fhw732ccz.1`, before it is used in SAM.

Published metadata describe 22,316 messages, 17 predictor features, and four labels:
0 legitimate, 1 path modification, 2 ghost injection, and 3 velocity drift.
The audit verifies the actual downloaded file rather than assuming that the
published description matches a local copy.

The released `Dataset.csv` contains 18 columns in total: 17 predictor features
and one `label` column. Phase 25C v2 records both counts explicitly.

Download version 1 from the DOI landing page and place, without renaming, the
files under:

```text
data/external/mendeley_adsb_injection/Dataset.csv
data/external/mendeley_adsb_injection/Receiver messages.csv
```

The dataset is CC BY 4.0 and is not redistributed in this package.

## Run

```bash
bash phases/phase25c_injection_dataset_audit/run_phase.sh
```

Phase 25C only audits suitability. It does not automatically merge the data
with LocaRDS or claim that message-level labels provide the multi-receiver
timestamps and receiver coordinates required by direct TDoA.
