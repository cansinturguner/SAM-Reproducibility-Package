#!/usr/bin/env python3
"""Validate deterministic SAM evidence fusion using frozen prior reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import statistics
import sys
import time
from pathlib import Path


VERIFIED = "VERIFIED"
CONFLICTING = "CONFLICTING"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
LEGACY = "LEGACY_UNASSURED"
NOT_EVALUATED = "NOT_EVALUATED"


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_record(path: str) -> dict:
    content = Path(path).read_bytes()
    return {
        "path": path,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "q05": percentile(values, 0.05),
        "q95": percentile(values, 0.95),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def fuse(
    crypto: str,
    physical: str,
    trust: str,
    *,
    crypto_enabled: bool = True,
    physical_enabled: bool = True,
    require_multiple_families: bool = True,
    legacy_only: bool = False,
) -> str:
    if legacy_only:
        return LEGACY
    enabled = []
    if crypto_enabled:
        enabled.append(crypto)
        enabled.append(trust)
    if physical_enabled:
        enabled.append(physical)
    if CONFLICTING in enabled:
        return CONFLICTING
    positive_crypto = crypto_enabled and crypto == VERIFIED and trust == VERIFIED
    positive_physical = physical_enabled and physical == VERIFIED
    if require_multiple_families:
        return VERIFIED if positive_crypto and positive_physical else INSUFFICIENT
    return VERIFIED if positive_crypto or positive_physical else INSUFFICIENT


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase5d", required=True)
    parser.add_argument("--phase8", required=True)
    parser.add_argument("--phase9", required=True)
    parser.add_argument("--phase10", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if args.iterations < 1000 or args.repetitions < 2:
        parser.error("use at least 1000 iterations and two repetitions")

    p5 = load(args.phase5d)
    p8 = load(args.phase8)
    p9 = load(args.phase9)
    p10 = load(args.phase10)

    assert p8["schema"] == "sam.phase8.crypto-benchmark.v1"
    assert p9["schema"] == "sam.phase9.tesla-delayed-auth.v1"
    assert p10["schema"] == "sam.phase10.identity-trust.v1"
    assert p5["frozen_configuration"]["clock_model"] == "bias_only"
    assert p5["frozen_configuration"]["minimum_modeled_receivers"] == 4
    assert all(p8["correctness"].values())
    assert all(p9["correctness"].values())
    assert all(p10["correctness"].values())

    cases = [
        ("all_evidence_valid", VERIFIED, VERIFIED, VERIFIED, VERIFIED),
        ("physical_missing", VERIFIED, INSUFFICIENT, VERIFIED, INSUFFICIENT),
        ("crypto_missing", INSUFFICIENT, VERIFIED, VERIFIED, INSUFFICIENT),
        ("trust_missing", VERIFIED, VERIFIED, INSUFFICIENT, INSUFFICIENT),
        ("physical_conflict", VERIFIED, CONFLICTING, VERIFIED, CONFLICTING),
        ("crypto_conflict", CONFLICTING, VERIFIED, VERIFIED, CONFLICTING),
        ("trust_conflict", VERIFIED, VERIFIED, CONFLICTING, CONFLICTING),
        ("all_evidence_missing", INSUFFICIENT, INSUFFICIENT, INSUFFICIENT, INSUFFICIENT),
    ]
    truth_table = []
    for name, crypto, physical, trust, expected in cases:
        actual = fuse(crypto, physical, trust)
        truth_table.append({
            "case": name,
            "crypto": crypto,
            "physical": physical,
            "trust": trust,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        })

    ablations = [
        {
            "id": "A0",
            "name": "Legacy baseline",
            "evaluation_status": "EVALUATED_RULE",
            "output_for_valid_input": fuse(VERIFIED, VERIFIED, VERIFIED, legacy_only=True),
            "interpretation": "No authentication or independent assurance claim.",
        },
        {
            "id": "A1",
            "name": "Full implemented SAM branches",
            "evaluation_status": "EVALUATED_RULE",
            "output_for_valid_input": fuse(VERIFIED, VERIFIED, VERIFIED),
            "interpretation": "Cryptographic, trust and physical evidence are jointly required.",
        },
        {
            "id": "A2",
            "name": "No cryptographic branch",
            "evaluation_status": "EVALUATED_RULE",
            "output_for_valid_input": fuse(
                INSUFFICIENT, VERIFIED, INSUFFICIENT, crypto_enabled=False
            ),
            "interpretation": "Physical corroboration alone cannot establish sender identity.",
        },
        {
            "id": "A3",
            "name": "No physical branch",
            "evaluation_status": "EVALUATED_RULE",
            "output_for_valid_input": fuse(
                VERIFIED, INSUFFICIENT, VERIFIED, physical_enabled=False
            ),
            "interpretation": "A valid signature alone does not independently corroborate reported state.",
        },
        {
            "id": "A4",
            "name": "No channel-quality assessment",
            "evaluation_status": NOT_EVALUATED,
            "output_for_valid_input": NOT_EVALUATED,
            "interpretation": "Channel-quality component is not implemented; no result is claimed.",
        },
        {
            "id": "A5",
            "name": "No overlap recovery",
            "evaluation_status": NOT_EVALUATED,
            "output_for_valid_input": NOT_EVALUATED,
            "interpretation": "Overlap-recovery component is not implemented; no result is claimed.",
        },
        {
            "id": "A6",
            "name": "Trust service unavailable",
            "evaluation_status": "EVALUATED_RULE",
            "valid_cache_output": fuse(VERIFIED, VERIFIED, VERIFIED),
            "cold_or_expired_cache_output": fuse(VERIFIED, VERIFIED, INSUFFICIENT),
            "interpretation": "Valid cache is fail-operational; missing/stale trust evidence degrades safely.",
        },
        {
            "id": "A7",
            "name": "Single-source decision",
            "evaluation_status": "EVALUATED_POLICY_VARIANT",
            "crypto_only_output": fuse(
                VERIFIED, INSUFFICIENT, VERIFIED,
                physical_enabled=False, require_multiple_families=False,
            ),
            "physical_only_output": fuse(
                INSUFFICIENT, VERIFIED, INSUFFICIENT,
                crypto_enabled=False, require_multiple_families=False,
            ),
            "interpretation": "This relaxed policy verifies with one family and is not the full-SAM policy.",
        },
    ]

    workload = [(c, p, t) for _, c, p, t, _ in cases]
    timings = []
    for _ in range(args.repetitions):
        start = time.perf_counter_ns()
        for index in range(args.iterations):
            c, p, t = workload[index % len(workload)]
            fuse(c, p, t)
        timings.append((time.perf_counter_ns() - start) / 1_000.0 / args.iterations)

    p10_states = {x["name"]: x["assurance_state"] for x in p10["trust_service_scenarios"]}
    report = {
        "schema": "sam.phase11.evidence-fusion.v1",
        "scope": {
            "implemented": "deterministic evidence fusion and partial A0-A7 rule evaluation",
            "not_implemented": [
                "message-level joining of LocaRDS and cryptographic observations",
                "channel-quality component for A4",
                "overlap-recovery component for A5",
                "attack/anomaly classifier",
                "certified airborne implementation",
            ],
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "configuration": {
            "iterations": args.iterations,
            "repetitions": args.repetitions,
            "full_policy": "VERIFIED requires crypto+trust and physical corroboration; any conflict dominates",
        },
        "input_reports": {
            "phase5d": file_record(args.phase5d),
            "phase8": file_record(args.phase8),
            "phase9": file_record(args.phase9),
            "phase10": file_record(args.phase10),
        },
        "source_evidence_summary": {
            "phase5d_real_locards": {
                "usable_test_rows": p5["counts"]["usable_test_rows"],
                "availability": p5["availability"]["fraction"],
                "pair_residual_absolute_q50_ns": p5["pair_residuals"]["absolute_q50_ns"],
                "pair_residual_absolute_q95_ns": p5["pair_residuals"]["absolute_q95_ns"],
            },
            "phase8_synthetic_crypto": {
                "all_correctness_checks_passed": all(p8["correctness"].values()),
                "hmac_verification_median_us": p8["timing_microseconds_per_message"]["hmac_verification"]["median"],
                "ecdsa_verification_median_us": p8["timing_microseconds_per_message"]["ecdsa_verification"]["median"],
            },
            "phase9_synthetic_tesla": {
                "messages_per_replicate": p9["configuration"]["transmitted_messages_per_replicate"],
                "zero_loss_authenticated_vs_received": p9["scenarios"][0]["authentication_availability_vs_received"]["mean"],
                "highest_loss_authenticated_vs_received": p9["scenarios"][-1]["authentication_availability_vs_received"]["mean"],
            },
            "phase10_synthetic_identity_trust": {
                "all_correctness_checks_passed": all(p10["correctness"].values()),
                "trust_states": p10_states,
            },
        },
        "fusion_truth_table": truth_table,
        "fusion_truth_table_pass_fraction": sum(x["passed"] for x in truth_table) / len(truth_table),
        "component_wise_A0_A7": ablations,
        "decision_time_microseconds": summary(timings),
        "peak_rss_mib": peak_rss_mib(),
        "interpretation_limits": [
            "Phase 5D is real LocaRDS evidence; Phases 8-10 are synthetic protocol workloads.",
            "Fusion validates decision rules across evidence summaries, not co-observed per-message evidence.",
            "A4 and A5 are deliberately NOT_EVALUATED until their components are implemented.",
            "A0-A3/A6-A7 outputs are controlled rule outcomes, not detection-accuracy measurements.",
            "No precision, recall, F1, false-positive or false-negative result is produced.",
        ],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

