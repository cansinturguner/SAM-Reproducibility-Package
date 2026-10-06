#!/usr/bin/env python3
"""Freeze and transfer a reference-independent receiver-integrity guard."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

P27 = Path(os.environ.get(
    "SAM_PHASE27_SCRIPTS",
    str(Path(__file__).resolve().parents[2] / "phase27_threshold_aware_integration" / "scripts"),
))
if not P27.exists():
    raise SystemExit("Phase 27 scripts are required at phases/phase27_threshold_aware_integration/scripts")
sys.path.insert(0, str(P27))
import threshold_core as core  # noqa: E402

DATASET_DOI = "10.5281/zenodo.4739276"
MAGNITUDES = (100, 250, 500, 750, 1000, 2000, 5000, 10000)


def aircraft_group(aircraft: str, seed: int, calibration_percent: int) -> str:
    token = f"{seed}|{aircraft}".encode()
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    return "calibration" if bucket < calibration_percent else "validation"


def load_trusted(path: Path) -> set[str]:
    out = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if core.truthy(row.get("trusted")):
                out.add(str(row.get("aircraft", "")).strip())
    return out


def build_context(row, sensors, biases, modeled, measurement_field):
    lat = core.finite(row.get("latitude"))
    lon = core.finite(row.get("longitude"))
    alt = core.finite(row.get("geoAltitude"))
    if alt is None:
        alt = core.finite(row.get("baroAltitude"))
    if None in (lat, lon, alt):
        return None, "missing_position_or_altitude"
    try:
        observed = core.measurements(row.get(measurement_field, "[]"), modeled)
    except (json.JSONDecodeError, TypeError):
        observed = []
    if len(observed) < 4:
        return None, "fewer_than_4_modeled_receivers"
    if not core.rank3([sensors[sid] for sid, _ in observed]):
        return None, "rank_below_3"
    xyz = core.ecef(lat, lon, alt)
    ids = [sid for sid, _ in observed]
    delays = np.asarray([np.linalg.norm(xyz - sensors[sid]) / core.C * 1e9 for sid in ids])
    corrected = np.asarray([ts - biases[sid] for sid, ts in observed])
    return {"sensor_ids": ids, "errors_ns": corrected - delays}, None


def receiver_scores(errors: np.ndarray) -> np.ndarray:
    matrix = np.abs(errors[:, None] - errors[None, :])
    return np.asarray([np.median(np.delete(matrix[i], i)) for i in range(len(errors))])


def guard_score(errors: np.ndarray) -> float:
    return float(np.max(receiver_scores(errors)))


def current_score(errors: np.ndarray) -> float:
    return float(np.median(np.abs(errors[1:] - errors[0])))


def qhigher(values, q):
    return float(np.quantile(np.asarray(values, dtype=float), q, method="higher"))


def state(score, threshold):
    if score is None:
        return "PHYSICAL_EVIDENCE_UNAVAILABLE"
    return "PHYSICALLY_CONFLICTING" if score > threshold else "PHYSICALLY_CONSISTENT"


EVENT_FIELDS = [
    "id", "timeAtServer", "aircraft", "source_partition", "physical_availability",
    "unavailable_reason", "receiver_count", "reference_score_ns", "guard_score_ns",
    "reference_state", "guard_state", "combined_state", "highest_scored_receiver",
]


def event(row, partition, context, reason, reference_threshold, guard_threshold):
    base = {
        "id": row.get("id", ""), "timeAtServer": row.get("timeAtServer", ""),
        "aircraft": row.get("aircraft", ""), "source_partition": partition,
        "physical_availability": context is not None, "unavailable_reason": reason or "",
        "receiver_count": 0, "reference_score_ns": "", "guard_score_ns": "",
        "reference_state": "PHYSICAL_EVIDENCE_UNAVAILABLE",
        "guard_state": "PHYSICAL_EVIDENCE_UNAVAILABLE",
        "combined_state": "PHYSICAL_EVIDENCE_UNAVAILABLE", "highest_scored_receiver": "",
    }
    if context is None:
        return base
    scores = receiver_scores(context["errors_ns"])
    ref_score = current_score(context["errors_ns"])
    g_score = float(np.max(scores))
    ref_state, guard_state = state(ref_score, reference_threshold), state(g_score, guard_threshold)
    base.update({
        "receiver_count": len(context["sensor_ids"]), "reference_score_ns": ref_score,
        "guard_score_ns": g_score, "reference_state": ref_state, "guard_state": guard_state,
        "combined_state": "PHYSICALLY_CONFLICTING" if "PHYSICALLY_CONFLICTING" in (ref_state, guard_state) else "PHYSICALLY_CONSISTENT",
        "highest_scored_receiver": context["sensor_ids"][int(np.argmax(scores))],
    })
    return base


def write_events(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def summarize(events):
    counts = Counter(x["combined_state"] for x in events)
    available = [x for x in events if x["physical_availability"]]
    def branch(name):
        c = Counter(x[name] for x in available)
        return {
            "available_rows": len(available),
            "PHYSICALLY_CONSISTENT": c["PHYSICALLY_CONSISTENT"],
            "PHYSICALLY_CONFLICTING": c["PHYSICALLY_CONFLICTING"],
            "empirical_benign_reference_conflict_fraction_among_available": c["PHYSICALLY_CONFLICTING"] / len(available) if available else None,
        }
    return {
        "originally_eligible_rows": len(events),
        "physical_available_rows": len(available),
        "physical_availability_fraction": len(available) / len(events) if events else None,
        "reference_rule": branch("reference_state"),
        "receiver_integrity_guard": branch("guard_state"),
        "combined_rule": branch("combined_state"),
        "PHYSICAL_EVIDENCE_UNAVAILABLE": counts["PHYSICAL_EVIDENCE_UNAVAILABLE"],
    }


def corruption_sensitivity(contexts, threshold, magnitudes):
    result = {}
    for magnitude in magnitudes:
        trials = conflicts = target_highest = 0
        baseline_consistent = consistent_to_conflicting = 0
        for context in contexts:
            errors = context["errors_ns"]
            baseline = guard_score(errors) > threshold
            for sign in (-1, 1):
                for target in range(len(errors)):
                    shifted = errors.copy(); shifted[target] += sign * magnitude
                    scores = receiver_scores(shifted)
                    conflict = float(np.max(scores)) > threshold
                    trials += 1; conflicts += int(conflict)
                    target_highest += int(target in np.flatnonzero(np.isclose(scores, np.max(scores), rtol=0, atol=1e-12)))
                    if not baseline:
                        baseline_consistent += 1
                        consistent_to_conflicting += int(conflict)
        result[str(magnitude)] = {
            "trials": trials,
            "result_conflict_fraction": conflicts / trials if trials else None,
            "consistent_to_conflicting_fraction": consistent_to_conflicting / baseline_consistent if baseline_consistent else None,
            "target_ranked_highest_fraction": target_highest / trials if trials else None,
        }
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--subset1-sensors", type=Path, required=True)
    p.add_argument("--subset2-observations", type=Path, required=True)
    p.add_argument("--subset2-sensors", type=Path, required=True)
    p.add_argument("--subset2-aircraft", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--decision-model", type=Path, required=True)
    p.add_argument("--model-output", type=Path, required=True)
    p.add_argument("--development-events", type=Path, required=True)
    p.add_argument("--subset1-events", type=Path, required=True)
    p.add_argument("--subset2-events", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--guard-quantile", type=float, default=.99)
    p.add_argument("--magnitudes-ns", type=int, nargs="+", default=MAGNITUDES)
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()
    if not 0 < a.guard_quantile < 1:
        p.error("--guard-quantile must be in (0,1)")
    started = time.perf_counter()
    model = core.load_decision_model(a.decision_model)
    input_hashes = core.verify_model_inputs(model, a.selected, a.subset1_sensors, a.calibration, a.skip_hash_check)
    input_hashes.update({
        "subset2_observations": core.sha256_file(a.subset2_observations),
        "subset2_sensors": core.sha256_file(a.subset2_sensors),
        "subset2_aircraft": core.sha256_file(a.subset2_aircraft),
        "decision_model": core.sha256_file(a.decision_model),
    })
    seed = int(model["seed"]); calpct = int(model["calibration_percent"])
    ref_threshold = float(model["threshold_ns"])
    sensors1 = core.load_sensors(a.subset1_sensors); sensors2 = core.load_sensors(a.subset2_sensors)
    biases = core.load_biases(a.calibration)
    modeled1, modeled2 = set(sensors1) & set(biases), set(sensors2) & set(biases)

    dev_rows, test_rows, test_contexts = [], [], []
    dev_scores = []
    with gzip.open(a.selected, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not core.truthy(row.get("eligible_ge4")):
                continue
            split = row.get("split", "").strip().lower(); ac = str(row.get("aircraft", "")).strip()
            is_dev = split == "development" and aircraft_group(ac, seed, calpct) == "validation"
            is_test = split == "test"
            if not (is_dev or is_test):
                continue
            context, reason = build_context(row, sensors1, biases, modeled1, "goodMeasurements")
            if is_dev:
                if context is not None:
                    dev_scores.append(guard_score(context["errors_ns"]))
                dev_rows.append((row, context, reason))
            else:
                test_rows.append((row, context, reason))
                if context is not None:
                    test_contexts.append(context)
    guard_threshold = qhigher(dev_scores, a.guard_quantile)
    dev_events = [event(r, "subset1_development_validation", c, reason, ref_threshold, guard_threshold) for r, c, reason in dev_rows]
    test_events = [event(r, "subset1_frozen_test", c, reason, ref_threshold, guard_threshold) for r, c, reason in test_rows]

    trusted = load_trusted(a.subset2_aircraft)
    subset2_events = []
    with a.subset2_observations.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("aircraft", "")).strip() not in trusted:
                continue
            try:
                good = core.measurements(row.get("measurements", "[]"), set(sensors2))
            except (json.JSONDecodeError, TypeError):
                continue
            if len(good) < 4:
                continue
            context, reason = build_context(row, sensors2, biases, modeled2, "measurements")
            subset2_events.append(event(row, "subset2_transfer", context, reason, ref_threshold, guard_threshold))

    write_events(a.development_events, dev_events); write_events(a.subset1_events, test_events); write_events(a.subset2_events, subset2_events)
    receiver_model = {
        "schema": "sam.phase31.receiver-integrity-model.v1", "seed": seed,
        "score": "maximum across receivers of median absolute calibrated pair residual incident on that receiver",
        "reference_independent": True, "threshold_ns": guard_threshold,
        "threshold_quantile": a.guard_quantile,
        "threshold_source": "LocaRDS subset-1 development-validation aircraft only; higher empirical quantile",
        "test_used_for_selection": False, "dataset_doi": DATASET_DOI,
    }
    a.model_output.parent.mkdir(parents=True, exist_ok=True)
    a.model_output.write_text(json.dumps(receiver_model, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema": "sam.phase31.reference-independent-receiver-integrity.v1",
        "scope": "development-frozen receiver-integrity guard, subset-1 test, subset-2 transfer, and controlled single-receiver corruption",
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": platform.python_version(), "numpy": np.__version__},
        "inputs": {"sha256": input_hashes, "dataset_doi": DATASET_DOI},
        "method": receiver_model,
        "development_validation": summarize(dev_events),
        "subset1_frozen_test": summarize(test_events),
        "subset2_transfer": summarize(subset2_events),
        "single_receiver_timestamp_corruption": corruption_sensitivity(test_contexts, guard_threshold, sorted(set(a.magnitudes_ns))),
        "artifacts": {"model": str(a.model_output), "development_events": str(a.development_events), "subset1_events": str(a.subset1_events), "subset2_events": str(a.subset2_events)},
        "runtime": {"wall_seconds": time.perf_counter() - started},
        "interpretation_limits": [
            "The guard is reference-independent but still depends on the frozen receiver clock model and LocaRDS receiver network.",
            "Conflict fractions on trusted-aircraft data are empirical benign-reference rates, not population false-positive rates.",
            "Timestamp shifts are controlled sensitivity conditions, not operational attack-detection rates.",
            "Subset 2 is a cross-partition transfer test using the same published sensor infrastructure, not an independent receiver network.",
            "The guard does not identify malicious intent; it exposes receiver-level timing inconsistency.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"guard_threshold_ns": guard_threshold, "subset1": report["subset1_frozen_test"], "subset2": report["subset2_transfer"]}, indent=2))


if __name__ == "__main__":
    main()
