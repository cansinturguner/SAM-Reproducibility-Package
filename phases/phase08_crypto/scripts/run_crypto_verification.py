#!/usr/bin/env python3
"""Benchmark SAM cryptographic verification primitives without RF claims."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import random
import resource
import statistics
import sys
import time
from pathlib import Path

from cryptography import __version__ as cryptography_version
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)


PROFILE_VERSION = "sam-phase8-v1"
HMAC_TAG_BYTES = 16
ROOT_KEY_BYTES = 64
TEMP_KEY_BYTES = 32


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def summary(values: list[float]) -> dict[str, float | int]:
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


def derive_temp_key(root_key: bytes, interval: int) -> bytes:
    """Benchmark-defined HMAC-SHA3-256 derivation with domain separation."""
    context = (
        b"SAM-PHASE8-TEMP-KEY\x00"
        + PROFILE_VERSION.encode("ascii")
        + interval.to_bytes(8, "big")
    )
    return hmac.new(root_key, context, hashlib.sha3_256).digest()[:TEMP_KEY_BYTES]


def authenticated_input(counter: int, message: bytes) -> bytes:
    return b"SAM-PHASE8-AUTH\x00" + counter.to_bytes(8, "big") + message


def make_messages(seed: int, count: int, message_bytes: int) -> list[bytes]:
    rng = random.Random(seed)
    return [rng.randbytes(message_bytes) for _ in range(count)]


def hmac_tag(key: bytes, counter: int, message: bytes) -> bytes:
    return hmac.new(
        key, authenticated_input(counter, message), hashlib.sha3_256
    ).digest()[:HMAC_TAG_BYTES]


def counter_is_fresh(last_accepted_counter: int, incoming_counter: int) -> bool:
    """Minimal Phase 8 monotonic freshness rule; equal/older values are rejected."""
    return incoming_counter > last_accepted_counter


def raw_ecdsa_signature(private_key: ec.EllipticCurvePrivateKey, data: bytes) -> bytes:
    der = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify_raw_ecdsa(
    public_key: ec.EllipticCurvePublicKey, data: bytes, signature: bytes
) -> bool:
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        public_key.verify(encode_dss_signature(r, s), data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def timed_batch(operation, repetitions: int) -> list[float]:
    operation()  # untimed warm-up to reduce one-time import/backend effects
    values = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - start) / 1_000.0)
    return values


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return value / (1024.0 * 1024.0)
    return value / 1024.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--messages", type=int, default=10_000)
    parser.add_argument("--message-bytes", type=int, default=14)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if args.messages < 100 or args.repetitions < 2 or args.message_bytes < 1:
        parser.error("use at least 100 messages, 2 repetitions, and 1 message byte")

    messages = make_messages(args.seed, args.messages, args.message_bytes)
    # Deterministic key material is acceptable only for this reproducible benchmark.
    root_key = hashlib.sha512(f"SAM-PHASE8:{args.seed}".encode()).digest()
    temp_key = derive_temp_key(root_key, interval=0)
    counters = list(range(args.messages))

    tags = [hmac_tag(temp_key, c, m) for c, m in zip(counters, messages)]
    hmac_sign_us = timed_batch(
        lambda: [hmac_tag(temp_key, c, m) for c, m in zip(counters, messages)],
        args.repetitions,
    )
    hmac_verify_us = timed_batch(
        lambda: [
            hmac.compare_digest(hmac_tag(temp_key, c, m), tag)
            for c, m, tag in zip(counters, messages, tags)
        ],
        args.repetitions,
    )

    modified = bytearray(messages[0])
    modified[0] ^= 1
    negative_hmac_rejected = not hmac.compare_digest(
        hmac_tag(temp_key, counters[0], bytes(modified)), tags[0]
    )
    # A receiver that has accepted counter 1 must reject a replay of counter 0.
    stale_counter_rejected = not counter_is_fresh(
        last_accepted_counter=counters[1], incoming_counter=counters[0]
    )

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    signatures = [raw_ecdsa_signature(private_key, m) for m in messages]
    ecdsa_sign_us = timed_batch(
        lambda: [raw_ecdsa_signature(private_key, m) for m in messages],
        args.repetitions,
    )
    ecdsa_verify_us = timed_batch(
        lambda: [verify_raw_ecdsa(public_key, m, s) for m, s in zip(messages, signatures)],
        args.repetitions,
    )
    negative_ecdsa_rejected = not verify_raw_ecdsa(
        public_key, bytes(modified), signatures[0]
    )

    def per_message(batch_values: list[float]) -> dict[str, float | int]:
        return summary([value / args.messages for value in batch_values])

    report = {
        "schema": "sam.phase8.crypto-benchmark.v1",
        "scope": {
            "implemented": "message-layer cryptographic primitive benchmark",
            "not_implemented": [
                "Phase Overlay RF waveform or demodulation",
                "DO-260C/ED-102B bit-level framing",
                "TESLA delayed key-disclosure state machine",
                "airborne certified hardware",
                "complete SAM evidence fusion",
            ],
            "security_label": "No attack or anomaly dataset or classifier is used.",
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
            "message_count": args.messages,
            "synthetic_message_bytes": args.message_bytes,
            "repetitions": args.repetitions,
            "root_key_bits": ROOT_KEY_BYTES * 8,
            "temporary_key_bits": TEMP_KEY_BYTES * 8,
            "hmac_algorithm": "HMAC-SHA3-256",
            "transmitted_hmac_tag_bits": HMAC_TAG_BYTES * 8,
            "kdf": "benchmark-defined domain-separated HMAC-SHA3-256",
            "ecdsa_curve": "NIST P-256/secp256r1",
            "ecdsa_hash": "SHA-256",
            "ecdsa_wire_encoding": "fixed-width r||s",
        },
        "correctness": {
            "valid_hmac_verified": all(
                hmac.compare_digest(hmac_tag(temp_key, c, m), tag)
                for c, m, tag in zip(counters, messages, tags)
            ),
            "modified_message_hmac_rejected": negative_hmac_rejected,
            "stale_counter_rejected_by_monotonic_rule": stale_counter_rejected,
            "valid_ecdsa_verified": all(
                verify_raw_ecdsa(public_key, m, s)
                for m, s in zip(messages, signatures)
            ),
            "modified_message_ecdsa_rejected": negative_ecdsa_rejected,
        },
        "timing_microseconds_per_message": {
            "hmac_generation": per_message(hmac_sign_us),
            "hmac_verification": per_message(hmac_verify_us),
            "ecdsa_generation": per_message(ecdsa_sign_us),
            "ecdsa_verification": per_message(ecdsa_verify_us),
        },
        "communication_bytes_per_authenticator": {
            "hmac_tag": HMAC_TAG_BYTES,
            "ecdsa_signature": 64,
            "notes": [
                "These are authenticator sizes only, not complete Phase Overlay frames.",
                "Certificate, key-disclosure, FEC, counter, and scheduling overhead are excluded.",
            ],
        },
        "peak_rss_mib": peak_rss_mib(),
        "interpretation_limits": [
            "Results characterize this Python implementation and machine.",
            "They are not measurements on certified airborne avionics.",
            "Synthetic messages measure primitive cost, not RF decoding or end-to-end authentication delay.",
            "Negative correctness checks are protocol unit tests, not anomaly detection metrics.",
        ],
    }

    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
