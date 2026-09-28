#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

from cryptography import __version__ as cryptography_version
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)


ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
CABBA_TAG_BITS = 196
CABBA_TAG_BYTES = 25
CABBA_INTERVAL_KEY_BYTES = 16


def percentile(values, p):
    x = sorted(values)
    z = (len(x) - 1) * p
    a = int(z)
    b = min(a + 1, len(x) - 1)
    return x[a] * (b - z) + x[b] * (z - a)


def summary(values):
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "q05": percentile(values, 0.05),
        "q95": percentile(values, 0.95),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "values": values,
    }


def peak_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def ec_key(label, seed):
    scalar = 1 + (
        int.from_bytes(hashlib.sha256(f"{label}:{seed}".encode()).digest(), "big")
        % (ORDER - 1)
    )
    return ec.derive_private_key(scalar, ec.SECP256R1())


def raw_sign(private_key, message):
    r, s = decode_dss_signature(private_key.sign(message, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def raw_verify(public_key, signature, message):
    try:
        if len(signature) != 64:
            return False
        der = encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        public_key.verify(der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def cabba_tag(key, message, sequence):
    digest = hmac.new(key, message + bytes([sequence]), hashlib.sha256).digest()
    tag = bytearray(digest[:CABBA_TAG_BYTES])
    tag[-1] &= 0xF0  # retain the leftmost 196 bits
    return bytes(tag)


def sam_tag(key, message):
    return hmac.new(key, message, hashlib.sha3_256).digest()[:16]


def fuse(crypto, physical, trust):
    if "CONFLICTING" in (crypto, physical, trust):
        return "CONFLICTING"
    if (crypto, physical, trust) == ("VERIFIED", "VERIFIED", "VERIFIED"):
        return "VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def build_reverse_chain(seed, count):
    chain = [b""] * count
    chain[-1] = hashlib.sha256(f"cabba-terminal:{seed}".encode()).digest()[:16]
    for i in range(count - 2, -1, -1):
        chain[i] = hashlib.sha256(b"cabba-chain:" + chain[i + 1]).digest()[:16]
    return chain


def chain_link_valid(earlier, later, distance):
    value = later
    for _ in range(distance):
        value = hashlib.sha256(b"cabba-chain:" + value).digest()[:16]
    return hmac.compare_digest(earlier, value)


def benchmark(repetitions, denominator, function):
    values = []
    result = None
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        result = function()
        values.append((time.perf_counter_ns() - start) / denominator / 1000)
    return result, summary(values)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--message-count", type=int, default=10000)
    p.add_argument("--repetitions", type=int, default=10)
    p.add_argument("--message-rate", type=float, default=6.2)
    a = p.parse_args()
    if a.message_count < 1000 or a.repetitions < 5 or a.message_rate <= 0:
        p.error("use >=1000 messages, >=5 repetitions, and a positive message rate")

    rng = random.Random(a.seed)
    messages = [rng.randbytes(14) for _ in range(a.message_count)]
    sequences = [i % 256 for i in range(a.message_count)]
    duration_seconds = a.message_count / a.message_rate
    interval_seconds = 5.0
    interval_count = max(2, math.ceil(duration_seconds / interval_seconds) + 1)
    chain = build_reverse_chain(a.seed, interval_count)
    message_intervals = [min(int((i / a.message_rate) // interval_seconds), interval_count - 2) for i in range(a.message_count)]

    ca_private = ec_key("cabba-ca", a.seed)
    aircraft_private = ec_key("cabba-aircraft", a.seed)
    aircraft_public = aircraft_private.public_key()
    aircraft_public_bytes = aircraft_public.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint,
    )
    certificate_signature = raw_sign(ca_private, aircraft_public_bytes)

    cabba_tags = [
        cabba_tag(chain[interval], message, sequence)
        for message, sequence, interval in zip(messages, sequences, message_intervals)
    ]
    signed_interval_indices = sorted(set(message_intervals))
    b2_signatures = {
        i: raw_sign(aircraft_private, chain[i]) for i in signed_interval_indices
    }

    sam_key = hashlib.sha3_256(f"sam-hmac:{a.seed}".encode()).digest()[:16]
    sam_tags = [sam_tag(sam_key, message) for message in messages]

    def cabba_verify_all():
        return sum(
            hmac.compare_digest(tag, cabba_tag(chain[interval], message, sequence))
            for message, sequence, interval, tag in zip(
                messages, sequences, message_intervals, cabba_tags
            )
        )

    def sam_verify_all():
        accepted = 0
        for message, tag in zip(messages, sam_tags):
            crypto = (
                "VERIFIED"
                if hmac.compare_digest(tag, sam_tag(sam_key, message))
                else "CONFLICTING"
            )
            if fuse(crypto, "VERIFIED", "VERIFIED") == "VERIFIED":
                accepted += 1
        return accepted

    cabba_accepted, cabba_timing = benchmark(
        a.repetitions, a.message_count, cabba_verify_all
    )
    sam_accepted, sam_timing = benchmark(a.repetitions, a.message_count, sam_verify_all)

    operation_iterations = max(1000, a.message_count)

    def verify_b2_many():
        idx = signed_interval_indices[0]
        signature = b2_signatures[idx]
        return sum(
            raw_verify(aircraft_public, signature, chain[idx])
            for _ in range(operation_iterations)
        )

    def verify_certificate_many():
        return sum(
            raw_verify(ca_private.public_key(), certificate_signature, aircraft_public_bytes)
            for _ in range(operation_iterations)
        )

    b2_ok, b2_timing = benchmark(5, operation_iterations, verify_b2_many)
    cert_ok, cert_timing = benchmark(5, operation_iterations, verify_certificate_many)

    scenarios = [
        ("scenario_1", 5.0, 5.0),
        ("scenario_2", 10.0, 15.0),
        ("scenario_3", 10.0, 20.0),
        ("scenario_4", 15.0, 30.0),
    ]
    scenario_results = []
    legacy_airtime_us = a.message_count * 120.0
    for name, b2_period, c_period in scenarios:
        boundaries = math.ceil(duration_seconds / interval_seconds)
        b2_count = math.floor(duration_seconds / b2_period) + 1
        b1_count = max(0, boundaries - b2_count)
        c_count = math.floor(duration_seconds / c_period) + 1
        added_packets = b1_count + b2_count + c_count
        added_airtime_us = b1_count * 120.0 + b2_count * 218.0 + c_count * 250.0
        scenario_results.append(
            {
                "name": name,
                "TB1_seconds": interval_seconds,
                "TB2_seconds": b2_period,
                "TC_seconds": c_period,
                "workload_duration_seconds": duration_seconds,
                "type_A_messages": a.message_count,
                "type_B1_packets": b1_count,
                "type_B2_packets": b2_count,
                "type_C_packets": c_count,
                "additional_packet_fraction_vs_type_A": added_packets / a.message_count,
                "analytical_added_airtime_fraction_vs_legacy_A": added_airtime_us / legacy_airtime_us,
                "published_airtime_microseconds": {
                    "A": 120.0,
                    "B1": 120.0,
                    "B2": 218.0,
                    "C": 250.0,
                },
            }
        )

    # Scheduled receiver-compute boundary.  CABBA uses the most bandwidth-
    # efficient published Table 3 setting (Scenario 4). The paper has conflicting
    # Scenario 4 timing statements elsewhere; SOURCE_DECISIONS.md records them.
    # SAM uses the frozen
    # Phase 19A one-second interval and 60-second signed-key period.  RF,
    # disclosure waiting, input I/O, and direct-TDoA remain outside this timing.
    cabba_s4 = scenario_results[-1]
    cabba_b1_count = cabba_s4["type_B1_packets"]
    cabba_b2_count = cabba_s4["type_B2_packets"]
    cabba_c_count = cabba_s4["type_C_packets"]
    first_interval = signed_interval_indices[0]
    first_b2_signature = b2_signatures[first_interval]

    def cabba_scheduled_receiver():
        accepted = cabba_verify_all()
        key_links = sum(
            chain_link_valid(chain[0], chain[1], 1) for _ in range(cabba_b1_count)
        )
        signed_keys = sum(
            raw_verify(aircraft_public, first_b2_signature, chain[first_interval])
            for _ in range(cabba_b2_count)
        )
        certificates = sum(
            raw_verify(ca_private.public_key(), certificate_signature, aircraft_public_bytes)
            for _ in range(cabba_c_count)
        )
        return accepted, key_links, signed_keys, certificates

    sam_interval_seconds = 1.0
    sam_b2_period_seconds = 60.0
    sam_b2_count = math.floor(duration_seconds / sam_b2_period_seconds) + 1
    sam_interval_key = hashlib.sha3_256(f"sam-interval:{a.seed}".encode()).digest()[:16]
    sam_b2_signature = raw_sign(aircraft_private, sam_interval_key)

    def sam_scheduled_receiver():
        accepted = sam_verify_all()
        signed_keys = sum(
            raw_verify(aircraft_public, sam_b2_signature, sam_interval_key)
            for _ in range(sam_b2_count)
        )
        # Cached trust verifies the compact aircraft record once for this
        # single-aircraft workload, rather than once per message.
        certificate = raw_verify(
            ca_private.public_key(), certificate_signature, aircraft_public_bytes
        )
        return accepted, signed_keys, certificate

    cabba_schedule_result, cabba_schedule_timing = benchmark(
        a.repetitions, a.message_count, cabba_scheduled_receiver
    )
    sam_schedule_result, sam_schedule_timing = benchmark(
        a.repetitions, a.message_count, sam_scheduled_receiver
    )

    modified = bytes([messages[0][0] ^ 1]) + messages[0][1:]
    modified_rejected = not hmac.compare_digest(
        cabba_tags[0], cabba_tag(chain[message_intervals[0]], modified, sequences[0])
    )
    stale_sequence_rejected = not hmac.compare_digest(
        cabba_tags[1],
        cabba_tag(chain[message_intervals[1]], messages[1], (sequences[1] - 1) % 256),
    )
    bad_b2 = bytearray(b2_signatures[signed_interval_indices[0]])
    bad_b2[0] ^= 1
    invalid_b2_rejected = not raw_verify(
        aircraft_public,
        bytes(bad_b2),
        chain[signed_interval_indices[0]],
    )
    bad_certificate = bytearray(certificate_signature)
    bad_certificate[0] ^= 1
    invalid_certificate_rejected = not raw_verify(
        ca_private.public_key(), bytes(bad_certificate), aircraft_public_bytes
    )
    chain_link_check = chain_link_valid(chain[0], chain[min(3, len(chain) - 1)], min(3, len(chain) - 1))

    report = {
        "schema": "sam.phase23.cabba-comparison.v1",
        "scope": {
            "implemented": "independent CABBA application-layer reproduction and same-workload SAM comparison",
            "not_implemented": [
                "CABBA authors' original custom SDR code",
                "D8PSK waveform generation or demodulation",
                "RS(54,34), RF framing, BER, Eb/N0 or receiver compatibility",
                "operational X.509 or aviation PKI",
                "SAM direct-TDoA in the authentication-only row",
                "certified airborne hardware",
            ],
            "security_label": "controlled protocol conformance and performance workload; no attack/anomaly classifier",
        },
        "provenance": {
            "primary_reference": "Ngamboe et al., CABBA, International Journal of Critical Infrastructure Protection 48 (2025) 100728",
            "doi": "10.1016/j.ijcip.2024.100728",
            "public_preprint": "arXiv:2312.09870",
            "original_author_code_used": False,
            "reproduction_statement": "Independent implementation from the published protocol description.",
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
            "seed": a.seed,
            "message_count": a.message_count,
            "synthetic_message_bytes": 14,
            "message_rate_per_second": a.message_rate,
            "repetitions": a.repetitions,
            "cabba_published_parameters": {
                "tesla_interval_seconds": interval_seconds,
                "interval_key_bits": 128,
                "type_A_sequence_bits": 8,
                "type_A_mac_bits": CABBA_TAG_BITS,
                "ecdsa_signature_bits": 512,
                "conceptual_public_key_bits": 256,
            },
            "reproduction_choices": {
                "hmac": "HMAC-SHA-256/196; digest is an explicit reproduction choice because the protocol description does not name one",
                "signature": "ECDSA P-256/SHA-256 fixed-width r||s",
                "software_public_key_encoding": "compressed SEC1 (33 bytes); not used as published wire-size evidence",
                "key_chain": "domain-separated SHA-256 reverse chain",
            },
            "sam_comparator": "HMAC-SHA3-256/128 + valid cached trust + controlled physical state + deterministic fusion; direct-TDoA excluded",
        },
        "correctness": {
            "cabba_all_valid_type_A_accepted": cabba_accepted == a.message_count,
            "sam_all_valid_messages_accepted": sam_accepted == a.message_count,
            "modified_type_A_rejected": modified_rejected,
            "stale_sequence_rejected": stale_sequence_rejected,
            "invalid_B2_signature_rejected": invalid_b2_rejected,
            "invalid_C_certificate_signature_rejected": invalid_certificate_rejected,
            "cabba_key_chain_link_valid": chain_link_check,
            "all_B2_benchmark_verifications_valid": b2_ok == operation_iterations,
            "all_C_benchmark_verifications_valid": cert_ok == operation_iterations,
            "cabba_scenario4_scheduled_receiver_valid": cabba_schedule_result
            == (a.message_count, cabba_b1_count, cabba_b2_count, cabba_c_count),
            "sam_scheduled_receiver_valid": sam_schedule_result
            == (a.message_count, sam_b2_count, True),
        },
        "same_workload_timing_microseconds_per_message": {
            "CABBA_type_A_post_disclosure_HMAC": cabba_timing,
            "SAM_crypto_trust_fusion_stage": sam_timing,
        },
        "periodic_verification_microseconds_per_operation": {
            "CABBA_type_B2_signed_interval_key": b2_timing,
            "CABBA_type_C_CA_signed_aircraft_key": cert_timing,
        },
        "scheduled_receiver_compute_microseconds_per_message": {
            "CABBA_scenario_4": {
                "timing": cabba_schedule_timing,
                "type_A_messages": a.message_count,
                "type_B1_key_chain_checks": cabba_b1_count,
                "type_B2_signature_checks": cabba_b2_count,
                "type_C_certificate_checks": cabba_c_count,
                "boundary": "Type A HMAC + B1 key-chain + B2 signature + C certificate verification; RF and disclosure wait excluded",
            },
            "SAM_frozen_crypto_trust_fusion_schedule": {
                "timing": sam_schedule_timing,
                "messages": a.message_count,
                "signed_interval_key_checks": sam_b2_count,
                "cached_aircraft_record_checks": 1,
                "boundary": "HMAC + cached trust + controlled physical state + fusion + scheduled signature checks; direct-TDoA and disclosure wait excluded",
            },
        },
        "protocol_latency_seconds": {
            "CABBA_nominal_next_interval_disclosure": interval_seconds,
            "SAM_frozen_phase19A_disclosure": 1.0,
            "note": "Protocol schedule latency is separate from microsecond computation time.",
        },
        "cabba_published_schedule_accounting": scenario_results,
        "functional_coverage": {
            "CABBA_reproduction": {
                "message_integrity": True,
                "data_origin_authentication": True,
                "entity_authentication": True,
                "delayed_disclosure": True,
                "published_phase_overlay_design": True,
                "phase_overlay_implemented_here": False,
                "physical_cross_sensor_corroboration": False,
                "multi_evidence_fusion": False,
            },
            "SAM_comparator_row": {
                "message_integrity": True,
                "data_origin_authentication": True,
                "entity_trust_cached": True,
                "delayed_disclosure": True,
                "phase_overlay_implemented": False,
                "physical_cross_sensor_corroboration": False,
                "multi_evidence_fusion": True,
                "note": "The controlled physical state exercises fusion but excludes direct-TDoA computation; use Phase 14/21 for the integrated physical path.",
            },
        },
        "peak_rss_mib": peak_mib(),
        "interpretation_limits": [
            "This is an independent application-layer reproduction, not the CABBA authors' original SDR implementation.",
            "The comparison does not reproduce CABBA RF phase overlay, FEC, BER, or backward-compatibility receiver tests.",
            "HMAC-SHA-256 is an explicit reproduction choice because the available CABBA protocol description does not name a digest.",
            "Scenario 4 uses the explicit CABBA Table 3 values TB2=15 s and TC=30 s; nearby prose and later uncertainty tables contain conflicting TB2 values.",
            "Published CABBA packet airtime is analytical accounting and is not measured RF occupancy on this Mac.",
            "The SAM comparison row excludes direct-TDoA; Phase 14 and Phase 21 remain the integrated SAM timing evidence.",
            "No precision, recall, F1, false-positive or false-negative result is produced.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
