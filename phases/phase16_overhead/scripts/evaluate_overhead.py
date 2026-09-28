#!/usr/bin/env python3
"""Deterministic logical communication-cost accounting for SAM."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import sys
from pathlib import Path

MESSAGE_BYTES = 14
TYPE_A_BYTES = 17
B1_BYTES = 16
B2_BYTES = 80
CA_RECORD_BYTES = 97


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def parse_numbers(text: str, cast):
    values = [cast(x) for x in text.split(",")]
    if not values or any(x <= 0 for x in values):
        raise argparse.ArgumentTypeError("all list values must be positive")
    return values


def exact_messages(rate: float, duration: int) -> int:
    return int(math.floor(rate * duration + 1e-9))


def evaluate(rate: float, aircraft: int, duration: int, policy: dict, b2_period: int) -> dict:
    messages_per_aircraft = exact_messages(rate, duration)
    intervals = math.ceil(duration / policy["interval_seconds"])
    b2_events = math.ceil(duration / b2_period)
    type_a = messages_per_aircraft * TYPE_A_BYTES
    b1 = intervals * policy["b1_repetitions"] * B1_BYTES
    b2 = b2_events * policy["b2_repetitions"] * B2_BYTES
    security_per_aircraft = type_a + b1 + b2
    surveillance_per_aircraft = messages_per_aircraft * MESSAGE_BYTES
    return {
        "policy": policy["name"],
        "message_rate_per_second": rate,
        "aircraft_count": aircraft,
        "messages_per_aircraft": messages_per_aircraft,
        "logical_security_bytes_per_aircraft": security_per_aircraft,
        "logical_security_bytes_per_message": security_per_aircraft / messages_per_aircraft,
        "logical_security_to_14byte_message_percent": 100.0 * security_per_aircraft / surveillance_per_aircraft,
        "aggregate_logical_security_kbit_per_second": security_per_aircraft * aircraft * 8.0 / duration / 1000.0,
        "breakdown_bytes_per_aircraft": {"type_a": type_a, "b1": b1, "b2": b2},
        "trust_lookup_bytes_per_aircraft_excluded_from_broadcast_stream": CA_RECORD_BYTES,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--seed", type=int, default=1103)
    ap.add_argument("--duration-seconds", type=int, default=3600)
    ap.add_argument("--message-rates", default="2,6.2,10")
    ap.add_argument("--aircraft-counts", default="1,50,200")
    ap.add_argument("--b2-period-seconds", type=int, default=60)
    a = ap.parse_args()
    if a.duration_seconds <= 0 or a.b2_period_seconds <= 0:
        ap.error("duration and B2 period must be positive")
    rates = parse_numbers(a.message_rates, float)
    aircraft_counts = parse_numbers(a.aircraft_counts, int)
    policies = [
        {"name": "P1_1s_single", "interval_seconds": 1, "b1_repetitions": 1, "b2_repetitions": 1},
        {"name": "P2_1s_double", "interval_seconds": 1, "b1_repetitions": 2, "b2_repetitions": 2},
        {"name": "P3_2s_double", "interval_seconds": 2, "b1_repetitions": 2, "b2_repetitions": 2},
        {"name": "P4_5s_triple", "interval_seconds": 5, "b1_repetitions": 3, "b2_repetitions": 3},
    ]
    scenarios = [evaluate(r, n, a.duration_seconds, p, a.b2_period_seconds)
                 for p in policies for r in rates for n in aircraft_counts]
    canonical = next(x for x in scenarios if x["policy"] == "P1_1s_single" and x["message_rate_per_second"] == 6.2 and x["aircraft_count"] == 1)
    encoded = json.dumps(scenarios, sort_keys=True, separators=(",", ":")).encode()
    report = {
        "schema": "sam.phase16.communication-overhead.v1",
        "scope": {
            "implemented": "deterministic logical-byte and aggregate-bit-rate accounting over a scheduling sensitivity matrix",
            "not_implemented": [
                "DO-260C/ED-102B bit-level mapping",
                "Phase Overlay RF framing or modulation",
                "FEC, BER or RF channel occupancy",
                "operational aircraft-density trace",
                "certificate traffic beyond the compact prototype",
                "ledger consensus or ledger writes",
            ],
            "security_label": "No attack/anomaly dataset or classifier is used.",
        },
        "platform": {
            "system": platform.system(), "release": platform.release(), "machine": platform.machine(),
            "processor": platform.processor(), "python": platform.python_version(), "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed_recorded_for_cross_phase_reproducibility": a.seed,
            "duration_seconds": a.duration_seconds,
            "message_rates_per_second": rates,
            "aircraft_counts": aircraft_counts,
            "b2_period_seconds": a.b2_period_seconds,
            "logical_object_bytes": {"surveillance_message_comparator": MESSAGE_BYTES, "type_a": TYPE_A_BYTES, "b1": B1_BYTES, "b2": B2_BYTES, "compact_ca_record": CA_RECORD_BYTES},
            "policies": policies,
        },
        "correctness": {
            "scenario_count": len(scenarios),
            "all_breakdowns_sum": all(sum(x["breakdown_bytes_per_aircraft"].values()) == x["logical_security_bytes_per_aircraft"] for x in scenarios),
            "aircraft_scaling_does_not_change_per_aircraft_cost": all(
                len({x["logical_security_bytes_per_aircraft"] for x in scenarios if x["policy"] == p["name"] and x["message_rate_per_second"] == r}) == 1
                for p in policies for r in rates
            ),
            "scenario_sha256": hashlib.sha256(encoded).hexdigest(),
        },
        "canonical_configuration": canonical,
        "scenarios": scenarios,
        "peak_rss_mib": peak_rss_mib(),
        "interpretation_limits": [
            "Results are exact logical-byte accounting, not measured RF traffic or channel occupancy.",
            "The 14-byte message is only a comparison denominator; security objects are not asserted to fit inside that message.",
            "Aggregate rates scale a constant per-aircraft schedule and are not derived from an operational density trace.",
            "The compact CA record is reported separately because trust lookup traffic is not part of the broadcast security stream.",
            "No precision, recall, F1, false-positive or false-negative result is produced.",
        ],
    }
    out = Path(a.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

