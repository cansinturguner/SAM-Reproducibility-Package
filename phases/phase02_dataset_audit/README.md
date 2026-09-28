# SAM Phase 2 LocaRDS Audit

This package audits LocaRDS subset 1 without loading the 1.24 GB observation file into memory. It does not calculate final TDoA results and does not generate security or anomaly labels.

Copy `scripts/audit_locards.py` into the existing `sam_phase1/scripts` folder, or run it directly from this package.

From the `sam_phase1` folder with the virtual environment active:

```bash
source .venv/bin/activate
python /path/to/sam_phase2_locards/scripts/audit_locards.py \
  --root data/raw/locards/subset_1 \
  --output reports/locards_subset_1_audit.json \
  --chunk-size 100000
```

The script automatically accepts either of these layouts:

- `data/raw/locards/subset_1/set_1.csv`
- `data/raw/locards/subset_1/subset_1/set_1.csv`

Expected runtime depends on storage speed. Progress is printed after every chunk.

The resulting JSON report contains:

- source-file SHA-256 hashes;
- sensor and aircraft table validation;
- row and measurement counts;
- declared-versus-parsed measurement mismatches;
- known-sensor and good-sensor availability;
- trusted-aircraft availability;
- distributions for observations with at least 3 and at least 4 usable receivers;
- malformed measurement rows, without silently discarding them.

Do not delete either duplicate extraction until their SHA-256 values have been confirmed identical.
