#!/usr/bin/env python3
"""Exhaustively verify the finite SAM assurance-composition policy."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import platform
import sys
from collections import Counter
from pathlib import Path


CRYPTO_STATES = ("VERIFIED", "CONFLICTING", "PENDING", "ABSENT")
TRUST_STATES = ("VALID", "REVOKED", "STALE", "ABSENT")
PHYSICAL_STATES = ("CONSISTENT", "CONFLICTING", "UNAVAILABLE")

VERIFIED = "VERIFIED"
CONFLICTING = "CONFLICTING"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
LEGACY = "LEGACY_UNASSURED"


def sam_policy(crypto: str, trust: str, physical: str) -> tuple[str, str]:
    """Implemented conflict-dominant SAM policy and its reason code."""
    if crypto == "CONFLICTING":
        return CONFLICTING, "CRYPTOGRAPHIC_CONFLICT"
    if trust == "REVOKED":
        return CONFLICTING, "REVOKED_CREDENTIAL"
    if physical == "CONFLICTING":
        return CONFLICTING, "PHYSICAL_CONFLICT"
    if crypto == "VERIFIED" and trust == "VALID" and physical == "CONSISTENT":
        return VERIFIED, "ALL_REQUIRED_EVIDENCE_SUPPORTS"
    missing = []
    if crypto != "VERIFIED":
        missing.append(f"CRYPTO_{crypto}")
    if trust != "VALID":
        missing.append(f"TRUST_{trust}")
    if physical != "CONSISTENT":
        missing.append(f"PHYSICAL_{physical}")
    return INSUFFICIENT, "+".join(missing)


def specification(crypto: str, trust: str, physical: str) -> str:
    conflict = (
        crypto == "CONFLICTING"
        or trust == "REVOKED"
        or physical == "CONFLICTING"
    )
    support = (
        crypto == "VERIFIED"
        and trust == "VALID"
        and physical == "CONSISTENT"
    )
    if conflict:
        return CONFLICTING
    if support:
        return VERIFIED
    return INSUFFICIENT


def legacy_policy() -> tuple[str, str]:
    return LEGACY, "A0_NO_SECURITY_ASSURANCE"


def mutant_no_physical_requirement(c: str, t: str, p: str) -> str:
    if c == "CONFLICTING" or t == "REVOKED" or p == "CONFLICTING":
        return CONFLICTING
    if c == "VERIFIED" and t == "VALID":
        return VERIFIED
    return INSUFFICIENT


def mutant_conflict_after_support(c: str, t: str, p: str) -> str:
    if c == "VERIFIED" and t == "VALID" and p == "CONSISTENT":
        return VERIFIED
    if c == "CONFLICTING":
        return INSUFFICIENT
    if t == "REVOKED" or p == "CONFLICTING":
        return CONFLICTING
    return INSUFFICIENT


def mutant_revocation_is_missing(c: str, t: str, p: str) -> str:
    if c == "CONFLICTING" or p == "CONFLICTING":
        return CONFLICTING
    if c == "VERIFIED" and t == "VALID" and p == "CONSISTENT":
        return VERIFIED
    return INSUFFICIENT


def mutant_pending_is_verified(c: str, t: str, p: str) -> str:
    if c == "CONFLICTING" or t == "REVOKED" or p == "CONFLICTING":
        return CONFLICTING
    if c in {"VERIFIED", "PENDING"} and t == "VALID" and p == "CONSISTENT":
        return VERIFIED
    return INSUFFICIENT


def report_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    report_dir = repo_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "sam_phase26_formal_assurance_logic.json"
    csv_path = report_dir / "sam_phase26_formal_assurance_truth_table.csv"

    rows = []
    all_cases = list(itertools.product(CRYPTO_STATES, TRUST_STATES, PHYSICAL_STATES))
    for index, (crypto, trust, physical) in enumerate(all_cases, start=1):
        decision, reason = sam_policy(crypto, trust, physical)
        expected = specification(crypto, trust, physical)
        rows.append(
            {
                "case_id": index,
                "crypto": crypto,
                "trust": trust,
                "physical": physical,
                "decision": decision,
                "reason": reason,
                "specification_decision": expected,
                "matches_specification": decision == expected,
            }
        )

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    decisions = Counter(row["decision"] for row in rows)
    predicates = {
        "state_space_complete": len(rows) == 48 and len({(r['crypto'], r['trust'], r['physical']) for r in rows}) == 48,
        "implementation_matches_specification": all(r["matches_specification"] for r in rows),
        "decision_totality": all(r["decision"] in {VERIFIED, CONFLICTING, INSUFFICIENT} for r in rows),
        "verified_iff_all_required_support": all(
            (r["decision"] == VERIFIED)
            == (r["crypto"] == "VERIFIED" and r["trust"] == "VALID" and r["physical"] == "CONSISTENT")
            for r in rows
        ),
        "conflict_dominance": all(
            r["decision"] == CONFLICTING
            for r in rows
            if r["crypto"] == "CONFLICTING" or r["trust"] == "REVOKED" or r["physical"] == "CONFLICTING"
        ),
        "absence_pending_or_stale_without_conflict_is_insufficient": all(
            r["decision"] == INSUFFICIENT
            for r in rows
            if r["crypto"] != "CONFLICTING"
            and r["trust"] != "REVOKED"
            and r["physical"] != "CONFLICTING"
            and not (r["crypto"] == "VERIFIED" and r["trust"] == "VALID" and r["physical"] == "CONSISTENT")
        ),
        "revocation_dominance": all(r["decision"] == CONFLICTING for r in rows if r["trust"] == "REVOKED"),
        "secured_policy_never_returns_legacy": all(r["decision"] != LEGACY for r in rows),
        "legacy_isolation": legacy_policy()[0] == LEGACY,
    }

    transitions = [
        {
            "name": "tesla_disclosure_valid",
            "before": sam_policy("PENDING", "VALID", "CONSISTENT")[0],
            "after": sam_policy("VERIFIED", "VALID", "CONSISTENT")[0],
            "expected": [INSUFFICIENT, VERIFIED],
        },
        {
            "name": "tesla_disclosure_invalid",
            "before": sam_policy("PENDING", "VALID", "CONSISTENT")[0],
            "after": sam_policy("CONFLICTING", "VALID", "CONSISTENT")[0],
            "expected": [INSUFFICIENT, CONFLICTING],
        },
        {
            "name": "cache_expiry",
            "before": sam_policy("VERIFIED", "VALID", "CONSISTENT")[0],
            "after": sam_policy("VERIFIED", "STALE", "CONSISTENT")[0],
            "expected": [VERIFIED, INSUFFICIENT],
        },
        {
            "name": "credential_revocation",
            "before": sam_policy("VERIFIED", "VALID", "CONSISTENT")[0],
            "after": sam_policy("VERIFIED", "REVOKED", "CONSISTENT")[0],
            "expected": [VERIFIED, CONFLICTING],
        },
        {
            "name": "physical_evidence_arrives_consistent",
            "before": sam_policy("VERIFIED", "VALID", "UNAVAILABLE")[0],
            "after": sam_policy("VERIFIED", "VALID", "CONSISTENT")[0],
            "expected": [INSUFFICIENT, VERIFIED],
        },
        {
            "name": "physical_evidence_arrives_conflicting",
            "before": sam_policy("VERIFIED", "VALID", "UNAVAILABLE")[0],
            "after": sam_policy("VERIFIED", "VALID", "CONFLICTING")[0],
            "expected": [INSUFFICIENT, CONFLICTING],
        },
    ]
    for item in transitions:
        item["passed"] = [item["before"], item["after"]] == item["expected"]

    mutants = {
        "drops_physical_requirement": mutant_no_physical_requirement,
        "loses_crypto_conflict_dominance": mutant_conflict_after_support,
        "treats_revocation_as_missing": mutant_revocation_is_missing,
        "accepts_pending_authentication": mutant_pending_is_verified,
    }
    mutation_results = []
    for name, mutant in mutants.items():
        differing = []
        for crypto, trust, physical in all_cases:
            expected = specification(crypto, trust, physical)
            observed = mutant(crypto, trust, physical)
            if observed != expected:
                differing.append(
                    {
                        "crypto": crypto,
                        "trust": trust,
                        "physical": physical,
                        "expected": expected,
                        "mutant": observed,
                    }
                )
        mutation_results.append(
            {
                "mutant": name,
                "killed": bool(differing),
                "differing_cases": len(differing),
                "first_counterexample": differing[0] if differing else None,
            }
        )

    passed = (
        all(predicates.values())
        and all(item["passed"] for item in transitions)
        and all(item["killed"] for item in mutation_results)
    )
    report = {
        "schema": "sam.phase26.formal-assurance-logic.v1",
        "scope": "exhaustive finite-state verification of SAM assurance composition",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "state_domains": {
            "cryptographic": list(CRYPTO_STATES),
            "trust": list(TRUST_STATES),
            "physical": list(PHYSICAL_STATES),
            "secured_policy_combinations": len(rows),
            "legacy_cases": 1,
        },
        "decision_distribution": dict(sorted(decisions.items())),
        "properties": predicates,
        "transition_checks": transitions,
        "mutation_checks": mutation_results,
        "artifacts": {
            "truth_table_csv": str(csv_path.relative_to(repo_root)),
            "truth_table_sha256": report_sha256(csv_path),
        },
        "overall_pass": passed,
        "interpretation_limits": [
            "This is exhaustive verification of the stated finite policy model, not proof of sensor, cryptographic primitive, or implementation security.",
            "The experiment verifies assurance-state composition and transition semantics; it does not estimate attack prevalence or detection accuracy.",
            "Operational correctness still depends on the evidence-producing branches and stated trust assumptions.",
        ],
    }
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

