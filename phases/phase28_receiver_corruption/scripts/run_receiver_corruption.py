#!/usr/bin/env python3
"""Evaluate single-receiver timestamp corruption in the frozen physical rule."""

from __future__ import annotations

import argparse
import csv
import gzip
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


DEFAULT_MAGNITUDES_NS = (100, 250, 500, 750, 1000, 2000, 5000, 10000)


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
    delays = {
        sensor_id: float(
            np.linalg.norm(aircraft_xyz - sensors[sensor_id]) / core.C * 1e9
        )
        for sensor_id, _ in observed
    }
    corrected = {
        sensor_id: timestamp - biases[sensor_id]
        for sensor_id, timestamp in observed
    }
    reference = observed[0][0]
    nonreference_ids = [sensor_id for sensor_id, _ in observed[1:]]
    residuals = np.asarray(
        [
            (corrected[sensor_id] - corrected[reference])
            - (delays[sensor_id] - delays[reference])
            for sensor_id in nonreference_ids
        ],
        dtype=float,
    )
    return {
        "reference": reference,
        "nonreference_ids": nonreference_ids,
        "residuals_ns": residuals,
    }, None


def shifted_score_ns(
    residuals_ns: np.ndarray, timestamp_offset_ns: float, target_index: int | None
) -> float:
    if target_index is None:
        shifted = residuals_ns - timestamp_offset_ns
    else:
        shifted = residuals_ns.copy()
        shifted[target_index] += timestamp_offset_ns
    return float(np.median(np.abs(shifted)))


def new_accumulator() -> dict[str, int]:
    return {
        "trials": 0,
        "baseline_consistent_trials": 0,
        "baseline_conflicting_trials": 0,
        "result_consistent": 0,
        "result_conflicting": 0,
        "consistent_to_conflicting": 0,
        "conflicting_to_consistent": 0,
    }


def update_accumulator(accumulator, baseline_state, result_state):
    accumulator["trials"] += 1
    if baseline_state == core.PHYSICALLY_CONSISTENT:
        accumulator["baseline_consistent_trials"] += 1
        if result_state == core.PHYSICALLY_CONFLICTING:
            accumulator["consistent_to_conflicting"] += 1
    else:
        accumulator["baseline_conflicting_trials"] += 1
        if result_state == core.PHYSICALLY_CONSISTENT:
            accumulator["conflicting_to_consistent"] += 1
    if result_state == core.PHYSICALLY_CONSISTENT:
        accumulator["result_consistent"] += 1
    else:
        accumulator["result_conflicting"] += 1


def finalize_accumulator(accumulator: dict[str, int]) -> dict:
    result = dict(accumulator)
    trials = accumulator["trials"]
    baseline_consistent = accumulator["baseline_consistent_trials"]
    result["result_conflict_fraction_all_trials"] = (
        accumulator["result_conflicting"] / trials if trials else None
    )
    result["consistent_to_conflicting_fraction"] = (
        accumulator["consistent_to_conflicting"] / baseline_consistent
        if baseline_consistent
        else None
    )
    result["conflicting_to_consistent_fraction"] = (
        accumulator["conflicting_to_consistent"]
        / accumulator["baseline_conflicting_trials"]
        if accumulator["baseline_conflicting_trials"]
        else None
    )
    return result


def new_observation_accumulator() -> dict[str, int]:
    return {
        "baseline_consistent_observation_trials": 0,
        "any_target_conflicting": 0,
        "all_targets_conflicting": 0,
    }


def finalize_observation_accumulator(accumulator: dict[str, int]) -> dict:
    result = dict(accumulator)
    denominator = accumulator["baseline_consistent_observation_trials"]
    result["any_target_conflicting_fraction"] = (
        accumulator["any_target_conflicting"] / denominator if denominator else None
    )
    result["all_targets_conflicting_fraction"] = (
        accumulator["all_targets_conflicting"] / denominator if denominator else None
    )
    return result


def combine_finalizable(accumulators: list[dict[str, int]]) -> dict:
    combined = new_accumulator()
    for accumulator in accumulators:
        for key in combined:
            combined[key] += accumulator[key]
    return finalize_accumulator(combined)


def combine_observation_accumulators(accumulators: list[dict[str, int]]) -> dict:
    combined = new_observation_accumulator()
    for accumulator in accumulators:
        for key in combined:
            combined[key] += accumulator[key]
    return finalize_observation_accumulator(combined)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--sensors", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--decision-model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--magnitudes-ns", type=int, nargs="+", default=DEFAULT_MAGNITUDES_NS)
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args()

    magnitudes = sorted(set(int(value) for value in args.magnitudes_ns))
    if not magnitudes or any(value <= 0 for value in magnitudes):
        parser.error("timestamp magnitudes must be positive")
    signed_offsets = sorted([-value for value in magnitudes] + magnitudes)

    start = time.perf_counter()
    model = core.load_decision_model(args.decision_model)
    input_hashes = core.verify_model_inputs(
        model, args.selected, args.sensors, args.calibration, args.skip_hash_check
    )
    threshold_ns = float(model["threshold_ns"])
    sensors = core.load_sensors(args.sensors)
    biases = core.load_biases(args.calibration)
    modeled = set(sensors) & set(biases)
    calibration_report = json.loads(args.calibration.read_text(encoding="utf-8"))
    calibration_reference = str(calibration_report["reference_sensor"])

    reference_results = {offset: new_accumulator() for offset in signed_offsets}
    nonreference_results = {offset: new_accumulator() for offset in signed_offsets}
    nonreference_observations = {
        offset: new_observation_accumulator() for offset in signed_offsets
    }
    calibration_reference_results = {
        offset: new_accumulator() for offset in signed_offsets
    }

    baseline = {
        "eligible_rows": 0,
        core.PHYSICALLY_CONSISTENT: 0,
        core.PHYSICALLY_CONFLICTING: 0,
        core.PHYSICAL_EVIDENCE_UNAVAILABLE: 0,
        "available_rows": 0,
        "reference_pair_trials": 0,
    }
    unavailable_reasons = {}
    calibration_reference_coverage = {
        "rows_containing_calibration_reference": 0,
        "as_decision_reference": 0,
        "as_nonreference": 0,
    }

    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["split"].strip().lower() != "test" or not core.truthy(row["eligible_ge4"]):
                continue
            baseline["eligible_rows"] += 1
            context, reason = physical_context(row, sensors, biases, modeled)
            if context is None:
                baseline[core.PHYSICAL_EVIDENCE_UNAVAILABLE] += 1
                unavailable_reasons[reason] = unavailable_reasons.get(reason, 0) + 1
                continue

            residuals = context["residuals_ns"]
            baseline_score = float(np.median(np.abs(residuals)))
            baseline_state = core.classify_score(baseline_score, threshold_ns)
            baseline[baseline_state] += 1
            baseline["available_rows"] += 1
            baseline["reference_pair_trials"] += len(residuals)

            anchor_target_index = None
            anchor_present = False
            if context["reference"] == calibration_reference:
                anchor_present = True
                calibration_reference_coverage["rows_containing_calibration_reference"] += 1
                calibration_reference_coverage["as_decision_reference"] += 1
            elif calibration_reference in context["nonreference_ids"]:
                anchor_present = True
                anchor_target_index = context["nonreference_ids"].index(calibration_reference)
                calibration_reference_coverage["rows_containing_calibration_reference"] += 1
                calibration_reference_coverage["as_nonreference"] += 1

            for offset in signed_offsets:
                reference_score = shifted_score_ns(residuals, offset, None)
                reference_state = core.classify_score(reference_score, threshold_ns)
                update_accumulator(reference_results[offset], baseline_state, reference_state)

                target_states = []
                for target_index in range(len(residuals)):
                    target_score = shifted_score_ns(residuals, offset, target_index)
                    target_state = core.classify_score(target_score, threshold_ns)
                    target_states.append(target_state)
                    update_accumulator(
                        nonreference_results[offset], baseline_state, target_state
                    )
                if baseline_state == core.PHYSICALLY_CONSISTENT:
                    observation_accumulator = nonreference_observations[offset]
                    observation_accumulator["baseline_consistent_observation_trials"] += 1
                    if any(
                        state == core.PHYSICALLY_CONFLICTING for state in target_states
                    ):
                        observation_accumulator["any_target_conflicting"] += 1
                    if all(
                        state == core.PHYSICALLY_CONFLICTING for state in target_states
                    ):
                        observation_accumulator["all_targets_conflicting"] += 1

                if anchor_present:
                    anchor_score = shifted_score_ns(
                        residuals, offset, anchor_target_index
                    )
                    anchor_state = core.classify_score(anchor_score, threshold_ns)
                    update_accumulator(
                        calibration_reference_results[offset],
                        baseline_state,
                        anchor_state,
                    )

    signed_results = []
    for offset in signed_offsets:
        signed_results.append(
            {
                "timestamp_offset_ns": offset,
                "propagation_distance_equivalent_m": abs(offset) * 1e-9 * core.C,
                "decision_reference_corruption": finalize_accumulator(
                    reference_results[offset]
                ),
                "single_nonreference_corruption": {
                    **finalize_accumulator(nonreference_results[offset]),
                    "observation_level": finalize_observation_accumulator(
                        nonreference_observations[offset]
                    ),
                },
                "calibration_reference_corruption": finalize_accumulator(
                    calibration_reference_results[offset]
                ),
            }
        )

    magnitude_summary = []
    for magnitude in magnitudes:
        signs = (-magnitude, magnitude)
        magnitude_summary.append(
            {
                "absolute_timestamp_offset_ns": magnitude,
                "propagation_distance_equivalent_m": magnitude * 1e-9 * core.C,
                "decision_reference_corruption": combine_finalizable(
                    [reference_results[offset] for offset in signs]
                ),
                "single_nonreference_corruption": {
                    **combine_finalizable(
                        [nonreference_results[offset] for offset in signs]
                    ),
                    "observation_level": combine_observation_accumulators(
                        [nonreference_observations[offset] for offset in signs]
                    ),
                },
                "calibration_reference_corruption": combine_finalizable(
                    [calibration_reference_results[offset] for offset in signs]
                ),
            }
        )

    report = {
        "schema": "sam.phase28.single-receiver-corruption.v1",
        "scope": "controlled timestamp corruption of one receiver at a time under the frozen Phase 25A physical decision",
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
            "physical_threshold_ns": threshold_ns,
            "timestamp_offset_magnitudes_ns": magnitudes,
            "directions": ["negative", "positive"],
            "decision_reference_rule": "first receiver after deterministic sensor-id sorting within each observation",
            "single_nonreference_rule": "every available nonreference receiver is corrupted once per signed offset",
            "calibration_reference_sensor": calibration_reference,
            "unchanged_values": [
                "reported aircraft position",
                "all other receiver timestamps",
                "receiver clock calibration",
                "receiver membership and geometry rule",
                "physical threshold",
            ],
        },
        "inputs": {
            "sha256": input_hashes,
            "decision_model_sha256": core.sha256_file(args.decision_model),
        },
        "baseline": baseline,
        "unavailable_reasons": unavailable_reasons,
        "calibration_reference_coverage": calibration_reference_coverage,
        "signed_offset_results": signed_results,
        "absolute_magnitude_summary": magnitude_summary,
        "runtime": {"wall_seconds": time.perf_counter() - start},
        "interpretation_limits": [
            "Timestamp offsets are deterministic sensitivity conditions and not measured receiver-compromise traces.",
            "The nonreference result is trial-weighted across every possible single nonreference target in each available observation.",
            "The decision reference is observation-specific; the calibration reference is the globally anchored receiver in the clock model.",
            "Conflict fractions are not operational attack-detection probabilities.",
            "No correlated multi-receiver compromise, RF manipulation, or receiver removal is modeled.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
