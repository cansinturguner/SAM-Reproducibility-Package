#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import reedsolo
from scipy.stats import beta


SCHEMA = "sam.phase24.rf-waveform-feasibility.v2"
GF_BITS = 6
GF_SIZE = 1 << GF_BITS
GF_ORDER = GF_SIZE - 1
GF_PRIMITIVE_POLYNOMIAL = 0x43  # x^6 + x + 1; implementation choice
RS_N = 54
RS_K = 34
RS_PARITY = RS_N - RS_K
RS_T = RS_PARITY // 2
RS_CODEC = reedsolo.RSCodec(
    nsym=RS_PARITY,
    nsize=GF_ORDER,
    fcr=1,
    prim=GF_PRIMITIVE_POLYNOMIAL,
    generator=2,
    c_exp=GF_BITS,
)


def peak_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def exact_binomial_interval(errors: int, trials: int, alpha: float = 0.05) -> dict:
    if trials <= 0:
        raise ValueError("trials must be positive")
    low = 0.0 if errors == 0 else float(beta.ppf(alpha / 2, errors, trials - errors + 1))
    high = 1.0 if errors == trials else float(beta.ppf(1 - alpha / 2, errors + 1, trials - errors))
    return {"low": low, "high": high}


def build_gf_tables():
    exp = np.zeros(GF_ORDER * 2, dtype=np.uint8)
    log = np.full(GF_SIZE, -1, dtype=np.int16)
    x = 1
    seen = set()
    for i in range(GF_ORDER):
        if x in seen:
            raise RuntimeError("primitive polynomial did not generate GF(64)")
        seen.add(x)
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & GF_SIZE:
            x ^= GF_PRIMITIVE_POLYNOMIAL
        x &= GF_ORDER
    exp[GF_ORDER:] = exp[:GF_ORDER]
    mul = np.zeros((GF_SIZE, GF_SIZE), dtype=np.uint8)
    for a in range(1, GF_SIZE):
        for b in range(1, GF_SIZE):
            mul[a, b] = exp[int(log[a]) + int(log[b])]
    return exp, log, mul, len(seen)


GF_EXP, GF_LOG, GF_MUL, GF_CYCLE = build_gf_tables()


def poly_mul(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] ^= int(GF_MUL[x, y])
    return out


def generator_poly() -> np.ndarray:
    g = [1]
    for i in range(1, RS_PARITY + 1):
        g = poly_mul(g, [1, int(GF_EXP[i])])
    return np.asarray(g, dtype=np.uint8)


RS_GENERATOR = generator_poly()


def rs_encode(messages: np.ndarray) -> np.ndarray:
    if messages.ndim != 2 or messages.shape[1] != RS_K:
        raise ValueError("messages must have shape (n,34)")
    work = np.zeros((messages.shape[0], RS_N), dtype=np.uint8)
    work[:, :RS_K] = messages
    for i in range(RS_K):
        coefficient = work[:, i].copy()
        for j, g in enumerate(RS_GENERATOR):
            work[:, i + j] ^= GF_MUL[coefficient, g]
    return np.concatenate((messages, work[:, RS_K:]), axis=1)


def gf_poly_eval(poly: np.ndarray, x: int) -> int:
    y = 0
    for coefficient in poly:
        y = int(GF_MUL[y, x]) ^ int(coefficient)
    return y


def codeword_syndromes(codeword: np.ndarray) -> list[int]:
    return [gf_poly_eval(codeword, int(GF_EXP[i])) for i in range(1, RS_PARITY + 1)]


def sixbit_to_d8psk_symbols(codewords: np.ndarray) -> np.ndarray:
    high = codewords >> 3
    low = codewords & 0x07
    out = np.empty((codewords.shape[0], RS_N * 2), dtype=np.uint8)
    out[:, 0::2] = high
    out[:, 1::2] = low
    return out


def d8psk_symbols_to_sixbit(symbols: np.ndarray) -> np.ndarray:
    return ((symbols[:, 0::2] << 3) | symbols[:, 1::2]).astype(np.uint8)


def differential_modulate(increments: np.ndarray) -> np.ndarray:
    phases = np.cumsum(increments.astype(np.int16), axis=1) & 7
    return np.exp(1j * (2 * np.pi / 8) * phases)


def differential_demodulate(received: np.ndarray) -> np.ndarray:
    previous = np.concatenate(
        (np.ones((received.shape[0], 1), dtype=np.complex128), received[:, :-1]),
        axis=1,
    )
    differences = received * np.conj(previous)
    angles = np.mod(np.angle(differences), 2 * np.pi)
    return (np.floor(angles / (2 * np.pi / 8) + 0.5).astype(np.uint8) & 7)


BIT_COUNTS_3 = np.asarray([int(i).bit_count() for i in range(8)], dtype=np.uint8)
BIT_COUNTS_6 = np.asarray([int(i).bit_count() for i in range(64)], dtype=np.uint8)


def ppm_d8psk_baseband(message_bits: np.ndarray, overlay_symbols: np.ndarray, samples_per_us: int = 8) -> np.ndarray:
    if message_bits.shape != (112,) or overlay_symbols.shape != (112,):
        raise ValueError("expected 112 PPM bits and 112 overlay symbols")
    if samples_per_us % 2:
        raise ValueError("samples_per_us must be even")
    phases = np.cumsum(overlay_symbols.astype(np.int16)) & 7
    waveform = np.zeros(112 * samples_per_us, dtype=np.complex64)
    half = samples_per_us // 2
    for i, bit in enumerate(message_bits):
        start = i * samples_per_us + (half if int(bit) else 0)
        waveform[start:start + half] = np.exp(1j * (2 * np.pi / 8) * phases[i])
    return waveform


def simulate_point(rng: np.random.Generator, ebno_db: float, packets: int, batch_size: int):
    overlay_bit_errors = 0
    overlay_bits = 0
    payload_bit_errors = 0
    payload_bits = 0
    recoverable_packets = 0
    decoder_correct_payload_packets = 0
    decoder_corrected_packets = 0
    decoder_declared_failures = 0
    decoder_miscorrections = 0
    symbol_error_hist = np.zeros(RS_N + 1, dtype=np.int64)

    for start in range(0, packets, batch_size):
        n = min(batch_size, packets - start)
        messages = rng.integers(0, GF_SIZE, size=(n, RS_K), dtype=np.uint8)
        codewords = rs_encode(messages)
        data_increments = sixbit_to_d8psk_symbols(codewords)
        reference = np.zeros((n, 4), dtype=np.uint8)  # 12 reference bits
        increments = np.concatenate((reference, data_increments), axis=1)
        transmitted = differential_modulate(increments)

        ebno = 10 ** (ebno_db / 10)
        n0 = 1.0 / (3.0 * ebno)
        noise = math.sqrt(n0 / 2) * (
            rng.standard_normal(transmitted.shape) + 1j * rng.standard_normal(transmitted.shape)
        )
        received_symbols = differential_demodulate(transmitted + noise)[:, 4:]
        received_codewords = d8psk_symbols_to_sixbit(received_symbols)

        overlay_bit_errors += int(BIT_COUNTS_3[np.bitwise_xor(received_symbols, data_increments)].sum())
        overlay_bits += n * RS_N * 2 * 3
        raw_payload_error_counts = BIT_COUNTS_6[np.bitwise_xor(received_codewords[:, :RS_K], messages)].sum(axis=1)
        payload_bit_errors += int(raw_payload_error_counts.sum())
        payload_bits += n * RS_K * GF_BITS

        symbol_errors = np.count_nonzero(received_codewords != codewords, axis=1)
        recoverable = symbol_errors <= RS_T
        recoverable_packets += int(recoverable.sum())
        symbol_error_hist += np.bincount(symbol_errors, minlength=RS_N + 1)

        for row in range(n):
            if symbol_errors[row] == 0:
                decoder_correct_payload_packets += 1
                continue
            try:
                decoded, _, _ = RS_CODEC.decode(bytes(received_codewords[row]))
            except reedsolo.ReedSolomonError:
                decoder_declared_failures += 1
                continue
            if bytes(decoded) == bytes(messages[row]):
                decoder_correct_payload_packets += 1
                decoder_corrected_packets += 1
            else:
                decoder_miscorrections += 1

    return {
        "ebno_db": ebno_db,
        "packets": packets,
        "overlay_bits_tested": overlay_bits,
        "raw_overlay_bit_errors": overlay_bit_errors,
        "raw_overlay_ber": overlay_bit_errors / overlay_bits,
        "raw_overlay_ber_ci95_exact": exact_binomial_interval(overlay_bit_errors, overlay_bits),
        "security_payload_bits_tested": payload_bits,
        "raw_security_payload_bit_errors": payload_bit_errors,
        "raw_security_payload_ber": payload_bit_errors / payload_bits,
        "rs_bounded_distance_recoverable_packets": recoverable_packets,
        "rs_bounded_distance_recoverable_fraction": recoverable_packets / packets,
        "rs_bounded_distance_failure_fraction": 1 - recoverable_packets / packets,
        "actual_rs_decoder": {
            "correct_payload_packets": decoder_correct_payload_packets,
            "correct_payload_fraction": decoder_correct_payload_packets / packets,
            "corrected_nonzero_error_packets": decoder_corrected_packets,
            "declared_failure_packets": decoder_declared_failures,
            "declared_failure_fraction": decoder_declared_failures / packets,
            "miscorrected_payload_packets": decoder_miscorrections,
            "miscorrection_fraction": decoder_miscorrections / packets,
        },
        "symbol_error_histogram": {str(i): int(v) for i, v in enumerate(symbol_error_hist) if v},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--packets-per-ebno", type=int, default=10000)
    p.add_argument("--highest-ebno-packets", type=int, default=20000)
    p.add_argument("--ebno-db", type=float, nargs="+", default=[8, 10, 12, 14, 15, 16, 18])
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--export-waveform", type=Path)
    a = p.parse_args()
    if a.packets_per_ebno < 1000 or a.highest_ebno_packets < a.packets_per_ebno or a.batch_size < 1:
        p.error("use at least 1000 packets per Eb/No and a positive batch size")
    if sorted(a.ebno_db) != a.ebno_db or len(set(a.ebno_db)) != len(a.ebno_db):
        p.error("Eb/No values must be unique and ascending")

    rng = np.random.default_rng(a.seed)
    test_message = np.arange(RS_K, dtype=np.uint8) & 63
    test_codeword = rs_encode(test_message.reshape(1, -1))[0]
    syndromes = codeword_syndromes(test_codeword)
    library_codeword = bytes(RS_CODEC.encode(bytes(test_message)))
    corrupted_ten = test_codeword.copy()
    corrupted_ten[:RS_T] ^= 1
    decoded_ten, _, _ = RS_CODEC.decode(bytes(corrupted_ten))

    test_data_symbols = sixbit_to_d8psk_symbols(test_codeword.reshape(1, -1))
    test_increments = np.concatenate((np.zeros((1, 4), dtype=np.uint8), test_data_symbols), axis=1)
    noiseless_received = differential_demodulate(differential_modulate(test_increments))
    noiseless_ok = bool(np.array_equal(noiseless_received, test_increments))

    ppm_bits = rng.integers(0, 2, size=112, dtype=np.uint8)
    waveform = ppm_d8psk_baseband(ppm_bits, test_increments[0])
    samples_per_us = 8
    half = samples_per_us // 2
    nonzero_per_symbol = [
        int(np.count_nonzero(waveform[i * samples_per_us:(i + 1) * samples_per_us]))
        for i in range(112)
    ]
    ppm_ok = all(x == half for x in nonzero_per_symbol)

    if a.export_waveform:
        a.export_waveform.parent.mkdir(parents=True, exist_ok=True)
        waveform.astype(np.complex64).tofile(a.export_waveform)

    started = time.perf_counter()
    highest_ebno = max(a.ebno_db)
    results = [
        simulate_point(
            rng,
            x,
            a.highest_ebno_packets if x == highest_ebno else a.packets_per_ebno,
            a.batch_size,
        )
        for x in a.ebno_db
    ]
    elapsed = time.perf_counter() - started

    report = {
        "schema": SCHEMA,
        "scope": {
            "implemented": "software-only CABBA PPM/D8PSK complex-baseband feasibility over AWGN",
            "gnu_radio_used": False,
            "sdr_hardware_used": False,
            "rf_transmission_performed": False,
            "commercial_receiver_tested": False,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "reedsolo": importlib.metadata.version("reedsolo"),
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": a.seed,
            "packets_per_ebno": a.packets_per_ebno,
            "highest_ebno_packets": a.highest_ebno_packets,
            "ebno_db": a.ebno_db,
            "modulation": "differential 8-PSK, hard-decision",
            "channel": "complex AWGN, perfect timing/carrier",
            "adsb_data_symbols": 112,
            "overlay_bits": 336,
            "reference_bits": 12,
            "security_bits": 204,
            "parity_bits": 120,
            "rs_code": "RS(54,34) over GF(64)",
            "rs_decoder": "reedsolo 1.7.0 bounded-distance decoder",
            "rs_correction_radius_symbols": RS_T,
            "gf64_primitive_polynomial": "x^6 + x + 1 (0x43)",
            "gf64_generator_roots": "alpha^1 through alpha^20",
            "samples_per_microsecond_waveform_smoke_test": samples_per_us,
        },
        "implementation_choices_not_attributed_to_cabba_authors": [
            "GF(64) primitive polynomial and generator-root convention",
            "systematic RS symbol layout",
            "binary-to-D8PSK increment mapping",
            "differential phase initialization and hard-decision detector",
            "perfect synchronization and complex AWGN model",
        ],
        "correctness": {
            "gf64_field_cycle_has_63_nonzero_elements": GF_CYCLE == 63,
            "rs_codeword_syndromes_zero": all(x == 0 for x in syndromes),
            "reedsolo_encoder_matches_internal_encoder": library_codeword == bytes(test_codeword),
            "actual_decoder_corrects_deterministic_10_symbol_error_vector": bytes(decoded_ten) == bytes(test_message),
            "noiseless_overlay_round_trip": noiseless_ok,
            "ppm_waveform_structure": ppm_ok,
        },
        "waveform_smoke_test": {
            "complex_sample_count": int(waveform.size),
            "duration_microseconds": waveform.size / samples_per_us,
            "nonzero_samples": int(np.count_nonzero(waveform)),
            "export_path": str(a.export_waveform) if a.export_waveform else None,
        },
        "ebno_results": results,
        "runtime": {
            "wall_seconds_for_ber_sweep": elapsed,
            "packets_per_second": len(results) * a.packets_per_ebno / elapsed,
            "peak_rss_mib": peak_mib(),
        },
        "interpretation_limits": [
            "This is a complex-baseband software simulation, not an RF or GNU Radio experiment.",
            "Perfect carrier and symbol timing are assumed; synchronization failures are outside scope.",
            "The report distinguishes the theoretical <=10-symbol correction radius from actual reedsolo decoder success, declared failure, and miscorrection.",
            "The GF(64), bit mapping, and differential conventions are explicit reproduction choices because a bit-exact authoritative specification was not available.",
            "A zero observed BER is bounded by the reported finite-sample confidence interval and is not proof of zero error probability.",
            "Results do not establish RTCA conformance, commercial-receiver compatibility, certified airborne performance, or safe operational RF behavior.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
