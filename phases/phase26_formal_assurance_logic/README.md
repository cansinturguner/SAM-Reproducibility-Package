# Phase 26 Formal Assurance Logic Verification

Phase 26 gives the SAM fusion policy a finite-state specification and checks
every admissible combination of cryptographic, trust, and physical evidence.
It is an exhaustive verification of the stated finite model, not a proof of
the correctness of cryptographic primitives, sensors, or an operational ADS-B
deployment.

## State domains

- Cryptographic evidence: `VERIFIED`, `CONFLICTING`, `PENDING`, `ABSENT`
- Trust evidence: `VALID`, `REVOKED`, `STALE`, `ABSENT`
- Physical evidence: `CONSISTENT`, `CONFLICTING`, `UNAVAILABLE`

`VALID` trust includes either an online-valid record or an unexpired valid
cache entry. `STALE` means that the policy-defined cache lifetime has expired.

The secured policy evaluates 4 x 4 x 3 = 48 combinations. The A0 legacy path
is checked separately and is the only path that may return
`LEGACY_UNASSURED`.

## Decision rule

Conflict has priority:

1. Return `CONFLICTING` if cryptographic evidence conflicts, the credential is
   revoked, or physical evidence conflicts.
2. Otherwise return `VERIFIED` only when cryptographic evidence is verified,
   trust is valid, and physical evidence is consistent.
3. Return `INSUFFICIENT_EVIDENCE` for every remaining secured-policy state.

## Run

From the root of `SAM_Reproducibility_Package`:

```bash
bash scripts/run_phase26.sh
```

Or run the scripts directly:

```bash
python phases/phase26_formal_assurance_logic/scripts/run_phase26.py
python phases/phase26_formal_assurance_logic/scripts/validate_report.py
```

The run writes:

- `reports/sam_phase26_formal_assurance_logic.json`
- `reports/sam_phase26_formal_assurance_truth_table.csv`

The experiment uses only the Python standard library.

