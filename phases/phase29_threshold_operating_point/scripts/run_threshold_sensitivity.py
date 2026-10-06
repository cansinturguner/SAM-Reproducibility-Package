#!/usr/bin/env python3
"""Development-defined threshold operating-point sensitivity for SAM."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

PHASE27_SCRIPTS = Path(
    os.environ.get(
        "SAM_PHASE27_SCRIPTS",
        str(
            Path(__file__).resolve().parents[2]
            / "phase27_threshold_aware_integration"
            / "scripts"
        ),
    )
)
if not PHASE27_SCRIPTS.exists():
    raise SystemExit(
        "Phase 27 is required. Expected: "
        "phases/phase27_threshold_aware_integration/scripts"
    )
sys.path.insert(0, str(PHASE27_SCRIPTS))
import threshold_core as core  # noqa: E402


DEFAULT_TARGETS = (0.95, 0.975, 0.99, 0.995, 0.999)
DEFAULT_BIASES_M = (100, 250, 400, 500, 750, 1000, 2000, 5000, 10000)
EARTH_RADIUS_M = 6_371_008.8


def aircraft_group(aircraft: str, seed: int, calibration_percent: int) -> str:
    token = f"{seed}|{aircraft}".encode()
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    return "calibration" if bucket < calibration_percent else "validation"


def physical_context(row, sensors, biases, modeled):
    latitude = core.finite(row.get("latitude"))
    longitude = core.finite(row.get("longitude"))
    altitude = core.finite(row.get("geoAltitude"))
    if altitude is None:
        altitude = core.finite(row.get("baroAltitude"))
    if None in (latitude, longitude, altitude):
        return None, "missing_position_or_altitude"
    try:
        observed = core.measurements(row.get("goodMeasurements", "[]"), modeled)
    except (json.JSONDecodeError, TypeError):
        observed = []
    if len(observed) < 4:
        return None, "fewer_than_4_modeled_receivers"
    if not core.rank3([sensors[sensor_id] for sensor_id, _ in observed]):
        return None, "rank_below_3"

    aircraft_xyz = core.ecef(latitude, longitude, altitude)
    delays = np.asarray(
        [
            np.linalg.norm(aircraft_xyz - sensors[sensor_id]) / core.C * 1e9
            for sensor_id, _ in observed
        ],
        dtype=float,
    )
    corrected = np.asarray(
        [timestamp - biases[sensor_id] for sensor_id, timestamp in observed],
        dtype=float,
    )
    residuals = (corrected[1:] - corrected[0]) - (delays[1:] - delays[0])
    return {
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "sensor_ids": [sensor_id for sensor_id, _ in observed],
        "nominal_delays_ns": delays,
        "residuals_ns": residuals,
        "score_ns": float(np.median(np.abs(residuals))),
    }, None


def deterministic_bearing(seed: int, row_id: str, distance_m: float) -> float:
    """Bit-exact Phase 25B deterministic bearing, returned in radians."""
    digest = hashlib.sha256(
        f"{seed}|{row_id}|{distance_m:.6f}".encode()
    ).digest()
    unit = int.from_bytes(digest[:8], "big") / 2**64
    return 2.0 * math.pi * unit


def destination(lat_deg: float, lon_deg: float, distance_m: float, bearing_rad: float):
    """Bit-exact Phase 25A/25B spherical destination-point calculation."""
    if distance_m == 0:
        return lat_deg, lon_deg
    angular = distance_m / EARTH_RADIUS_M
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing_rad)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    lon2 = (lon2 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
    return math.degrees(lat2), math.degrees(lon2)


def score_for_claimed_position(context, sensors, latitude, longitude, altitude):
    claimed_xyz = core.ecef(latitude, longitude, altitude)
    claimed_delays = np.asarray(
        [
            np.linalg.norm(claimed_xyz - sensors[sensor_id]) / core.C * 1e9
            for sensor_id in context["sensor_ids"]
        ],
        dtype=float,
    )
    nominal_pair = context["nominal_delays_ns"][1:] - context["nominal_delays_ns"][0]
    claimed_pair = claimed_delays[1:] - claimed_delays[0]
    attacked_residuals = context["residuals_ns"] + nominal_pair - claimed_pair
    return float(np.median(np.abs(attacked_residuals)))


def fixed_ground_score(context, sensors, spoofer_xyz):
    spoofer_delays = np.asarray(
        [
            np.linalg.norm(spoofer_xyz - sensors[sensor_id]) / core.C * 1e9
            for sensor_id in context["sensor_ids"]
        ],
        dtype=float,
    )
    nominal_pair = context["nominal_delays_ns"][1:] - context["nominal_delays_ns"][0]
    spoofer_pair = spoofer_delays[1:] - spoofer_delays[0]
    attacked_residuals = context["residuals_ns"] + spoofer_pair - nominal_pair
    return float(np.median(np.abs(attacked_residuals)))


def higher_quantile(values: np.ndarray, q: float) -> float:
    return float(np.quantile(values, q, method="higher"))


def cluster_ci(scores: np.ndarray, aircraft: np.ndarray, threshold: float, seed: int):
    unique, inverse = np.unique(aircraft, return_inverse=True)
    totals = np.bincount(inverse)
    conflicts = np.bincount(inverse, weights=(scores > threshold).astype(float))
    rng = np.random.default_rng(seed)
    estimates = np.empty(2000, dtype=float)
    for index in range(2000):
        draw = rng.integers(0, len(unique), size=len(unique))
        estimates[index] = conflicts[draw].sum() / totals[draw].sum()
    estimate = float(np.mean(scores > threshold))
    low, high = np.quantile(estimates, [0.025, 0.975])
    return {
        "estimate": estimate,
        "ci95_low": float(low),
        "ci95_high": float(high),
        "replicates": 2000,
        "seed": seed,
        "aircraft": int(len(unique)),
        "method": "aircraft-cluster bootstrap with replacement; row-weighted conflict fraction",
    }


def paired_result(benign_scores: np.ndarray, attacked_scores: np.ndarray, threshold: float):
    benign_conflict = benign_scores > threshold
    attacked_conflict = attacked_scores > threshold
    baseline_consistent = ~benign_conflict
    baseline_conflicting = benign_conflict
    return {
        "attacked_conflict_fraction_all_available": float(np.mean(attacked_conflict)),
        "consistent_to_conflicting_fraction": float(
            np.mean(attacked_conflict[baseline_consistent])
        ) if np.any(baseline_consistent) else None,
        "conflicting_to_consistent_fraction": float(
            np.mean(~attacked_conflict[baseline_conflicting])
        ) if np.any(baseline_conflicting) else None,
        "attacked_conflicting_rows": int(np.sum(attacked_conflict)),
        "consistent_to_conflicting_rows": int(
            np.sum(attacked_conflict & baseline_consistent)
        ),
        "conflicting_to_consistent_rows": int(
            np.sum((~attacked_conflict) & baseline_conflicting)
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--sensors", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--decision-model", type=Path, required=True)
    parser.add_argument("--phase25b-report", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--targets", type=float, nargs="+", default=DEFAULT_TARGETS)
    parser.add_argument("--biases-m", type=float, nargs="+", default=DEFAULT_BIASES_M)
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args()

    targets = sorted(set(args.targets))
    if any(not 0 < value < 1 for value in targets):
        parser.error("all targets must be strictly between zero and one")
    if 0.99 not in targets:
        parser.error("targets must include the frozen 0.99 operating point")
    biases_m = sorted(set(float(value) for value in args.biases_m))
    if not biases_m or any(value <= 0 for value in biases_m):
        parser.error("position biases must be positive")

    started = time.perf_counter()
    model = core.load_decision_model(args.decision_model)
    input_hashes = core.verify_model_inputs(
        model, args.selected, args.sensors, args.calibration, args.skip_hash_check
    )
    seed = int(model["seed"])
    calibration_percent = int(model["calibration_percent"])
    frozen_threshold = float(model["threshold_ns"])
    sensors = core.load_sensors(args.sensors)
    receiver_biases = core.load_biases(args.calibration)
    modeled = set(sensors) & set(receiver_biases)
    # Frozen Phase 25B ground-spoofer location: the geodetic projection of the
    # modeled-receiver ECEF centroid, with height fixed to zero.
    spoofer_xyz = core.ecef(48.757894483589844, 8.536577272001962, 0.0)

    development_validation_scores = []
    test_scores = []
    test_aircraft = []
    attacked = {distance: [] for distance in biases_m}
    ground_scores = []
    counts = {
        "development_validation_original_ge4": 0,
        "development_validation_available": 0,
        "subset1_test_original_ge4": 0,
        "subset1_test_available": 0,
        "subset1_test_unavailable": 0,
    }
    unavailable_reasons = {}

    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            split = row.get("split", "").strip().lower()
            if not core.truthy(row.get("eligible_ge4")):
                continue
            aircraft = str(row.get("aircraft", "")).strip()
            is_dev_validation = (
                split == "development"
                and aircraft_group(aircraft, seed, calibration_percent) == "validation"
            )
            is_test = split == "test"
            if not (is_dev_validation or is_test):
                continue
            if is_dev_validation:
                counts["development_validation_original_ge4"] += 1
            else:
                counts["subset1_test_original_ge4"] += 1

            context, reason = physical_context(row, sensors, receiver_biases, modeled)
            if context is None:
                if is_test:
                    counts["subset1_test_unavailable"] += 1
                    unavailable_reasons[reason] = unavailable_reasons.get(reason, 0) + 1
                continue
            if is_dev_validation:
                counts["development_validation_available"] += 1
                development_validation_scores.append(context["score_ns"])
                continue

            counts["subset1_test_available"] += 1
            test_scores.append(context["score_ns"])
            test_aircraft.append(aircraft)
            row_id = str(row.get("id", f"row-{counts['subset1_test_available']}"))
            for distance in biases_m:
                bearing = deterministic_bearing(seed, row_id, distance)
                shifted_lat, shifted_lon = destination(
                    context["latitude"], context["longitude"], distance, bearing
                )
                attacked[distance].append(
                    score_for_claimed_position(
                        context,
                        sensors,
                        shifted_lat,
                        shifted_lon,
                        context["altitude"],
                    )
                )
            ground_scores.append(fixed_ground_score(context, sensors, spoofer_xyz))

    dev_scores = np.asarray(development_validation_scores, dtype=float)
    benign_scores = np.asarray(test_scores, dtype=float)
    aircraft_array = np.asarray(test_aircraft, dtype=str)
    ground_array = np.asarray(ground_scores, dtype=float)
    attacked_arrays = {
        distance: np.asarray(values, dtype=float) for distance, values in attacked.items()
    }
    if len(dev_scores) == 0 or len(benign_scores) == 0:
        raise SystemExit("No usable development-validation or test score was produced")

    operating_points = []
    csv_rows = []
    for target in targets:
        threshold = higher_quantile(dev_scores, target)
        is_frozen_target = math.isclose(target, 0.99, rel_tol=0.0, abs_tol=1e-12)
        if is_frozen_target and not math.isclose(
            threshold, frozen_threshold, rel_tol=0.0, abs_tol=1e-9
        ):
            raise SystemExit(
                f"Frozen q99 threshold mismatch: recomputed={threshold} model={frozen_threshold}"
            )
        benign_conflicts = int(np.sum(benign_scores > threshold))
        point = {
            "target_development_benign_consistency": target,
            "threshold_ns": threshold,
            "is_frozen_operating_point": is_frozen_target,
            "development_validation": {
                "available_rows": int(len(dev_scores)),
                "consistent_rows": int(np.sum(dev_scores <= threshold)),
                "conflicting_rows": int(np.sum(dev_scores > threshold)),
                "empirical_consistency_fraction": float(np.mean(dev_scores <= threshold)),
            },
            "subset1_benign_reference": {
                "available_rows": int(len(benign_scores)),
                "consistent_rows": int(len(benign_scores) - benign_conflicts),
                "conflicting_rows": benign_conflicts,
                "conflict_fraction": float(benign_conflicts / len(benign_scores)),
                "aircraft_cluster_conflict_fraction_ci95": cluster_ci(
                    benign_scores, aircraft_array, threshold, seed
                ),
            },
            "position_bias": {},
            "fixed_ground_spoofer": paired_result(
                benign_scores, ground_array, threshold
            ),
        }
        for distance in biases_m:
            result = paired_result(benign_scores, attacked_arrays[distance], threshold)
            point["position_bias"][str(distance)] = result
            csv_rows.append(
                {
                    "target_development_benign_consistency": target,
                    "threshold_ns": threshold,
                    "scenario": "position_bias",
                    "magnitude_m": distance,
                    "subset1_benign_conflict_fraction": benign_conflicts / len(benign_scores),
                    **{
                        key: result[key]
                        for key in (
                            "attacked_conflict_fraction_all_available",
                            "consistent_to_conflicting_fraction",
                            "conflicting_to_consistent_fraction",
                        )
                    },
                }
            )
        ground = point["fixed_ground_spoofer"]
        csv_rows.append(
            {
                "target_development_benign_consistency": target,
                "threshold_ns": threshold,
                "scenario": "fixed_ground_spoofer",
                "magnitude_m": "",
                "subset1_benign_conflict_fraction": benign_conflicts / len(benign_scores),
                **{
                    key: ground[key]
                    for key in (
                        "attacked_conflict_fraction_all_available",
                        "consistent_to_conflicting_fraction",
                        "conflicting_to_consistent_fraction",
                    )
                },
            }
        )
        operating_points.append(point)

    phase25b_crosscheck = None
    if args.phase25b_report:
        previous = json.loads(args.phase25b_report.read_text(encoding="utf-8"))
        frozen_point = next(item for item in operating_points if item["is_frozen_operating_point"])
        comparisons = {}
        for distance in biases_m:
            key = str(distance)
            expected = previous["position_bias_sensitivity"][key]["PHYSICALLY_CONFLICTING"]
            observed = frozen_point["position_bias"][key]["attacked_conflicting_rows"]
            comparisons[key] = {"expected": int(expected), "observed": int(observed), "match": int(expected) == int(observed)}
        expected_ground = previous["fixed_ground_spoofer_fake_track"]["PHYSICALLY_CONFLICTING"]
        observed_ground = frozen_point["fixed_ground_spoofer"]["attacked_conflicting_rows"]
        phase25b_crosscheck = {
            "position_bias": comparisons,
            "fixed_ground_spoofer": {
                "expected": int(expected_ground),
                "observed": int(observed_ground),
                "match": int(expected_ground) == int(observed_ground),
            },
            "all_match": all(item["match"] for item in comparisons.values())
            and int(expected_ground) == int(observed_ground),
        }

    report = {
        "schema": "sam.phase29.threshold-operating-point-sensitivity.v1",
        "scope": "development-defined physical-threshold operating points evaluated on held-out benign-reference and controlled position-bias scenarios",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": seed,
            "score": model["score"],
            "threshold_quantile_method": "numpy higher empirical quantile",
            "candidate_target_benign_consistency": targets,
            "frozen_target_benign_consistency": 0.99,
            "frozen_threshold_ns": frozen_threshold,
            "position_bias_m": biases_m,
            "selection_rule": "all candidate thresholds are computed only from Phase 5B development-validation aircraft",
            "no_retuning": [
                "subset-1 test does not select an operating point",
                "controlled attack scenarios do not select an operating point",
                "the frozen 0.99 point remains the manuscript decision unless prospectively changed",
            ],
        },
        "inputs": {
            "sha256": input_hashes,
            "decision_model": core.sha256_file(args.decision_model),
            "phase25b_report": core.sha256_file(args.phase25b_report) if args.phase25b_report else None,
        },
        "counts": counts,
        "unavailable_reasons": unavailable_reasons,
        "operating_points": operating_points,
        "phase25b_frozen_point_crosscheck": phase25b_crosscheck,
        "runtime": {"wall_seconds": time.perf_counter() - started},
        "interpretation_limits": [
            "Operating-point sensitivity is descriptive; no threshold is selected from test or controlled-attack outcomes.",
            "Trusted-aircraft metadata provides a benign reference filter, not guaranteed attack-free ground truth.",
            "Position offsets and the fixed-ground-spoofer case are controlled perturbations, not captured operational attacks.",
            "Conflict sensitivity is conditional on the implemented score, receiver set, calibration, and geometry gate.",
            "Results do not estimate operational attack prevalence or certified detection performance.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
