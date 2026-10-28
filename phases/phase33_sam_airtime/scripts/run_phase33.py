#!/usr/bin/env python3
"""Analytical SAM reference-transport and airtime accounting."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path


TYPE_A_BYTES = 17
B1_BYTES = 16
B2_BYTES = 80
OVERLAY_USABLE_BITS = 204
CARRIER_AIRTIME_US = 120.0


POLICIES = (
    {"name": "P1_1s_single", "interval_seconds": 1, "b1_repetitions": 1, "b2_repetitions": 1},
    {"name": "P2_1s_double", "interval_seconds": 1, "b1_repetitions": 2, "b2_repetitions": 2},
    {"name": "P3_2s_double", "interval_seconds": 2, "b1_repetitions": 2, "b2_repetitions": 2},
    {"name": "P4_5s_triple", "interval_seconds": 5, "b1_repetitions": 3, "b2_repetitions": 3},
)


def positive_csv(text: str, cast):
    values = [cast(item) for item in text.split(",")]
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("all values must be positive")
    return values


def frames_for(byte_count: int) -> int:
    return math.ceil(byte_count * 8 / OVERLAY_USABLE_BITS)


def sam_scenario(rate: float, aircraft: int, duration: int, b2_period: int, policy: dict) -> dict:
    messages = math.floor(rate * duration + 1e-9)
    intervals = math.ceil(duration / policy["interval_seconds"])
    b1_objects = intervals * policy["b1_repetitions"]
    b2_objects = math.ceil(duration / b2_period) * policy["b2_repetitions"]
    b1_frames = b1_objects * frames_for(B1_BYTES)
    b2_frames = b2_objects * frames_for(B2_BYTES)
    added_frames = b1_frames + b2_frames
    baseline_airtime_us = messages * CARRIER_AIRTIME_US
    added_airtime_us = added_frames * CARRIER_AIRTIME_US
    transmitted_frames = messages + added_frames
    security_bits = messages * TYPE_A_BYTES * 8 + b1_objects * B1_BYTES * 8 + b2_objects * B2_BYTES * 8
    overlay_capacity_bits = transmitted_frames * OVERLAY_USABLE_BITS
    return {
        "policy": policy["name"],
        "message_rate_per_second": rate,
        "aircraft_count": aircraft,
        "duration_seconds": duration,
        "per_aircraft": {
            "surveillance_frames": messages,
            "type_a_objects_overlaid_on_surveillance_frames": messages,
            "b1_objects": b1_objects,
            "b2_objects": b2_objects,
            "b1_additional_frames": b1_frames,
            "b2_additional_frames": b2_frames,
            "total_additional_frames": added_frames,
            "additional_packet_fraction_vs_surveillance": added_frames / messages,
            "baseline_surveillance_airtime_microseconds": baseline_airtime_us,
            "added_airtime_microseconds": added_airtime_us,
            "analytical_added_airtime_fraction_vs_surveillance": added_airtime_us / baseline_airtime_us,
            "analytical_added_airtime_percent_vs_surveillance": 100.0 * added_airtime_us / baseline_airtime_us,
            "security_bits": security_bits,
            "overlay_capacity_bits_after_fragmentation": overlay_capacity_bits,
            "overlay_payload_utilization_fraction": security_bits / overlay_capacity_bits,
        },
        "aggregate": {
            "additional_frames": added_frames * aircraft,
            "added_airtime_seconds_over_horizon": added_airtime_us * aircraft / 1e6,
            "mean_added_channel_occupancy_fraction": added_airtime_us * aircraft / (duration * 1e6),
            "mean_added_channel_occupancy_percent": 100.0 * added_airtime_us * aircraft / (duration * 1e6),
        },
    }


def cabba_scenario4(rate: float, duration: int) -> dict:
    messages = math.floor(rate * duration + 1e-9)
    workload_duration = messages / rate
    boundaries = math.ceil(workload_duration / 5.0)
    b2 = math.floor(workload_duration / 15.0) + 1
    b1 = max(0, boundaries - b2)
    certificates = math.floor(workload_duration / 30.0) + 1
    added = b1 * 120.0 + b2 * 218.0 + certificates * 250.0
    baseline = messages * 120.0
    return {
        "name": "CABBA_Scenario_4_recomputed",
        "message_rate_per_second": rate,
        "duration_seconds": duration,
        "type_a_messages": messages,
        "type_b1_packets": b1,
        "type_b2_packets": b2,
        "type_c_packets": certificates,
        "analytical_added_airtime_fraction_vs_legacy_A": added / baseline,
        "analytical_added_airtime_percent_vs_legacy_A": 100.0 * added / baseline,
        "boundary": "Phase 23 equations and packet durations; functions and schedules differ from SAM",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--message-rates", default="2,6.2,10")
    parser.add_argument("--aircraft-counts", default="1,50,200")
    parser.add_argument("--b2-period-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.b2_period_seconds <= 0:
        parser.error("duration and B2 period must be positive")
    rates = positive_csv(args.message_rates, float)
    aircraft_counts = positive_csv(args.aircraft_counts, int)

    scenarios = [
        sam_scenario(rate, aircraft, args.duration_seconds, args.b2_period_seconds, policy)
        for policy in POLICIES
        for rate in rates
        for aircraft in aircraft_counts
    ]
    canonical = next(
        row for row in scenarios
        if row["policy"] == "P1_1s_single"
        and row["message_rate_per_second"] == 6.2
        and row["aircraft_count"] == 200
    )
    serialized = json.dumps(scenarios, sort_keys=True, separators=(",", ":")).encode()
    report = {
        "schema": "sam.phase33.reference-transport-airtime.v1",
        "scope": "analytical airtime under one explicit SAM reference transport",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "reference_transport": {
            "carrier": "legacy-readable 1090ES-length carrier with modeled PPM/D8PSK phase overlay",
            "carrier_airtime_microseconds": CARRIER_AIRTIME_US,
            "usable_overlay_bits_per_frame": OVERLAY_USABLE_BITS,
            "object_bytes": {"type_a": TYPE_A_BYTES, "b1": B1_BYTES, "b2": B2_BYTES},
            "frames_per_object": {
                "type_a": frames_for(TYPE_A_BYTES),
                "b1": frames_for(B1_BYTES),
                "b2": frames_for(B2_BYTES),
            },
            "mapping": {
                "type_a": "overlaid on its existing surveillance frame",
                "b1": "fragmented into additional security-bearing carrier frames",
                "b2": "fragmented into additional security-bearing carrier frames",
            },
        },
        "configuration": {
            "duration_seconds": args.duration_seconds,
            "message_rates_per_second": rates,
            "aircraft_counts": aircraft_counts,
            "b2_period_seconds": args.b2_period_seconds,
            "policies": list(POLICIES),
            "scenario_count": len(scenarios),
        },
        "canonical_configuration": canonical,
        "cabba_scenario4_comparator": cabba_scenario4(6.2, args.duration_seconds),
        "correctness": {
            "scenario_sha256": hashlib.sha256(serialized).hexdigest(),
            "type_a_fits_one_overlay_frame": TYPE_A_BYTES * 8 <= OVERLAY_USABLE_BITS,
            "b1_fits_one_overlay_frame": B1_BYTES * 8 <= OVERLAY_USABLE_BITS,
            "b2_requires_four_overlay_frames": frames_for(B2_BYTES) == 4,
            "airtime_fraction_equals_added_frame_fraction": all(
                abs(row["per_aircraft"]["additional_packet_fraction_vs_surveillance"] - row["per_aircraft"]["analytical_added_airtime_fraction_vs_surveillance"]) < 1e-15
                for row in scenarios
            ),
        },
        "scenarios": scenarios,
        "interpretation_limits": [
            "This is an analytical reference transport, not a standards allocation or certified implementation.",
            "The calculation assumes 204 usable security bits after the modeled Phase 24 coding layout.",
            "Fragment and object identifiers are not specified; the result is a lower bound under the stated usable-payload assumption.",
            "Phase-overlay compatibility, synchronization, interference, receiver sensitivity, and legacy-receiver behavior remain unmeasured.",
            "The CABBA comparator uses different objects, schedules, and assurance functions and is not a performance-equivalence claim.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

