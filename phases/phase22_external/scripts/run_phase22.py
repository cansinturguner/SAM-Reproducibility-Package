#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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
from collections import defaultdict
from pathlib import Path

import numpy as np

from phase14_core import C, canonical_message, ecef, finite, fuse, load_biases, load_sensors, rank3, sha256_file, trust_bootstrap, truthy

EXPECTED = {
    "observations": "5ff68c7e402caa183678c03f4d23ba45b63bc96fa1177f8ce7e4fb530c45dd58",
    "sensors": "998a63f5fc89fa41fd1a37468431da96f355812054e7bca8b2a4f4db0ba47d1b",
    "aircraft": "70156a0865e655f4fb470e5814fd153708ac9f97ef193b70ebf3f4a5d84e1893",
}


def peak_mib():
    x = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return x / (1024 * 1024) if sys.platform == "darwin" else x / 1024


def dist(values):
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return {"n": 0}
    return {
        "n": int(x.size),
        "signed_median_ns": float(np.median(x)),
        "absolute_q50_ns": float(np.quantile(np.abs(x), .50)),
        "absolute_q90_ns": float(np.quantile(np.abs(x), .90)),
        "absolute_q95_ns": float(np.quantile(np.abs(x), .95)),
        "absolute_q99_ns": float(np.quantile(np.abs(x), .99)),
        "within_500ns_fraction": float(np.mean(np.abs(x) <= 500)),
        "within_1000ns_fraction": float(np.mean(np.abs(x) <= 1000)),
    }


def load_trusted(path):
    out = set()
    total = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            total += 1
            if truthy(row.get("trusted")):
                out.add(str(row.get("aircraft", "")).strip())
    return out, total


def parse_measurements(raw, allowed):
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            ts = finite(item[1])
            if sid in allowed and ts is not None:
                dedup.setdefault(sid, ts)
    return sorted(dedup.items())


def bootstrap_aircraft(stats_by_aircraft, replicates, seed):
    aircraft = sorted(stats_by_aircraft)
    rng = random.Random(seed)
    availability = []
    aircraft_medians = []
    for _ in range(replicates):
        sample = [aircraft[rng.randrange(len(aircraft))] for _ in aircraft]
        eligible = sum(stats_by_aircraft[a]["eligible"] for a in sample)
        supported = sum(stats_by_aircraft[a]["supported"] for a in sample)
        medians = []
        for a in sample:
            residuals = stats_by_aircraft[a]["residuals"]
            if residuals:
                medians.append(float(np.median(np.abs(np.asarray(residuals)))))
        availability.append(supported / eligible if eligible else float("nan"))
        aircraft_medians.append(float(np.median(medians)) if medians else float("nan"))
    availability = np.asarray([x for x in availability if math.isfinite(x)])
    aircraft_medians = np.asarray([x for x in aircraft_medians if math.isfinite(x)])
    return {
        "method": "aircraft-cluster bootstrap with replacement",
        "replicates": replicates,
        "seed": seed,
        "availability_weighted_by_rows": {
            "ci95_low": float(np.quantile(availability, .025)),
            "ci95_high": float(np.quantile(availability, .975)),
        },
        "median_of_aircraft_level_median_absolute_residual_ns": {
            "ci95_low": float(np.quantile(aircraft_medians, .025)),
            "ci95_high": float(np.quantile(aircraft_medians, .975)),
        },
    }


def primary_summary(path):
    p = json.loads(path.read_text(encoding="utf-8"))
    return {
        "availability": float(p["availability"]["fraction"]),
        "pair_residual_absolute_q50_ns": float(p["pair_residuals"]["absolute_q50_ns"]),
        "pair_residual_absolute_q95_ns": float(p["pair_residuals"]["absolute_q95_ns"]),
        "usable_rows": int(p["counts"]["usable_test_rows"]),
        "eligible_rows": int(p["counts"]["test_original_ge4_rows"]),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", type=Path, required=True)
    p.add_argument("--sensors", type=Path, required=True)
    p.add_argument("--aircraft", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--primary", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--bootstrap-replicates", type=int, default=2000)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()
    if a.bootstrap_replicates < 2000:
        p.error("--bootstrap-replicates must be at least 2000")

    hashes = {
        "observations": sha256_file(a.observations),
        "sensors": sha256_file(a.sensors),
        "aircraft": sha256_file(a.aircraft),
        "calibration": sha256_file(a.calibration),
        "primary": sha256_file(a.primary),
    }
    if not a.skip_hash_check:
        for key in ("observations", "sensors", "aircraft"):
            if hashes[key] != EXPECTED[key]:
                raise SystemExit(f"Unexpected subset-2 {key} SHA-256: {hashes[key]}")

    trusted, aircraft_table_rows = load_trusted(a.aircraft)
    good_sensors = load_sensors(a.sensors)
    biases = load_biases(a.calibration)
    modeled = set(good_sensors) & set(biases)
    root_key, trust_ok = trust_bootstrap(a.seed)
    if not trust_ok:
        raise SystemExit("Frozen cached trust bootstrap failed")

    counts = {
        "rows_read": 0, "trusted_aircraft_rows": 0, "trusted_good_ge3_rows": 0,
        "external_eligible_good_ge4_rows": 0, "physical_supported_rows": 0,
        "fewer_than_4_modeled_receivers": 0, "geometry_rank_below_3": 0,
        "hmac_verified_rows": 0, "VERIFIED": 0,
        "INSUFFICIENT_EVIDENCE": 0, "CONFLICTING": 0,
    }
    residuals = []
    by_receiver_count = defaultdict(list)
    by_aircraft = defaultdict(lambda: {"eligible": 0, "supported": 0, "residuals": []})
    start = time.perf_counter()
    with a.observations.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            counts["rows_read"] += 1
            aircraft = str(row.get("aircraft", "")).strip()
            if aircraft not in trusted:
                continue
            counts["trusted_aircraft_rows"] += 1
            try:
                good_ms = parse_measurements(row["measurements"], set(good_sensors))
            except (json.JSONDecodeError, TypeError):
                continue
            if len(good_ms) < 3:
                continue
            counts["trusted_good_ge3_rows"] += 1
            if len(good_ms) < 4:
                continue
            counts["external_eligible_good_ge4_rows"] += 1
            by_aircraft[aircraft]["eligible"] += 1

            msg = canonical_message(row)
            interval = int(float(row.get("timeAtServer") or 0.0))
            key = hmac.new(root_key, b"interval:" + interval.to_bytes(8, "big", signed=False), hashlib.sha3_256).digest()[:16]
            tag = hmac.new(key, msg, hashlib.sha3_256).digest()[:16]
            crypto = "VERIFIED" if hmac.compare_digest(tag, hmac.new(key, msg, hashlib.sha3_256).digest()[:16]) else "CONFLICTING"
            counts["hmac_verified_rows"] += crypto == "VERIFIED"

            modeled_ms = [(sid, ts) for sid, ts in good_ms if sid in modeled]
            physical = "INSUFFICIENT_EVIDENCE"
            if len(modeled_ms) < 4:
                counts["fewer_than_4_modeled_receivers"] += 1
            elif not rank3([good_sensors[sid] for sid, _ in modeled_ms]):
                counts["geometry_rank_below_3"] += 1
            else:
                lat, lon = finite(row["latitude"]), finite(row["longitude"])
                alt = finite(row["geoAltitude"])
                if alt is None:
                    alt = finite(row["baroAltitude"])
                if None not in (lat, lon, alt):
                    xyz = ecef(lat, lon, alt)
                    delays = {sid: float(np.linalg.norm(xyz - good_sensors[sid]) / C * 1e9) for sid, _ in modeled_ms}
                    corrected = {sid: ts - biases[sid] for sid, ts in modeled_ms}
                    ref = modeled_ms[0][0]
                    row_residuals = [(corrected[sid] - corrected[ref]) - (delays[sid] - delays[ref]) for sid, _ in modeled_ms[1:]]
                    residuals.extend(row_residuals)
                    by_aircraft[aircraft]["residuals"].extend(row_residuals)
                    bucket = str(len(modeled_ms)) if len(modeled_ms) < 8 else "8+"
                    by_receiver_count[bucket].extend(row_residuals)
                    physical = "VERIFIED"
                    counts["physical_supported_rows"] += 1
                    by_aircraft[aircraft]["supported"] += 1
            state = fuse(crypto, physical, "VERIFIED")
            counts[state] += 1
    wall = time.perf_counter() - start

    eligible = counts["external_eligible_good_ge4_rows"]
    availability = counts["physical_supported_rows"] / eligible if eligible else 0.0
    external_residuals = dist(residuals)
    bootstrap = bootstrap_aircraft(by_aircraft, a.bootstrap_replicates, a.seed)
    bootstrap["availability_weighted_by_rows"]["estimate"] = availability
    aircraft_medians = [float(np.median(np.abs(np.asarray(v["residuals"])))) for v in by_aircraft.values() if v["residuals"]]
    bootstrap["median_of_aircraft_level_median_absolute_residual_ns"]["estimate"] = float(np.median(aircraft_medians))
    primary = primary_summary(a.primary)

    report = {
        "schema": "sam.phase22.external-validation.v1",
        "scope": {
            "implemented": "frozen subset-1 SAM physical, cryptographic, cached-trust and fusion policy applied to LocaRDS subset 2",
            "not_implemented": ["subset-2 recalibration or threshold selection", "authenticator captured from RF", "RF waveform processing", "certified airborne hardware"],
        },
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "processor": platform.processor(), "python": platform.python_version(), "numpy": np.__version__, "logical_cpu_count": os.cpu_count()},
        "configuration": {
            "seed": a.seed, "clock_model": "frozen subset-1 bias_only", "minimum_modeled_receivers": 4,
            "receiver_geometry_rank": 3, "geometry_ratio_minimum": None, "minimum_baseline_m": None,
            "bootstrap_replicates": a.bootstrap_replicates, "trust_mode": "valid cached trust",
            "fusion_policy": "VERIFIED requires crypto + trust + physical; conflict dominates",
        },
        "inputs": {"paths": {"observations": str(a.observations), "sensors": str(a.sensors), "aircraft": str(a.aircraft), "calibration": str(a.calibration), "primary": str(a.primary)}, "sha256": hashes, "dataset_doi": "10.5281/zenodo.4739276"},
        "metadata": {"aircraft_table_rows": aircraft_table_rows, "trusted_aircraft_identifiers": len(trusted), "sensor_table_rows": 716, "good_sensors": len(good_sensors), "frozen_modeled_good_sensors": len(modeled)},
        "counts": counts,
        "availability": {"denominator": "trusted subset-2 rows with at least four released-good receivers", "numerator": "rows supported by at least four frozen-modeled receivers and rank-three geometry", "fraction": availability},
        "pair_residuals": external_residuals,
        "aircraft_clustered_confidence_intervals": bootstrap,
        "by_modeled_receiver_count": {k: dist(v) for k, v in sorted(by_receiver_count.items())},
        "primary_subset1_comparison": {
            "subset1": primary,
            "subset2": {"availability": availability, "pair_residual_absolute_q50_ns": external_residuals["absolute_q50_ns"], "pair_residual_absolute_q95_ns": external_residuals["absolute_q95_ns"], "usable_rows": counts["physical_supported_rows"], "eligible_rows": eligible},
            "subset2_minus_subset1": {"availability": availability - primary["availability"], "pair_residual_absolute_q50_ns": external_residuals["absolute_q50_ns"] - primary["pair_residual_absolute_q50_ns"], "pair_residual_absolute_q95_ns": external_residuals["absolute_q95_ns"] - primary["pair_residual_absolute_q95_ns"]},
        },
        "runtime": {"wall_seconds": wall, "rows_read_per_second": counts["rows_read"] / wall, "eligible_rows_per_second": eligible / wall, "peak_rss_mib": peak_mib()},
        "interpretation_limits": [
            "Subset 2 is an independent released LocaRDS data partition, but it uses the same published sensor metadata table as subset 1.",
            "No subset-2 observation was used to update the frozen subset-1 clock parameters or decision rules.",
            "Cryptographic authenticators are deterministic synthetic surrogates bound to real subset-2 observations.",
            "Availability measures evidence support and is not an attack-detection rate.",
            "Results characterize the recorded Python/Mac prototype and not certified avionics hardware.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

