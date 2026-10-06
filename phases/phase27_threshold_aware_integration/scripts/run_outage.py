#!/usr/bin/env python3
"""Threshold-aware trust refresh and scheduled-outage replay."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import math
import os
import platform
import socket
import socketserver
import statistics
import threading
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

import threshold_core as core


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for line in self.rfile:
            request = json.loads(line)
            if self.server.outage_at is not None and float(request["sim_time"]) >= self.server.outage_at:
                response = {"available": False}
            else:
                time.sleep(self.server.delay_ms / 1000.0)
                response = {
                    "available": True,
                    "record": base64.b64encode(self.server.record).decode(),
                    "signature": base64.b64encode(self.server.signature).decode(),
                }
            self.wfile.write((json.dumps(response, separators=(",", ":")) + "\n").encode())
            self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def lookup(handle, sim_time: float, ca_public_key) -> bool:
    request = {"aircraft": "prototype", "sim_time": sim_time}
    handle.write((json.dumps(request, separators=(",", ":")) + "\n").encode())
    handle.flush()
    response = json.loads(handle.readline())
    if not response["available"]:
        return False
    record = base64.b64decode(response["record"])
    signature = base64.b64decode(response["signature"])
    try:
        ca_public_key.verify(signature, record, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def run_once(args, delay_ms: int, outage_at: float | None) -> dict:
    model = core.load_decision_model(args.decision_model)
    input_hashes = core.verify_model_inputs(
        model, args.selected, args.sensors, args.calibration, args.skip_hash_check
    )
    threshold_ns = float(model["threshold_ns"])
    sensors = core.load_sensors(args.sensors)
    biases = core.load_biases(args.calibration)
    modeled = set(sensors) & set(biases)
    ca_public, record, signature, root_key = core.deterministic_crypto_material(args.seed)

    server = Server(("127.0.0.1", 0), Handler)
    server.delay_ms = delay_ms
    server.outage_at = outage_at
    server.record = record
    server.signature = signature
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sock = socket.create_connection(server.server_address)
    handle = sock.makefile("rwb")

    counts = {
        "eligible_rows": 0,
        "hmac_verified": 0,
        core.PHYSICALLY_CONSISTENT: 0,
        core.PHYSICALLY_CONFLICTING: 0,
        core.PHYSICAL_EVIDENCE_UNAVAILABLE: 0,
        "trust_valid": 0,
        "trust_stale_or_absent": 0,
        "VERIFIED": 0,
        "CONFLICTING": 0,
        "INSUFFICIENT_EVIDENCE": 0,
        "refresh_attempts": 0,
        "refresh_successes": 0,
        "refresh_failures": 0,
    }
    cache_time = None
    next_retry_time = -math.inf
    start = time.perf_counter()
    try:
        with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as zipped:
            for row in csv.DictReader(zipped):
                if row["split"].strip().lower() != "test" or not core.truthy(row["eligible_ge4"]):
                    continue
                counts["eligible_rows"] += 1
                sim_time = float(row.get("timeAtServer") or 0.0)
                cache_valid = (
                    cache_time is not None
                    and sim_time - cache_time <= args.cache_ttl_seconds
                )
                if not cache_valid and sim_time >= next_retry_time:
                    counts["refresh_attempts"] += 1
                    if lookup(handle, sim_time, ca_public):
                        cache_time = sim_time
                        next_retry_time = -math.inf
                        counts["refresh_successes"] += 1
                    else:
                        next_retry_time = sim_time + args.retry_interval_seconds
                        counts["refresh_failures"] += 1

                trust = (
                    "VALID"
                    if cache_time is not None
                    and sim_time - cache_time <= args.cache_ttl_seconds
                    else "STALE"
                )
                counts["trust_valid" if trust == "VALID" else "trust_stale_or_absent"] += 1
                crypto = core.verify_hmac(row, root_key)
                if crypto == "VERIFIED":
                    counts["hmac_verified"] += 1
                physical, _, _ = core.physical_decision(
                    row, sensors, biases, modeled, threshold_ns
                )
                counts[physical] += 1
                final_state = core.fuse(crypto, trust, physical)
                counts[final_state] += 1
        wall_seconds = time.perf_counter() - start
    finally:
        handle.close()
        sock.close()
        server.shutdown()
        server.server_close()
        thread.join()
    return {
        "counts": counts,
        "wall_seconds": wall_seconds,
        "threshold_ns": threshold_ns,
        "input_hashes": input_hashes,
    }


def summarize(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--sensors", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--decision-model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--cache-ttl-seconds", type=float, default=900.0)
    parser.add_argument("--retry-interval-seconds", type=float, default=60.0)
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 3:
        parser.error("--repetitions must be at least 3")

    scenarios = [
        ("online_0ms", 0, None),
        ("online_50ms", 50, None),
        ("online_250ms", 250, None),
        ("outage_at_1800s", 50, 1800.0),
    ]
    output = []
    first_run = None
    for name, delay_ms, outage_at in scenarios:
        runs = [run_once(args, delay_ms, outage_at) for _ in range(args.repetitions)]
        baseline_counts = runs[0]["counts"]
        if any(run["counts"] != baseline_counts for run in runs):
            raise SystemExit(f"Non-deterministic counts in {name}")
        if first_run is None:
            first_run = runs[0]
        output.append(
            {
                "name": name,
                "added_delay_ms": delay_ms,
                "outage_at_seconds": outage_at,
                "counts": baseline_counts,
                "wall_seconds": summarize([run["wall_seconds"] for run in runs]),
            }
        )

    report = {
        "schema": "sam.phase27b.threshold-aware-trust-outage.v1",
        "scope": "threshold-aware physical decision + deterministic HMAC + signed TCP trust refresh + cache + fusion",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": args.seed,
            "repetitions": args.repetitions,
            "physical_threshold_ns": first_run["threshold_ns"],
            "cache_ttl_seconds": args.cache_ttl_seconds,
            "retry_interval_seconds": args.retry_interval_seconds,
            "outage_rule": "service unavailable for requests at or after 1800 s of dataset time",
            "fusion_policy": "physical conflict remains CONFLICTING even when trust becomes stale",
        },
        "inputs": {
            "sha256": first_run["input_hashes"],
            "decision_model_sha256": core.sha256_file(args.decision_model),
        },
        "scenarios": output,
        "correctness": {
            "all_online_hmac_verified": all(
                scenario["counts"]["hmac_verified"]
                == scenario["counts"]["eligible_rows"]
                for scenario in output[:3]
            ),
            "frozen_eligible_count": output[0]["counts"]["eligible_rows"] == 82_986,
            "frozen_physical_state_counts": all(
                scenario["counts"][core.PHYSICALLY_CONSISTENT] == 77_309
                and scenario["counts"][core.PHYSICALLY_CONFLICTING] == 1_049
                and scenario["counts"][core.PHYSICAL_EVIDENCE_UNAVAILABLE] == 4_628
                for scenario in output
            ),
            "online_full_policy_counts": all(
                scenario["counts"]["VERIFIED"] == 77_309
                and scenario["counts"]["CONFLICTING"] == 1_049
                and scenario["counts"]["INSUFFICIENT_EVIDENCE"] == 4_628
                for scenario in output[:3]
            ),
            "outage_preserves_physical_conflict": output[3]["counts"]["CONFLICTING"] == 1_049,
            "outage_creates_insufficient_evidence": output[3]["counts"]["INSUFFICIENT_EVIDENCE"] > 4_628,
            "outage_retry_backoff_active": 0 < output[3]["counts"]["refresh_failures"] < 100,
        },
        "interpretation_limits": [
            "Trust delay is controlled over loopback and is not operational WAN latency.",
            "The outage is a scheduled availability condition and not an attack label.",
            "No new revocation is injected after the final successful refresh.",
            "The threshold is a prototype operating point and the authenticator is synthetic.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

