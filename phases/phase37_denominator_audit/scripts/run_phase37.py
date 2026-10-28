#!/usr/bin/env python3
"""Physical-evidence denominator, artifact, and sensitivity audit."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import platform
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
P25 = ROOT / "phases" / "phase25a_physical_decision" / "scripts"
P31 = ROOT / "phases" / "phase31_receiver_integrity" / "scripts"
sys.path[:0] = [str(P25), str(P31)]
from physical_core import C, destination_point, deterministic_bearing, ecef, load_biases, load_sensors, residuals_for_claimed_position, row_score, sha256_file, truthy  # noqa: E402
from run_phase31 import build_context, core as threshold_core, load_trusted  # noqa: E402


DISTANCES = (0.0, 100.0, 250.0, 400.0, 500.0, 750.0, 1000.0, 2000.0, 5000.0, 10000.0)


def q(values: list[float], probability: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), probability))


def artifact_flags(context: dict, tolerance_ns: float, receiver: str) -> dict:
    ids = context["sensor_ids"]
    errors = context["errors_ns"]
    residuals = errors[1:] - errors[0]
    nearest = np.rint(residuals / 1e9)
    near_nonzero_integer = bool(np.any((nearest != 0) & (np.abs(residuals - nearest * 1e9) <= tolerance_ns)))
    contains = receiver in ids
    reference_is = ids[0] == receiver
    largest_index = int(np.argmax(np.abs(residuals))) + 1
    largest_pair_involves = reference_is or ids[largest_index] == receiver
    return {
        "contains_receiver": contains,
        "decision_reference_is_receiver": reference_is,
        "largest_absolute_reference_pair_involves_receiver": largest_pair_involves,
        "near_nonzero_integer_second": near_nonzero_integer,
    }


def summarize_artifacts(flags: list[dict]) -> dict:
    total = len(flags)
    def count(key): return sum(bool(item[key]) for item in flags)
    both = sum(item["contains_receiver"] and item["near_nonzero_integer_second"] for item in flags)
    neither = sum(not item["contains_receiver"] and not item["near_nonzero_integer_second"] for item in flags)
    return {
        "conflicting_rows": total,
        "contains_receiver_134": count("contains_receiver"),
        "decision_reference_is_134": count("decision_reference_is_receiver"),
        "largest_absolute_reference_pair_involves_134": count("largest_absolute_reference_pair_involves_receiver"),
        "near_nonzero_integer_second_pair_residual": count("near_nonzero_integer_second"),
        "contains_134_and_near_integer_second": both,
        "neither_contains_134_nor_near_integer_second": neither,
        "fractions_among_conflicts": {
            "contains_receiver_134": count("contains_receiver") / total if total else None,
            "near_nonzero_integer_second": count("near_nonzero_integer_second") / total if total else None,
            "both": both / total if total else None,
            "neither": neither / total if total else None,
        },
    }


def cluster_bootstrap(by_aircraft: dict, distances: tuple[float, ...], replicates: int, seed: int) -> dict:
    aircraft = sorted(by_aircraft)
    rng = np.random.default_rng(seed)
    estimates = {distance: [] for distance in distances}
    net = {distance: [] for distance in distances if distance != 0.0}
    for _ in range(replicates):
        sample = rng.choice(aircraft, size=len(aircraft), replace=True)
        totals = {distance: [0, 0] for distance in distances}
        for ac in sample:
            record = by_aircraft[str(ac)]
            for distance in distances:
                totals[distance][0] += record[distance][0]
                totals[distance][1] += record[distance][1]
        fractions = {distance: totals[distance][1] / totals[distance][0] for distance in distances}
        for distance in distances:
            estimates[distance].append(fractions[distance])
            if distance != 0.0:
                net[distance].append(fractions[distance] - fractions[0.0])
    return {
        str(distance): {
            "conflict_fraction_ci95": [q(estimates[distance], 0.025), q(estimates[distance], 0.975)],
            "baseline_adjusted_gain_ci95": None if distance == 0.0 else [q(net[distance], 0.025), q(net[distance], 0.975)],
        }
        for distance in distances
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--subset1-sensors", type=Path, required=True)
    p.add_argument("--subset2-observations", type=Path, required=True)
    p.add_argument("--subset2-sensors", type=Path, required=True)
    p.add_argument("--subset2-aircraft", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--decision-model", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--bootstrap-replicates", type=int, default=2000)
    p.add_argument("--integer-second-tolerance-ns", type=float, default=10000.0)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()
    if a.bootstrap_replicates < 100:
        p.error("use at least 100 bootstrap replicates")
    started = time.perf_counter()
    model = json.loads(a.decision_model.read_text(encoding="utf-8"))
    threshold = float(model["threshold_ns"])
    if not a.skip_hash_check:
        expected = model.get("input_sha256", {})
        actual = {"selected": sha256_file(a.selected), "sensors": sha256_file(a.subset1_sensors), "calibration": sha256_file(a.calibration)}
        for key, value in actual.items():
            if expected.get(key) != value:
                raise SystemExit(f"{key} SHA-256 mismatch")
    sensors1 = load_sensors(a.subset1_sensors)
    sensors2 = load_sensors(a.subset2_sensors)
    biases = load_biases(a.calibration)
    modeled1, modeled2 = set(sensors1) & set(biases), set(sensors2) & set(biases)

    total_test = eligible1 = available1 = conflicts1 = 0
    flags1 = []
    attack_counts = {distance: Counter() for distance in DISTANCES}
    by_aircraft = defaultdict(lambda: {distance: [0, 0] for distance in DISTANCES})
    with gzip.open(a.selected, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("split", "").strip().lower() != "test":
                continue
            total_test += 1
            if not truthy(row.get("eligible_ge4")):
                continue
            eligible1 += 1
            context, _ = build_context(row, sensors1, biases, modeled1, "goodMeasurements")
            if context is None:
                continue
            available1 += 1
            baseline_score = float(np.median(np.abs(context["errors_ns"][1:] - context["errors_ns"][0])))
            if baseline_score > threshold:
                conflicts1 += 1
                flags1.append(artifact_flags(context, a.integer_second_tolerance_ns, "134"))
            ac = str(row.get("aircraft", ""))
            lat = float(row["latitude"]); lon = float(row["longitude"])
            alt_text = row.get("geoAltitude") or row.get("baroAltitude")
            alt = float(alt_text)
            inputs = {
                "measurements": list(zip(context["sensor_ids"], [0.0] * len(context["sensor_ids"]))),
                "position": (lat, lon, alt),
                "corrected": {sid: float(error + np.linalg.norm(ecef(lat, lon, alt) - sensors1[sid]) / C * 1e9) for sid, error in zip(context["sensor_ids"], context["errors_ns"])},
            }
            for distance in DISTANCES:
                bearing = deterministic_bearing(a.seed, str(row.get("id", "")), distance)
                shifted_lat, shifted_lon = destination_point(lat, lon, distance, bearing)
                residuals = residuals_for_claimed_position(inputs, (shifted_lat, shifted_lon, alt), sensors1)
                conflict = row_score(residuals) > threshold
                attack_counts[distance]["total"] += 1
                attack_counts[distance]["conflict"] += int(conflict)
                by_aircraft[ac][distance][0] += 1
                by_aircraft[ac][distance][1] += int(conflict)

    trusted = load_trusted(a.subset2_aircraft)
    trusted_rows2 = eligible2 = available2 = conflicts2 = 0
    flags2 = []
    with a.subset2_observations.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("aircraft", "")).strip() not in trusted:
                continue
            trusted_rows2 += 1
            try:
                measurements = threshold_core.measurements(row.get("measurements", "[]"), set(sensors2))
            except (json.JSONDecodeError, TypeError):
                continue
            if len(measurements) < 4:
                continue
            eligible2 += 1
            context, _ = build_context(row, sensors2, biases, modeled2, "measurements")
            if context is None:
                continue
            available2 += 1
            score = float(np.median(np.abs(context["errors_ns"][1:] - context["errors_ns"][0])))
            if score > threshold:
                conflicts2 += 1
                flags2.append(artifact_flags(context, a.integer_second_tolerance_ns, "134"))

    bootstrap = cluster_bootstrap(by_aircraft, DISTANCES, a.bootstrap_replicates, a.seed)
    baseline_fraction = attack_counts[0.0]["conflict"] / attack_counts[0.0]["total"]
    sensitivity = {}
    for distance in DISTANCES:
        fraction = attack_counts[distance]["conflict"] / attack_counts[distance]["total"]
        sensitivity[str(distance)] = {
            "available_rows": attack_counts[distance]["total"],
            "conflicting_rows": attack_counts[distance]["conflict"],
            "raw_conflict_fraction": fraction,
            "benign_baseline_conflict_fraction": baseline_fraction,
            "baseline_adjusted_gain": fraction - baseline_fraction,
            **bootstrap[str(distance)],
        }

    report = {
        "schema": "sam.phase37.denominator-audit.v1",
        "scope": "denominator transparency, conflict-tail attribution, and baseline-adjusted position-bias sensitivity",
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": platform.python_version(), "numpy": np.__version__},
        "configuration": {"seed": a.seed, "threshold_ns": threshold, "bootstrap_replicates": a.bootstrap_replicates, "integer_second_tolerance_ns": a.integer_second_tolerance_ns, "position_bias_m": list(DISTANCES)},
        "inputs": {"sha256": {"selected": sha256_file(a.selected), "subset1_sensors": sha256_file(a.subset1_sensors), "subset2_observations": sha256_file(a.subset2_observations), "subset2_sensors": sha256_file(a.subset2_sensors), "subset2_aircraft": sha256_file(a.subset2_aircraft), "calibration": sha256_file(a.calibration), "decision_model": sha256_file(a.decision_model)}},
        "availability_denominators": {
            "subset1": {"complete_test_partition_rows": total_test, "originally_eligible_rows": eligible1, "physical_available_rows": available1, "conditional_availability_among_originally_eligible": available1 / eligible1, "end_to_end_yield_from_complete_test_partition": available1 / total_test},
            "subset2": {"trusted_rows": trusted_rows2, "trusted_good_ge4_rows": eligible2, "physical_available_rows": available2, "conditional_availability_among_trusted_good_ge4": available2 / eligible2, "end_to_end_yield_from_trusted_rows": available2 / trusted_rows2},
        },
        "benign_reference_conflict_attribution": {"subset1": summarize_artifacts(flags1), "subset2": summarize_artifacts(flags2)},
        "position_bias_sensitivity": sensitivity,
        "runtime": {"wall_seconds": time.perf_counter() - started},
        "interpretation_limits": [
            "Conflict attribution categories overlap and do not establish the cause of a timestamp anomaly.",
            "Integer-second proximity is audited without timestamp wrapping, correction, or row deletion.",
            "Receiver 134 involvement is an association audit, not proof that receiver 134 caused the conflict.",
            "Position offsets are controlled synthetic perturbations; sensitivity is not operational detection accuracy.",
            "Bootstrap intervals resample aircraft and retain within-aircraft dependence.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"availability_denominators": report["availability_denominators"], "benign_reference_conflict_attribution": report["benign_reference_conflict_attribution"], "position_bias_sensitivity": report["position_bias_sensitivity"]}, indent=2))


if __name__ == "__main__":
    main()

