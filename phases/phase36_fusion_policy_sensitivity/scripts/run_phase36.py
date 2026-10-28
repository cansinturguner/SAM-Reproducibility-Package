#!/usr/bin/env python3
"""Compare conflict-dominant and corroborated-conflict fusion policies."""

from __future__ import annotations

import argparse
import itertools
import json
import platform
from collections import Counter
from pathlib import Path


CRYPTO = ("VERIFIED", "CONFLICTING", "PENDING", "ABSENT")
TRUST = ("VALID", "REVOKED", "STALE", "ABSENT")
PHYSICAL = ("PHYSICALLY_CONSISTENT", "PHYSICALLY_CONFLICTING", "PHYSICAL_EVIDENCE_UNAVAILABLE")


def strict(crypto: str, trust: str, physical: str) -> str:
    if crypto == "CONFLICTING" or trust == "REVOKED" or physical == "PHYSICALLY_CONFLICTING":
        return "CONFLICTING"
    if crypto == "VERIFIED" and trust == "VALID" and physical == "PHYSICALLY_CONSISTENT":
        return "VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def corroborated(crypto: str, trust: str, physical: str) -> str:
    if trust == "REVOKED":
        return "CONFLICTING"
    conflict_count = int(crypto == "CONFLICTING") + int(physical == "PHYSICALLY_CONFLICTING")
    if conflict_count >= 2:
        return "CONFLICTING"
    if crypto == "VERIFIED" and trust == "VALID" and physical == "PHYSICALLY_CONSISTENT":
        return "VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def split_key(key: str) -> tuple[str, str, str]:
    parts = key.split("|")
    if len(parts) != 3:
        raise ValueError(f"invalid evidence-combination key: {key}")
    return parts[0], parts[1], parts[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase34-report", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    truth_rows = []
    strict_distribution = Counter()
    alternative_distribution = Counter()
    for crypto, trust, physical in itertools.product(CRYPTO, TRUST, PHYSICAL):
        s = strict(crypto, trust, physical)
        a = corroborated(crypto, trust, physical)
        strict_distribution[s] += 1
        alternative_distribution[a] += 1
        truth_rows.append(
            {
                "cryptographic": crypto,
                "trust": trust,
                "physical": physical,
                "strict_conflict_dominant": s,
                "corroborated_conflict": a,
                "different": s != a,
            }
        )

    replay = None
    if args.phase34_report:
        source = json.loads(args.phase34_report.read_text(encoding="utf-8"))
        if source.get("schema") != "sam.phase34.joint-branch-replay.v1":
            raise SystemExit("unsupported Phase 34 report")
        scenarios = []
        for scenario in source["scenarios"]:
            strict_counts = Counter()
            alternative_counts = Counter()
            transitions = Counter()
            for key, count in scenario["evidence_combination_counts"].items():
                crypto, trust, physical = split_key(key)
                s = strict(crypto, trust, physical)
                a = corroborated(crypto, trust, physical)
                strict_counts[s] += count
                alternative_counts[a] += count
                transitions[f"{s}->{a}"] += count
            scenarios.append(
                {
                    "name": scenario["name"],
                    "strict_conflict_dominant": dict(sorted(strict_counts.items())),
                    "corroborated_conflict": dict(sorted(alternative_counts.items())),
                    "decision_transitions": dict(sorted(transitions.items())),
                    "changed_observations": sum(
                        count for key, count in transitions.items() if key.split("->")[0] != key.split("->")[1]
                    ),
                }
            )
        replay = {
            "source_report": str(args.phase34_report),
            "eligible_rows": source["population"]["eligible_rows"],
            "scenarios": scenarios,
        }

    illustrative_sequences = {
        "isolated_physical_conflict": {
            "states": [
                ("VERIFIED", "VALID", "PHYSICALLY_CONSISTENT"),
                ("VERIFIED", "VALID", "PHYSICALLY_CONFLICTING"),
                ("VERIFIED", "VALID", "PHYSICALLY_CONSISTENT"),
            ]
        },
        "simultaneous_crypto_and_physical_conflict": {
            "states": [("CONFLICTING", "VALID", "PHYSICALLY_CONFLICTING")]
        },
        "revocation_only": {
            "states": [("VERIFIED", "REVOKED", "PHYSICALLY_CONSISTENT")]
        },
    }
    for item in illustrative_sequences.values():
        item["strict"] = [strict(*state) for state in item["states"]]
        item["corroborated"] = [corroborated(*state) for state in item["states"]]

    report = {
        "schema": "sam.phase36.fusion-policy-sensitivity.v1",
        "scope": "finite-state and optional Phase 34 replay comparison of two assurance policies",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "policies": {
            "strict_conflict_dominant": "any crypto conflict, revocation, or physical conflict yields CONFLICTING",
            "corroborated_conflict": "revocation remains dominant; otherwise crypto and physical must both conflict",
        },
        "finite_state": {
            "combinations": len(truth_rows),
            "strict_distribution": dict(sorted(strict_distribution.items())),
            "corroborated_distribution": dict(sorted(alternative_distribution.items())),
            "different_cases": sum(row["different"] for row in truth_rows),
            "rows": truth_rows,
        },
        "phase34_replay": replay,
        "illustrative_sequences": illustrative_sequences,
        "correctness": {
            "state_space_complete": len(truth_rows) == 48,
            "both_policies_verify_only_full_support": all(
                (row["strict_conflict_dominant"] == "VERIFIED") == (row["cryptographic"] == "VERIFIED" and row["trust"] == "VALID" and row["physical"] == "PHYSICALLY_CONSISTENT")
                and (row["corroborated_conflict"] == "VERIFIED") == (row["cryptographic"] == "VERIFIED" and row["trust"] == "VALID" and row["physical"] == "PHYSICALLY_CONSISTENT")
                for row in truth_rows
            ),
            "revocation_dominant_in_both": all(
                row["strict_conflict_dominant"] == "CONFLICTING" and row["corroborated_conflict"] == "CONFLICTING"
                for row in truth_rows if row["trust"] == "REVOKED"
            ),
            "alternative_changes_at_least_one_case": any(row["different"] for row in truth_rows),
        },
        "interpretation_limits": [
            "The corroborated-conflict policy is a sensitivity comparator, not a deployment recommendation.",
            "Reducing single-branch conflicts also delays or suppresses response to a genuine single-source compromise.",
            "No cost function or operational safety authority is used to select between policies.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

