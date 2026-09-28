#!/usr/bin/env python3
"""Reproducible TESLA delayed-authentication availability experiment."""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_FLOOR
import hashlib
import hmac
import json
import math
import os
import platform
import random
import resource
import statistics
import sys
import time
from pathlib import Path


KEY_BYTES = 16
TAG_BYTES = 16
SEQUENCE_BYTES = 1
MESSAGE_BYTES = 14


def chain_hash(value: bytes) -> bytes:
    return hashlib.sha3_256(b"SAM-PHASE9-CHAIN\x00" + value).digest()[:KEY_BYTES]


def authentication_key(interval_key: bytes) -> bytes:
    return hashlib.sha3_256(b"SAM-PHASE9-AUTH-KEY\x00" + interval_key).digest()


def build_chain(seed: int, intervals: int) -> list[bytes]:
    terminal = hashlib.sha3_256(f"SAM-PHASE9:{seed}".encode()).digest()[:KEY_BYTES]
    keys = [b""] * intervals
    keys[-1] = terminal
    for index in range(intervals - 2, -1, -1):
        keys[index] = chain_hash(keys[index + 1])
    return keys


def derive_earlier_key(later_key: bytes, steps: int) -> bytes:
    value = later_key
    for _ in range(steps):
        value = chain_hash(value)
    return value


def tag(interval_key: bytes, interval: int, sequence: int, payload: bytes) -> bytes:
    data = interval.to_bytes(4, "big") + sequence.to_bytes(1, "big") + payload
    return hmac.new(authentication_key(interval_key), data, hashlib.sha3_256).digest()[:TAG_BYTES]


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


def messages_per_interval(rate: float, intervals: int) -> list[int]:
    counts = []
    # Decimal prevents a workload such as 6.2 messages/s for 600 s from
    # becoming 3719 messages through binary floating-point accumulation.
    rate_decimal = Decimal(str(rate))
    cumulative = Decimal("0")
    emitted = 0
    for _ in range(intervals):
        cumulative += rate_decimal
        target = int(cumulative.to_integral_value(rounding=ROUND_FLOOR))
        counts.append(target - emitted)
        emitted = target
    return counts


def make_workload(seed: int, counts: list[int], keys: list[bytes]) -> list[list[tuple]]:
    rng = random.Random(seed)
    workload = []
    for interval, count in enumerate(counts):
        rows = []
        for sequence in range(count):
            payload = rng.randbytes(MESSAGE_BYTES)
            rows.append((sequence, payload, tag(keys[interval], interval, sequence, payload)))
        workload.append(rows)
    return workload


def simulate_once(
    workload: list[list[tuple]],
    keys: list[bytes],
    loss: float,
    interval_seconds: float,
    rng: random.Random,
) -> dict:
    received_messages: dict[int, list[tuple]] = {}
    received_disclosures: dict[int, bytes] = {}
    transmitted = sum(len(rows) for rows in workload)
    received = 0

    for interval, rows in enumerate(workload):
        kept = [row for row in rows if rng.random() >= loss]
        if kept:
            received_messages[interval] = kept
            received += len(kept)
        # Key K_i is disclosed as B1 in interval i+1. A final disclosure slot
        # after the workload is included so the last interval can authenticate.
        if rng.random() >= loss:
            received_disclosures[interval + 1] = keys[interval]

    authenticated = 0
    delays = []
    max_buffered = 0
    buffered = 0
    pending = {i: list(rows) for i, rows in received_messages.items()}

    for disclosure_time in range(1, len(workload) + 1):
        buffered += len(received_messages.get(disclosure_time - 1, []))
        max_buffered = max(max_buffered, buffered)
        if disclosure_time not in received_disclosures:
            continue
        disclosed_index = disclosure_time - 1
        disclosed_key = received_disclosures[disclosure_time]
        for interval in sorted(list(pending)):
            if interval > disclosed_index:
                continue
            recovered_key = derive_earlier_key(disclosed_key, disclosed_index - interval)
            verified_here = 0
            for sequence, payload, expected in pending[interval]:
                actual = tag(recovered_key, interval, sequence, payload)
                if hmac.compare_digest(actual, expected):
                    authenticated += 1
                    verified_here += 1
                    delays.append((disclosure_time - interval) * interval_seconds)
            buffered -= verified_here
            del pending[interval]

    return {
        "transmitted_messages": transmitted,
        "received_messages": received,
        "authenticated_messages": authenticated,
        "received_fraction": received / transmitted,
        "authentication_availability_vs_transmitted": authenticated / transmitted,
        "authentication_availability_vs_received": authenticated / received if received else 0.0,
        "delay_q50_seconds": percentile(delays, 0.5),
        "delay_q95_seconds": percentile(delays, 0.95),
        "maximum_buffered_messages": max_buffered,
        "unresolved_received_messages": received - authenticated,
    }


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--message-rate", type=float, default=6.2)
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--loss-probabilities", default="0,0.1,0.2,0.3,0.4,0.5")
    args = parser.parse_args()
    losses = [float(value) for value in args.loss_probabilities.split(",")]
    if args.interval_seconds <= 0 or args.duration_seconds <= 0 or args.message_rate <= 0:
        parser.error("duration, interval, and message rate must be positive")
    if args.replicates < 2 or any(value < 0 or value >= 1 for value in losses):
        parser.error("use at least two replicates and loss probabilities in [0,1)")

    intervals = math.ceil(args.duration_seconds / args.interval_seconds)
    counts = messages_per_interval(args.message_rate * args.interval_seconds, intervals)
    keys = build_chain(args.seed, intervals)
    workload = make_workload(args.seed + 1, counts, keys)

    # Deterministic protocol self-checks.
    chain_consistent = all(chain_hash(keys[i + 1]) == keys[i] for i in range(intervals - 1))
    sequence_valid = max(counts) <= 256
    sample = workload[0][0]
    sample_valid = hmac.compare_digest(sample[2], tag(keys[0], 0, sample[0], sample[1]))

    start = time.perf_counter()
    scenarios = []
    for loss_index, loss in enumerate(losses):
        results = []
        for replicate in range(args.replicates):
            scenario_seed = args.seed + 100_000 * loss_index + replicate
            results.append(
                simulate_once(workload, keys, loss, args.interval_seconds, random.Random(scenario_seed))
            )
        scenarios.append({
            "independent_type_a_and_b1_loss_probability": loss,
            "received_fraction": distribution([x["received_fraction"] for x in results]),
            "authentication_availability_vs_transmitted": distribution(
                [x["authentication_availability_vs_transmitted"] for x in results]
            ),
            "authentication_availability_vs_received": distribution(
                [x["authentication_availability_vs_received"] for x in results]
            ),
            "authentication_delay_q50_seconds": distribution(
                [x["delay_q50_seconds"] for x in results if x["delay_q50_seconds"] is not None]
            ),
            "authentication_delay_q95_seconds": distribution(
                [x["delay_q95_seconds"] for x in results if x["delay_q95_seconds"] is not None]
            ),
            "maximum_buffered_messages": distribution(
                [float(x["maximum_buffered_messages"]) for x in results]
            ),
            "unresolved_received_messages": distribution(
                [float(x["unresolved_received_messages"]) for x in results]
            ),
        })
    elapsed = time.perf_counter() - start

    report = {
        "schema": "sam.phase9.tesla-delayed-auth.v1",
        "scope": {
            "implemented": "TESLA key chain, one-interval delayed B1 disclosure, buffering and loss simulation",
            "not_implemented": [
                "Phase Overlay RF waveform, RS FEC or BER",
                "B2 signed-key and Type-C certificate scheduling",
                "trust-service or PKI availability",
                "complete SAM evidence fusion",
                "certified airborne hardware",
            ],
            "security_label": "No attack/anomaly dataset or classifier is used; loss is an availability stress variable.",
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": args.seed,
            "duration_seconds": args.duration_seconds,
            "interval_seconds": args.interval_seconds,
            "interval_count": intervals,
            "message_rate_per_second": args.message_rate,
            "transmitted_messages_per_replicate": sum(counts),
            "replicates_per_loss_probability": args.replicates,
            "key_bits": KEY_BYTES * 8,
            "hmac_algorithm": "HMAC-SHA3-256",
            "transmitted_tag_bits": TAG_BYTES * 8,
            "sequence_bits": SEQUENCE_BYTES * 8,
            "disclosure_delay_intervals": 1,
            "type_a_security_data_bytes_excluding_fec": TAG_BYTES + SEQUENCE_BYTES,
            "b1_interval_key_bytes_excluding_framing_and_fec": KEY_BYTES,
        },
        "correctness": {
            "key_chain_consistent": chain_consistent,
            "sequence_field_sufficient_for_configured_interval": sequence_valid,
            "sample_hmac_verified": sample_valid,
            "zero_loss_all_messages_authenticated": scenarios[0][
                "authentication_availability_vs_transmitted"
            ]["mean"] == 1.0 if losses and losses[0] == 0 else None,
        },
        "scenarios": scenarios,
        "benchmark": {
            "total_wall_seconds": elapsed,
            "simulated_message_instances": sum(counts) * args.replicates * len(losses),
            "peak_rss_mib": peak_rss_mib(),
        },
        "interpretation_limits": [
            "One-second intervals and HMAC-SHA3-256/128 are explicit experimental choices.",
            "Simulation intervals summarize Monte Carlo loss replicates; they are not confidence intervals for global ADS-B traffic.",
            "Loss is independent and conditional on the synthetic workload; burst loss and RF propagation are not modeled.",
            "Authentication delay is protocol buffering delay, not RF reception or certified avionics latency.",
            "Logical authenticator/key sizes exclude Phase Overlay framing, FEC, certificates and scheduling overhead.",
        ],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
