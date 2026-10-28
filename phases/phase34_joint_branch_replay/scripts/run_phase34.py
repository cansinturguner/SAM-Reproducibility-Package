#!/usr/bin/env python3
"""Replay joint cryptographic, trust, and physical evidence states."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE27_SCRIPTS = REPO_ROOT / "phases" / "phase27_threshold_aware_integration" / "scripts"
sys.path.insert(0, str(PHASE27_SCRIPTS))
import threshold_core as core  # noqa: E402


SCENARIOS = (
    {
        "name": "S0_all_valid_reference",
        "crypto_conflict_rate": 0.0,
        "crypto_pending_rate": 0.0,
        "trust_revoked_rate": 0.0,
        "trust_stale_rate": 0.0,
    },
    {
        "name": "S1_crypto_conflict_1pct",
        "crypto_conflict_rate": 0.01,
        "crypto_pending_rate": 0.0,
        "trust_revoked_rate": 0.0,
        "trust_stale_rate": 0.0,
    },
    {
        "name": "S2_crypto_pending_10pct",
        "crypto_conflict_rate": 0.0,
        "crypto_pending_rate": 0.10,
        "trust_revoked_rate": 0.0,
        "trust_stale_rate": 0.0,
    },
    {
        "name": "S3_trust_revoked_1pct",
        "crypto_conflict_rate": 0.0,
        "crypto_pending_rate": 0.0,
        "trust_revoked_rate": 0.01,
        "trust_stale_rate": 0.0,
    },
    {
        "name": "S4_trust_stale_10pct",
        "crypto_conflict_rate": 0.0,
        "crypto_pending_rate": 0.0,
        "trust_revoked_rate": 0.0,
        "trust_stale_rate": 0.10,
    },
    {
        "name": "S5_joint_controlled_interaction",
        "crypto_conflict_rate": 0.01,
        "crypto_pending_rate": 0.10,
        "trust_revoked_rate": 0.01,
        "trust_stale_rate": 0.10,
    },
)


def unit_interval(message: bytes, scenario: str, dimension: str, seed: int) -> float:
    digest = hashlib.sha256(
        b"SAM-PHASE34|" + str(seed).encode() + b"|" + scenario.encode() + b"|" + dimension.encode() + b"|" + message
    ).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def evidence_states(message: bytes, scenario: dict, seed: int) -> tuple[str, str]:
    crypto_draw = unit_interval(message, scenario["name"], "crypto", seed)
    if crypto_draw < scenario["crypto_conflict_rate"]:
        crypto = "CONFLICTING"
    elif crypto_draw < scenario["crypto_conflict_rate"] + scenario["crypto_pending_rate"]:
        crypto = "PENDING"
    else:
        crypto = "VERIFIED"

    trust_draw = unit_interval(message, scenario["name"], "trust", seed)
    if trust_draw < scenario["trust_revoked_rate"]:
        trust = "REVOKED"
    elif trust_draw < scenario["trust_revoked_rate"] + scenario["trust_stale_rate"]:
        trust = "STALE"
    else:
        trust = "VALID"
    return crypto, trust


def physical_only(physical: str) -> str:
    if physical == core.PHYSICALLY_CONFLICTING:
        return "CONFLICTING"
    if physical == core.PHYSICALLY_CONSISTENT:
        return "VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def crypto_only(crypto: str) -> str:
    if crypto == "CONFLICTING":
        return "CONFLICTING"
    if crypto == "VERIFIED":
        return "VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def reason(crypto: str, trust: str, physical: str) -> str:
    reasons = []
    if crypto == "CONFLICTING":
        reasons.append("CRYPTOGRAPHIC_CONFLICT")
    if trust == "REVOKED":
        reasons.append("REVOKED_CREDENTIAL")
    if physical == core.PHYSICALLY_CONFLICTING:
        reasons.append("PHYSICAL_CONFLICT")
    if reasons:
        return "+".join(reasons)
    missing = []
    if crypto != "VERIFIED":
        missing.append(f"CRYPTO_{crypto}")
    if trust != "VALID":
        missing.append(f"TRUST_{trust}")
    if physical != core.PHYSICALLY_CONSISTENT:
        missing.append("PHYSICAL_UNAVAILABLE")
    return "+".join(missing) if missing else "ALL_REQUIRED_EVIDENCE_SUPPORTS"


def sorted_counts(counter: Counter) -> dict:
    return {key: counter[key] for key in sorted(counter)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--sensors", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--decision-model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    model = core.load_decision_model(args.decision_model)
    hashes = core.verify_model_inputs(
        model, args.selected, args.sensors, args.calibration, args.skip_hash_check
    )
    sensors = core.load_sensors(args.sensors)
    biases = core.load_biases(args.calibration)
    modeled = set(sensors) & set(biases)
    threshold_ns = float(model["threshold_ns"])

    scenario_counters = {
        scenario["name"]: {
            "crypto": Counter(),
            "trust": Counter(),
            "physical": Counter(),
            "full": Counter(),
            "physical_only": Counter(),
            "crypto_only": Counter(),
            "full_vs_physical_only": Counter(),
            "full_vs_crypto_only": Counter(),
            "reasons": Counter(),
            "combinations": Counter(),
        }
        for scenario in SCENARIOS
    }
    rows_read = test_rows = eligible_rows = 0

    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows_read += 1
            if row.get("split", "").strip().lower() != "test":
                continue
            test_rows += 1
            if not core.truthy(row.get("eligible_ge4")):
                continue
            eligible_rows += 1
            physical, _, _ = core.physical_decision(row, sensors, biases, modeled, threshold_ns)
            message = core.canonical_message(row)
            for scenario in SCENARIOS:
                crypto, trust = evidence_states(message, scenario, args.seed)
                full = core.fuse(crypto, trust, physical)
                p_only = physical_only(physical)
                c_only = crypto_only(crypto)
                counters = scenario_counters[scenario["name"]]
                counters["crypto"][crypto] += 1
                counters["trust"][trust] += 1
                counters["physical"][physical] += 1
                counters["full"][full] += 1
                counters["physical_only"][p_only] += 1
                counters["crypto_only"][c_only] += 1
                counters["full_vs_physical_only"][f"{p_only}->{full}"] += 1
                counters["full_vs_crypto_only"][f"{c_only}->{full}"] += 1
                counters["reasons"][reason(crypto, trust, physical)] += 1
                counters["combinations"][f"{crypto}|{trust}|{physical}"] += 1

    results = []
    for scenario in SCENARIOS:
        counters = scenario_counters[scenario["name"]]
        results.append(
            {
                "name": scenario["name"],
                "controlled_rates": {key: scenario[key] for key in scenario if key != "name"},
                "evidence_counts": {
                    "cryptographic": sorted_counts(counters["crypto"]),
                    "trust": sorted_counts(counters["trust"]),
                    "physical": sorted_counts(counters["physical"]),
                },
                "policy_outputs": {
                    "full_sam": sorted_counts(counters["full"]),
                    "physical_only": sorted_counts(counters["physical_only"]),
                    "cryptographic_only": sorted_counts(counters["crypto_only"]),
                },
                "decision_transitions": {
                    "physical_only_to_full_sam": sorted_counts(counters["full_vs_physical_only"]),
                    "cryptographic_only_to_full_sam": sorted_counts(counters["full_vs_crypto_only"]),
                },
                "full_sam_reason_counts": sorted_counts(counters["reasons"]),
                "evidence_combination_counts": sorted_counts(counters["combinations"]),
                "full_differs_from_physical_only": sum(
                    count for transition, count in counters["full_vs_physical_only"].items()
                    if transition.split("->")[0] != transition.split("->")[1]
                ),
                "full_differs_from_cryptographic_only": sum(
                    count for transition, count in counters["full_vs_crypto_only"].items()
                    if transition.split("->")[0] != transition.split("->")[1]
                ),
            }
        )

    reference = next(item for item in results if item["name"] == "S0_all_valid_reference")
    joint = next(item for item in results if item["name"] == "S5_joint_controlled_interaction")
    report = {
        "schema": "sam.phase34.joint-branch-replay.v1",
        "scope": "real LocaRDS physical evidence with deterministic controlled cryptographic and trust branch states",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "configuration": {
            "seed": args.seed,
            "physical_threshold_ns": threshold_ns,
            "scenario_count": len(SCENARIOS),
            "assignment": "SHA-256 observation-bound deterministic draws, independent of row order",
            "fusion_policy": "conflict dominates; full VERIFIED requires crypto VERIFIED, trust VALID, and physical CONSISTENT",
        },
        "inputs": {
            "sha256": hashes,
            "decision_model_sha256": core.sha256_file(args.decision_model),
        },
        "population": {
            "rows_read": rows_read,
            "test_rows": test_rows,
            "eligible_rows": eligible_rows,
        },
        "scenarios": results,
        "cross_scenario_checks": {
            "reference_full_equals_physical_only": reference["policy_outputs"]["full_sam"] == reference["policy_outputs"]["physical_only"],
            "joint_full_differs_from_physical_only": joint["full_differs_from_physical_only"] > 0,
            "joint_full_differs_from_crypto_only": joint["full_differs_from_cryptographic_only"] > 0,
            "every_scenario_preserves_population": all(
                sum(item["policy_outputs"]["full_sam"].values()) == eligible_rows for item in results
            ),
        },
        "runtime": {"wall_seconds": time.perf_counter() - started},
        "interpretation_limits": [
            "The physical branch uses real decoded LocaRDS observations; cryptographic and trust perturbations are controlled synthetic states.",
            "Scenario rates exercise branch interactions and are not estimates of operational event prevalence.",
            "This experiment evaluates assurance-state composition, not attack-class detection accuracy.",
            "LocaRDS does not contain SAM authenticators co-captured with the original RF broadcasts.",
            "The two LocaRDS partitions share the published receiver infrastructure.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

