#!/usr/bin/env python3
"""Benchmark CABBA-aligned identity/B2 verification and SAM trust degradation."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import resource
import statistics
import sys
import time
from pathlib import Path

from cryptography import __version__ as cryptography_version
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)


INTERVAL_KEY_BYTES = 16
HMAC_TAG_BYTES = 16


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
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


def raw_sign(private_key: ec.EllipticCurvePrivateKey, data: bytes) -> bytes:
    der = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def raw_verify(public_key: ec.EllipticCurvePublicKey, data: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        public_key.verify(encode_dss_signature(r, s), data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def compressed_public_key(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
    )


def aircraft_public_key_from_bytes(value: bytes) -> ec.EllipticCurvePublicKey:
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), value)


def interval_key(seed: int, index: int) -> bytes:
    return hashlib.sha3_256(
        b"SAM-PHASE10-INTERVAL\x00"
        + seed.to_bytes(8, "big")
        + index.to_bytes(8, "big")
    ).digest()[:INTERVAL_KEY_BYTES]


def message_tag(key: bytes, message: bytes) -> bytes:
    auth_key = hashlib.sha3_256(b"SAM-PHASE10-AUTH\x00" + key).digest()
    return hmac.new(auth_key, message, hashlib.sha3_256).digest()[:HMAC_TAG_BYTES]


def assurance_state(
    service_available: bool,
    cache_present: bool,
    cache_age_seconds: int,
    cache_ttl_seconds: int,
    registry_revoked: bool,
    ca_valid: bool,
    b2_valid: bool,
    hmac_valid: bool,
) -> str:
    trust_record_available = service_available or (
        cache_present and cache_age_seconds <= cache_ttl_seconds
    )
    if not trust_record_available:
        return "INSUFFICIENT_EVIDENCE"
    if registry_revoked or not ca_valid or not b2_valid or not hmac_valid:
        return "CONFLICTING"
    return "VERIFIED"


def timed_batch(operation, repetitions: int, count: int) -> dict:
    operation()  # warm-up
    values = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - start) / 1_000.0 / count)
    return summary(values)


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024.0 * 1024.0) if sys.platform == "darwin" else value / 1024.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--cache-ttl-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.iterations < 100 or args.repetitions < 2 or args.cache_ttl_seconds < 1:
        parser.error("use >=100 iterations, >=2 repetitions and a positive cache TTL")

    ca_private = ec.generate_private_key(ec.SECP256R1())
    ca_public = ca_private.public_key()
    aircraft_private = ec.generate_private_key(ec.SECP256R1())
    aircraft_public_bytes = compressed_public_key(aircraft_private.public_key())
    ca_signature = raw_sign(ca_private, b"SAM-AIRCRAFT-KEY\x00" + aircraft_public_bytes)
    aircraft_public = aircraft_public_key_from_bytes(aircraft_public_bytes)

    keys = [interval_key(args.seed, index) for index in range(args.iterations)]
    b2_signatures = [raw_sign(aircraft_private, b"SAM-B2\x00" + key) for key in keys]
    message = hashlib.sha3_256(b"SAM-PHASE10-MESSAGE").digest()[:14]
    tags = [message_tag(key, message) for key in keys]

    ca_valid = raw_verify(ca_public, b"SAM-AIRCRAFT-KEY\x00" + aircraft_public_bytes, ca_signature)
    all_b2_valid = all(
        raw_verify(aircraft_public, b"SAM-B2\x00" + key, signature)
        for key, signature in zip(keys, b2_signatures)
    )
    all_hmac_valid = all(
        hmac.compare_digest(message_tag(key, message), expected)
        for key, expected in zip(keys, tags)
    )

    timing = {
        "ca_record_verification": timed_batch(
            lambda: [
                raw_verify(ca_public, b"SAM-AIRCRAFT-KEY\x00" + aircraft_public_bytes, ca_signature)
                for _ in range(args.iterations)
            ],
            args.repetitions,
            args.iterations,
        ),
        "b2_signature_generation": timed_batch(
            lambda: [raw_sign(aircraft_private, b"SAM-B2\x00" + key) for key in keys],
            args.repetitions,
            args.iterations,
        ),
        "b2_signature_verification": timed_batch(
            lambda: [
                raw_verify(aircraft_public, b"SAM-B2\x00" + key, signature)
                for key, signature in zip(keys, b2_signatures)
            ],
            args.repetitions,
            args.iterations,
        ),
        "message_hmac_verification": timed_batch(
            lambda: [
                hmac.compare_digest(message_tag(key, message), expected)
                for key, expected in zip(keys, tags)
            ],
            args.repetitions,
            args.iterations,
        ),
    }

    scenarios_input = [
        ("online_valid", True, False, 0, False),
        ("offline_valid_cache", False, True, args.cache_ttl_seconds // 2, False),
        ("offline_cold_start", False, False, 0, False),
        ("offline_expired_cache", False, True, args.cache_ttl_seconds + 1, False),
        ("online_revoked_record", True, False, 0, True),
    ]
    scenarios = []
    for name, service, cache, age, revoked in scenarios_input:
        state = assurance_state(
            service, cache, age, args.cache_ttl_seconds, revoked,
            ca_valid, all_b2_valid, all_hmac_valid,
        )
        scenarios.append({
            "name": name,
            "service_available": service,
            "cache_present": cache,
            "cache_age_seconds": age,
            "registry_revoked": revoked,
            "ca_record_valid": ca_valid,
            "b2_signature_valid": all_b2_valid,
            "message_hmac_valid": all_hmac_valid,
            "assurance_state": state,
        })

    modified_key = bytearray(keys[0])
    modified_key[0] ^= 1
    invalid_b2_rejected = not raw_verify(
        aircraft_public, b"SAM-B2\x00" + bytes(modified_key), b2_signatures[0]
    )
    modified_public = bytearray(aircraft_public_bytes)
    modified_public[-1] ^= 1
    modified_ca_record_rejected = not raw_verify(
        ca_public, b"SAM-AIRCRAFT-KEY\x00" + bytes(modified_public), ca_signature
    )

    report = {
        "schema": "sam.phase10.identity-trust.v1",
        "scope": {
            "implemented": "CA-signed aircraft-key record, ECDSA-signed B2 keys, HMAC verification and deterministic trust degradation",
            "not_implemented": [
                "X.509 certificate parsing or global aviation PKI",
                "permissioned blockchain consensus or ledger writes",
                "Phase Overlay RF framing, FEC or BER",
                "complete SAM evidence fusion",
                "certified airborne hardware",
            ],
            "security_label": "No attack/anomaly dataset or classifier is used; negative cases are protocol unit tests.",
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "cryptography": cryptography_version,
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": args.seed,
            "iterations": args.iterations,
            "repetitions": args.repetitions,
            "cache_ttl_seconds": args.cache_ttl_seconds,
            "signature_algorithm": "ECDSA P-256 with SHA-256",
            "signature_encoding": "fixed-width r||s",
            "aircraft_public_key_encoding": "compressed SEC1",
            "hmac_algorithm": "HMAC-SHA3-256",
            "hmac_tag_bits": HMAC_TAG_BYTES * 8,
            "interval_key_bits": INTERVAL_KEY_BYTES * 8,
        },
        "correctness": {
            "ca_record_verified": ca_valid,
            "all_b2_signatures_verified": all_b2_valid,
            "all_message_hmacs_verified": all_hmac_valid,
            "modified_b2_key_rejected": invalid_b2_rejected,
            "modified_ca_record_rejected": modified_ca_record_rejected,
        },
        "timing_microseconds_per_operation": timing,
        "logical_communication_bytes_excluding_rf_framing_and_fec": {
            "compressed_aircraft_public_key": len(aircraft_public_bytes),
            "ca_signature": len(ca_signature),
            "compact_ca_record_total": len(aircraft_public_bytes) + len(ca_signature),
            "interval_key": INTERVAL_KEY_BYTES,
            "aircraft_signature_over_interval_key": len(b2_signatures[0]),
            "signed_b2_content_total": INTERVAL_KEY_BYTES + len(b2_signatures[0]),
            "message_hmac_tag": HMAC_TAG_BYTES,
        },
        "trust_service_scenarios": scenarios,
        "peak_rss_mib": peak_rss_mib(),
        "interpretation_limits": [
            "Timing values characterize this Python implementation and machine, not certified avionics.",
            "Online/offline service modes are deterministic local state tests and do not model network latency.",
            "The CA record is a compact signed-key prototype, not an X.509 certificate.",
            "Communication sizes exclude RF framing, Phase Overlay, FEC, repetition and scheduling.",
            "CONFLICTING denotes disagreement between cryptographic validity and trust status, not anomaly detection.",
        ],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

