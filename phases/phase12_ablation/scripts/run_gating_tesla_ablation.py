#!/usr/bin/env python3
"""Paired A4 gating and A5 TESLA key-chain recovery ablation."""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import platform
import random
import resource
import statistics
import sys
import time
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_record(path: str) -> dict:
    data = Path(path).read_bytes()
    return {"path": path, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def distribution(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "simulation_interval_95_low": percentile(values, 0.025),
        "simulation_interval_95_high": percentile(values, 0.975),
    }


def counts_per_interval(rate_per_interval: float, intervals: int) -> list[int]:
    rate = Decimal(str(rate_per_interval))
    cumulative = Decimal("0")
    emitted = 0
    result = []
    for _ in range(intervals):
        cumulative += rate
        target = int(cumulative.to_integral_value(rounding=ROUND_FLOOR))
        result.append(target - emitted)
        emitted = target
    return result


def make_receipt_realization(
    counts: list[int], loss: float, rng: random.Random
) -> tuple[list[int], list[bool]]:
    received_counts = []
    disclosures = []
    for count in counts:
        received_counts.append(sum(rng.random() >= loss for _ in range(count)))
        disclosures.append(rng.random() >= loss)
    return received_counts, disclosures


def evaluate_mode(
    received_counts: list[int], disclosures: list[bool], recovery: bool
) -> dict:
    intervals = len(received_counts)
    authenticated = 0
    delays: list[float] = []
    release_at: dict[int, int] = {}

    next_received: int | None = None
    earliest_from = [None] * intervals
    for index in range(intervals - 1, -1, -1):
        if disclosures[index]:
            next_received = index
        earliest_from[index] = next_received

    for interval, count in enumerate(received_counts):
        disclosure_index = earliest_from[interval] if recovery else (
            interval if disclosures[interval] else None
        )
        if disclosure_index is None:
            continue
        authenticated += count
        disclosure_time = disclosure_index + 1
        release_at[disclosure_time] = release_at.get(disclosure_time, 0) + count
        delays.extend([float(disclosure_time - interval)] * count)

    buffered = 0
    maximum_buffered = 0
    for current_time in range(1, intervals + 1):
        buffered += received_counts[current_time - 1]
        maximum_buffered = max(maximum_buffered, buffered)
        buffered -= release_at.get(current_time, 0)

    received = sum(received_counts)
    return {
        "received_messages": received,
        "authenticated_messages": authenticated,
        "authentication_availability_vs_received": authenticated / received if received else 0.0,
        "authentication_delay_q50_seconds": percentile(delays, 0.5),
        "authentication_delay_q95_seconds": percentile(delays, 0.95),
        "maximum_buffered_messages": maximum_buffered,
        "unresolved_received_messages": received - authenticated,
    }


def summarize_runs(runs: list[dict]) -> dict:
    return {
        "authentication_availability_vs_received": distribution(
            [x["authentication_availability_vs_received"] for x in runs]
        ),
        "authentication_delay_q50_seconds": distribution(
            [x["authentication_delay_q50_seconds"] for x in runs if x["authentication_delay_q50_seconds"] is not None]
        ),
        "authentication_delay_q95_seconds": distribution(
            [x["authentication_delay_q95_seconds"] for x in runs if x["authentication_delay_q95_seconds"] is not None]
        ),
        "maximum_buffered_messages": distribution(
            [float(x["maximum_buffered_messages"]) for x in runs]
        ),
        "unresolved_received_messages": distribution(
            [float(x["unresolved_received_messages"]) for x in runs]
        ),
    }


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase5d", required=True)
    parser.add_argument("--phase9", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    p5 = load(args.phase5d)
    p9 = load(args.phase9)
    assert p9["schema"] == "sam.phase9.tesla-delayed-auth.v1"
    assert p9["configuration"]["transmitted_messages_per_replicate"] == 3720
    original = p5["counts"]["test_original_ge4_rows"]
    usable = p5["counts"]["usable_test_rows"]
    unsupported = original - usable

    config = p9["configuration"]
    intervals = config["interval_count"]
    rate_per_interval = config["message_rate_per_second"] * config["interval_seconds"]
    counts = counts_per_interval(rate_per_interval, intervals)
    assert sum(counts) == config["transmitted_messages_per_replicate"]

    start = time.perf_counter()
    scenarios = []
    max_reproduction_error = 0.0
    for loss_index, phase9_scenario in enumerate(p9["scenarios"]):
        loss = phase9_scenario["independent_type_a_and_b1_loss_probability"]
        direct_runs = []
        recovery_runs = []
        paired_availability_deltas = []
        paired_unresolved_reductions = []
        for replicate in range(config["replicates_per_loss_probability"]):
            rng = random.Random(config["seed"] + 100_000 * loss_index + replicate)
            received_counts, disclosures = make_receipt_realization(counts, loss, rng)
            direct = evaluate_mode(received_counts, disclosures, recovery=False)
            recovered = evaluate_mode(received_counts, disclosures, recovery=True)
            direct_runs.append(direct)
            recovery_runs.append(recovered)
            paired_availability_deltas.append(
                recovered["authentication_availability_vs_received"]
                - direct["authentication_availability_vs_received"]
            )
            paired_unresolved_reductions.append(
                float(direct["unresolved_received_messages"] - recovered["unresolved_received_messages"])
            )
        direct_summary = summarize_runs(direct_runs)
        recovery_summary = summarize_runs(recovery_runs)
        reference = phase9_scenario["authentication_availability_vs_received"]["mean"]
        reproduction_error = abs(
            recovery_summary["authentication_availability_vs_received"]["mean"] - reference
        )
        max_reproduction_error = max(max_reproduction_error, reproduction_error)
        scenarios.append({
            "independent_type_a_and_b1_loss_probability": loss,
            "direct_b1_only": direct_summary,
            "tesla_chain_recovery": recovery_summary,
            "paired_chain_minus_direct_availability": distribution(paired_availability_deltas),
            "paired_unresolved_message_reduction": distribution(paired_unresolved_reductions),
            "phase9_chain_availability_reference": reference,
            "phase9_reproduction_absolute_error": reproduction_error,
        })
    elapsed = time.perf_counter() - start

    report = {
        "schema": "sam.phase12.gating-tesla-ablation.v1",
        "scope": {
            "implemented": "A4 receiver/geometry gating summary and paired A5 TESLA recovery ablation",
            "not_implemented": [
                "raw-IQ overlap recovery",
                "channel anomaly/change detection",
                "physical residuals for unsupported receiver geometries",
                "certified airborne buffering policy",
            ],
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "inputs": {"phase5d": file_record(args.phase5d), "phase9": file_record(args.phase9)},
        "A4_receiver_geometry_gating": {
            "real_locards_test_original_ge4_rows": original,
            "rows_supported_by_frozen_modeled_receiver_and_rank_rule": usable,
            "rows_without_sufficient_frozen_physical_support": unsupported,
            "supported_fraction": usable / original,
            "unsupported_fraction": unsupported / original,
            "without_gate_nominal_admission_fraction": 1.0,
            "interpretation": "Removing the gate would admit unsupported rows; no physical-verification result is assigned to them.",
        },
        "A5_tesla_chain_recovery": {
            "paired_design": "Identical Type-A and B1 loss draws for direct-only and chain-recovery modes",
            "replicates_per_loss_probability": config["replicates_per_loss_probability"],
            "no_timeout_policy": True,
            "scenarios": scenarios,
            "maximum_phase9_reproduction_absolute_error": max_reproduction_error,
        },
        "benchmark": {"wall_seconds": elapsed, "peak_rss_mib": peak_rss_mib()},
        "interpretation_limits": [
            "A4 uses real frozen LocaRDS counts and does not classify unsupported rows.",
            "A5 uses the Phase 9 deterministic synthetic loss workload.",
            "Simulation intervals summarize replicates and are not global traffic confidence intervals.",
            "Direct-only unresolved messages remain buffered because no arbitrary timeout is modeled.",
            "No attack/anomaly labels or detection metrics are produced.",
        ],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

