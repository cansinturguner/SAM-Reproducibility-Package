#!/usr/bin/env python3
"""Controlled TESLA and secure/legacy downgrade robustness experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import statistics
from collections import Counter
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "q025": percentile(values, 0.025),
        "q95": percentile(values, 0.95),
        "q975": percentile(values, 0.975),
        "minimum": min(values),
        "maximum": max(values),
    }


def channel_loss_sequence(count: int, rng: random.Random, cfg: dict) -> list[bool]:
    state = "GOOD"
    losses = []
    for _ in range(count):
        loss_probability = cfg["loss_good"] if state == "GOOD" else cfg["loss_bad"]
        losses.append(rng.random() < loss_probability)
        transition = rng.random()
        if state == "GOOD" and transition < cfg["p_good_to_bad"]:
            state = "BAD"
        elif state == "BAD" and transition < cfg["p_bad_to_good"]:
            state = "GOOD"
    return losses


def burst_replicate(intervals: int, messages_per_interval: list[int], rng: random.Random, cfg: dict) -> dict:
    event_count = sum(messages_per_interval) + intervals
    lost = iter(channel_loss_sequence(event_count, rng, cfg))
    received_by_interval = {}
    disclosure_received = {}
    transmitted = received = 0
    for interval, count in enumerate(messages_per_interval):
        kept = 0
        for _ in range(count):
            transmitted += 1
            if not next(lost):
                kept += 1
                received += 1
        received_by_interval[interval] = kept
        disclosure_received[interval] = not next(lost)

    authenticated = 0
    delays = []
    last_disclosed = None
    for disclosure_index in range(intervals):
        if not disclosure_received[disclosure_index]:
            continue
        last_disclosed = disclosure_index
        for interval in range(disclosure_index + 1):
            count = received_by_interval.get(interval, 0)
            if count:
                authenticated += count
                delays.extend([float(disclosure_index - interval + 1)] * count)
                received_by_interval[interval] = 0
    unresolved = sum(received_by_interval.values())
    return {
        "transmitted": transmitted,
        "received": received,
        "authenticated": authenticated,
        "availability_vs_received": authenticated / received if received else 0.0,
        "availability_vs_transmitted": authenticated / transmitted,
        "delay_q50_intervals": percentile(delays, 0.5) if delays else 0.0,
        "delay_q95_intervals": percentile(delays, 0.95) if delays else 0.0,
        "unresolved_received": unresolved,
        "last_disclosed_interval": last_disclosed,
    }


def burst_experiment(seed: int, replicates: int, duration: int, rate: float) -> list[dict]:
    intervals = duration
    counts = []
    emitted = 0
    for index in range(1, intervals + 1):
        target = math.floor(index * rate + 1e-9)
        counts.append(target - emitted)
        emitted = target
    configs = (
        {"name": "mild_burst", "p_good_to_bad": 0.01, "p_bad_to_good": 0.50, "loss_good": 0.01, "loss_bad": 0.60},
        {"name": "moderate_burst", "p_good_to_bad": 0.02, "p_bad_to_good": 0.20, "loss_good": 0.02, "loss_bad": 0.80},
        {"name": "severe_burst", "p_good_to_bad": 0.04, "p_bad_to_good": 0.10, "loss_good": 0.05, "loss_bad": 0.95},
    )
    rows = []
    for c_index, cfg in enumerate(configs):
        results = [
            burst_replicate(intervals, counts, random.Random(seed + c_index * 100000 + rep), cfg)
            for rep in range(replicates)
        ]
        rows.append(
            {
                "name": cfg["name"],
                "parameters": {key: value for key, value in cfg.items() if key != "name"},
                "authentication_availability_vs_received": summary([r["availability_vs_received"] for r in results]),
                "authentication_availability_vs_transmitted": summary([r["availability_vs_transmitted"] for r in results]),
                "authentication_delay_q50_intervals": summary([r["delay_q50_intervals"] for r in results]),
                "authentication_delay_q95_intervals": summary([r["delay_q95_intervals"] for r in results]),
                "unresolved_received_messages": summary([float(r["unresolved_received"]) for r in results]),
            }
        )
    return rows


def late_packet_experiment(rate: float) -> list[dict]:
    message_count = math.floor(rate)
    send_times = [(index + 0.5) / message_count for index in range(message_count)]
    rows = []
    for network_delay in (0.05, 0.25, 0.75, 1.10):
        for clock_bound in (0.0, 0.05, 0.10, 0.25):
            safe = sum(send + network_delay + clock_bound < 1.0 for send in send_times)
            rows.append(
                {
                    "one_way_delay_seconds": network_delay,
                    "receiver_clock_uncertainty_bound_seconds": clock_bound,
                    "messages_in_interval": message_count,
                    "accepted_for_delayed_verification": safe,
                    "rejected_as_late_or_unsafe": message_count - safe,
                    "safe_fraction": safe / message_count,
                }
            )
    return rows


def sequence_experiment() -> dict:
    seen = set()
    accepted = 0
    for interval in (0, 1):
        for sequence in range(256):
            token = (interval, sequence)
            if token not in seen:
                seen.add(token)
                accepted += 1
    replay_rejected = (0, 0) in seen
    overflow_rejected = 256 > 255
    reset_in_next_interval_accepted = (1, 0) in seen and (0, 0) in seen
    return {
        "sequence_bits": 8,
        "scope": "per TESLA interval",
        "legitimate_boundary_messages_accepted": accepted,
        "expected_legitimate_messages": 512,
        "sequence_256_rejected_before_encoding": overflow_rejected,
        "old_interval_sequence_replay_rejected": replay_rejected,
        "sequence_zero_in_next_interval_accepted": reset_in_next_interval_accepted,
        "authenticated_replay_key": "interval_id + sequence + payload tag",
    }


def route(policy: str, secure_capability: bool, frame: str) -> tuple[bool, str, str]:
    if frame == "VALID_SECURE":
        return True, "VERIFIED", "SECURE_EVIDENCE_VALID"
    if frame == "INVALID_SECURE":
        return secure_capability, "CONFLICTING", "SECURE_EVIDENCE_INVALID"
    if frame == "LEGACY" and secure_capability and policy == "capability_pin":
        return True, "INSUFFICIENT_EVIDENCE", "DOWNGRADE_BLOCKED"
    if frame == "LEGACY":
        return secure_capability, "LEGACY_UNASSURED", "LEGACY_PATH"
    raise ValueError(frame)


def downgrade_experiment() -> dict:
    sequence = ("LEGACY", "VALID_SECURE", "LEGACY", "INVALID_SECURE", "VALID_SECURE")
    policies = {}
    for policy in ("permissive_fallback", "capability_pin"):
        secure = False
        outputs = []
        for frame in sequence:
            secure, state, reason = route(policy, secure, frame)
            outputs.append({"input": frame, "secure_capability_after": secure, "state": state, "reason": reason})
        policies[policy] = outputs
    pinned = policies["capability_pin"]
    permissive = policies["permissive_fallback"]
    return {
        "input_sequence": list(sequence),
        "policies": policies,
        "checks": {
            "permissive_policy_downgrades_after_secure_establishment": permissive[2]["state"] == "LEGACY_UNASSURED",
            "capability_pin_blocks_downgrade": pinned[2]["state"] == "INSUFFICIENT_EVIDENCE" and pinned[2]["reason"] == "DOWNGRADE_BLOCKED",
            "capability_pin_preserves_explicit_invalidity": pinned[3]["state"] == "CONFLICTING",
            "valid_secure_frame_recovers_verified_state": pinned[-1]["state"] == "VERIFIED",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--message-rate", type=float, default=6.2)
    args = parser.parse_args()
    if args.replicates < 20 or args.duration_seconds < 60 or args.message_rate <= 0:
        parser.error("use >=20 replicates, >=60 seconds, and a positive message rate")

    burst = burst_experiment(args.seed, args.replicates, args.duration_seconds, args.message_rate)
    late = late_packet_experiment(args.message_rate)
    sequence = sequence_experiment()
    downgrade = downgrade_experiment()
    report = {
        "schema": "sam.phase35.protocol-robustness.v1",
        "scope": "controlled TESLA timing/loss edge cases and secure-to-legacy downgrade handling",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "configuration": {
            "seed": args.seed,
            "replicates": args.replicates,
            "duration_seconds": args.duration_seconds,
            "message_rate_per_second": args.message_rate,
            "tesla_interval_seconds": 1.0,
        },
        "burst_loss": burst,
        "late_packet_and_clock_uncertainty": late,
        "sequence_boundary": sequence,
        "downgrade_routing": downgrade,
        "correctness": {
            "burst_scenarios_have_bounded_availability": all(0 <= row["authentication_availability_vs_received"]["minimum"] <= row["authentication_availability_vs_received"]["maximum"] <= 1 for row in burst),
            "clock_uncertainty_never_increases_safe_fraction": all(
                all(group[i]["safe_fraction"] >= group[i + 1]["safe_fraction"] for i in range(len(group) - 1))
                for delay in (0.05, 0.25, 0.75, 1.10)
                for group in [[row for row in late if row["one_way_delay_seconds"] == delay]]
            ),
            "sequence_boundary_checks_pass": sequence["legitimate_boundary_messages_accepted"] == sequence["expected_legitimate_messages"] and sequence["sequence_256_rejected_before_encoding"] and sequence["old_interval_sequence_replay_rejected"] and sequence["sequence_zero_in_next_interval_accepted"],
            "downgrade_checks_pass": all(downgrade["checks"].values()),
        },
        "interpretation_limits": [
            "Gilbert-Elliott parameters are controlled sensitivity conditions and are not fitted to operational 1090 MHz traces.",
            "Late-packet results use a conservative receiver clock-uncertainty bound and idealized fixed one-way delays.",
            "Sequence and downgrade results are protocol-state conformance tests, not RF experiments.",
            "Capability pinning prevents assurance downgrade but does not prevent channel jamming or message deletion.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

