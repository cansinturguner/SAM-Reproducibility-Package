#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import statistics
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def quantile(values, p):
    q = sorted(values)
    z = (len(q) - 1) * p
    lo = int(math.floor(z))
    hi = int(math.ceil(z))
    if lo == hi:
        return q[lo]
    return q[lo] * (hi - z) + q[hi] * (z - lo)


def bootstrap_median(values, rng, replicates):
    n = len(values)
    draws = []
    for _ in range(replicates):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        draws.append(statistics.median(sample))
    return {
        "estimate": statistics.median(values),
        "ci95_low": quantile(draws, 0.025),
        "ci95_high": quantile(draws, 0.975),
        "recorded_repetitions": n,
    }


def method(report, name):
    for row in report["methods"]:
        if row["method"] == name:
            return row
    raise SystemExit(f"Phase 19A method not found: {name}")


def phase17_scenario(report, name):
    for row in report["scenarios"]:
        if row["name"] == name:
            return row
    raise SystemExit(f"Phase 17 scenario not found: {name}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase14", type=Path, required=True)
    p.add_argument("--phase17", type=Path, required=True)
    p.add_argument("--phase19a", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--bootstrap-replicates", type=int, default=10000)
    a = p.parse_args()
    if a.bootstrap_replicates < 2000:
        p.error("--bootstrap-replicates must be at least 2000")

    p14, p17, p19 = load(a.phase14), load(a.phase17), load(a.phase19a)
    if p14.get("schema") != "sam.phase14.integrated-message-pipeline.v1":
        raise SystemExit("Unexpected Phase 14 schema")
    if p17.get("schema") != "sam.phase17.integrated-trust-refresh.v2":
        raise SystemExit("Unexpected Phase 17 schema")
    if p19.get("schema") != "sam.phase19a.authentication-baselines.v1":
        raise SystemExit("Unexpected Phase 19A schema")

    eligible = int(p14["counts"]["test_original_ge4_rows"])
    supported = int(p14["counts"]["physical_supported_rows"])
    if eligible != 82986 or supported != 78358:
        raise SystemExit("Frozen Phase 14 counts do not match the validated experiment")

    rng = random.Random(a.seed)
    rows = []
    definitions = [
        ("Legacy unauthenticated", "authentication-only", False, False, False, False),
        ("Pre-shared HMAC", "authentication-only", True, False, False, False),
        ("ECDSA per message", "authentication-only", True, False, False, False),
        ("TESLA-style post-disclosure HMAC", "authentication-only", True, True, False, False),
    ]
    for name, boundary, auth, delayed, physical, trust in definitions:
        src = method(p19, name)
        values = [float(x) for x in src["microseconds_per_message"]["values"]]
        rows.append({
            "method": name,
            "timing_boundary": boundary,
            "median_microseconds_per_message": statistics.median(values),
            "bootstrap_ci95_microseconds": bootstrap_median(values, rng, a.bootstrap_replicates),
            "protocol_delay_seconds": src["protocol_authentication_delay_seconds"],
            "logical_security_bytes_per_message": src["logical_security_bytes_per_message"],
            "functional_coverage": {
                "message_authentication": auth,
                "delayed_disclosure": delayed,
                "physical_cross_sensor": physical,
                "cached_identity_trust": trust,
                "fusion": False,
            },
            "source": "Phase 19A measured",
        })

    sam_values = [float(x) for x in p14["summaries"]["microseconds_per_original_ge4_row"]["values"]]
    sam_median = statistics.median(sam_values)
    sam_row = {
        "method": "SAM cached integrated path",
        "timing_boundary": "integrated cached path",
        "median_microseconds_per_message": sam_median,
        "bootstrap_ci95_microseconds": bootstrap_median(sam_values, rng, a.bootstrap_replicates),
        "protocol_delay_seconds": 1.0,
        "logical_security_bytes_per_message": method(p19, "SAM crypto-trust-fusion stage")["logical_security_bytes_per_message"],
        "functional_coverage": {
            "message_authentication": True,
            "delayed_disclosure": True,
            "physical_cross_sensor": True,
            "cached_identity_trust": True,
            "fusion": True,
        },
        "physical_support": {
            "eligible_rows": eligible,
            "supported_rows": supported,
            "availability": supported / eligible,
        },
        "source": "Phase 14 measured; includes file replay, physical/TDoA, HMAC, cached trust and fusion",
    }
    rows.append(sam_row)

    trust = []
    for name in ("online_0ms", "online_50ms", "online_250ms"):
        x = phase17_scenario(p17, name)
        delay_ms = float(x["added_delay_ms"])
        refreshes = int(x["counts"]["refresh_successes"])
        increment_us = refreshes * delay_ms * 1000.0 / eligible
        trust.append({
            "scenario": name,
            "successful_refreshes": refreshes,
            "controlled_delay_ms_per_refresh": delay_ms,
            "derived_amortized_delay_microseconds_per_message": increment_us,
            "sam_cached_median_plus_derived_delay_microseconds": sam_median + increment_us,
            "derivation": "refresh_successes * controlled_delay / eligible_rows",
        })

    outage = phase17_scenario(p17, "outage_at_1800s")
    report = {
        "schema": "sam.phase19b.system-boundary-comparison.v1",
        "scope": {
            "implemented": "cross-phase comparison with explicit authentication-only, integrated cached-path, protocol-delay and amortized trust-refresh boundaries",
            "not_implemented": [
                "complete CABBA reproduction",
                "RF framing, FEC, BER or channel occupancy",
                "operational WAN or ledger consensus",
                "certified airborne hardware",
                "attack or anomaly classification",
            ],
        },
        "platform": {
            "consolidation_system": platform.system(),
            "consolidation_release": platform.release(),
            "consolidation_machine": platform.machine(),
            "python": platform.python_version(),
            "measurement_platform_note": "All source measurements were produced on the recorded Mac ARM/Python 3.12 prototype.",
        },
        "configuration": {
            "seed": a.seed,
            "bootstrap_replicates": a.bootstrap_replicates,
            "comparison_workload": "10,000-message authentication microbenchmark plus frozen 82,986-row LocaRDS integrated replay",
        },
        "inputs": {
            "phase14": {"path": str(a.phase14), "sha256": sha256_file(a.phase14)},
            "phase17": {"path": str(a.phase17), "sha256": sha256_file(a.phase17)},
            "phase19a": {"path": str(a.phase19a), "sha256": sha256_file(a.phase19a)},
        },
        "comparison": rows,
        "trust_refresh_amortization": trust,
        "scheduled_outage_context": {
            "service_outage_at_dataset_seconds": outage["outage_at_seconds"],
            "refresh_attempts": outage["counts"]["refresh_attempts"],
            "refresh_successes": outage["counts"]["refresh_successes"],
            "refresh_failures": outage["counts"]["refresh_failures"],
            "VERIFIED": outage["counts"]["VERIFIED"],
            "INSUFFICIENT_EVIDENCE": outage["counts"]["INSUFFICIENT_EVIDENCE"],
            "CONFLICTING": outage["counts"]["CONFLICTING"],
            "note": "Outage behavior is reported as a controlled availability state transition, not folded into authentication compute cost.",
        },
        "interpretation_limits": [
            "Authentication-only rows and the SAM integrated row have different functional coverage; timings must be read with the coverage fields.",
            "The Phase 14 SAM value includes direct-TDoA/physical processing but excludes TESLA schedule delay and online refresh.",
            "The one-second TESLA delay is protocol latency and is not added to microsecond compute time.",
            "Trust-refresh increments are derived amortized controlled delays, not operational-WAN measurements.",
            "Bootstrap intervals quantify recorded prototype run-to-run variation and do not establish certified airborne performance.",
            "Logical byte counts are not RF-channel occupancy.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

