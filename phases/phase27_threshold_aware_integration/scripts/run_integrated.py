#!/usr/bin/env python3
"""Fresh-process threshold-aware integrated SAM replay."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

import threshold_core as core


def empty_counts() -> dict[str, int]:
    return {
        "rows_read": 0,
        "test_rows": 0,
        "eligible_rows": 0,
        "hmac_verified": 0,
        core.PHYSICALLY_CONSISTENT: 0,
        core.PHYSICALLY_CONFLICTING: 0,
        core.PHYSICAL_EVIDENCE_UNAVAILABLE: 0,
        "VERIFIED": 0,
        "CONFLICTING": 0,
        "INSUFFICIENT_EVIDENCE": 0,
    }


def run_worker(args) -> dict:
    start = time.perf_counter()
    cpu_start = time.process_time()
    model = core.load_decision_model(args.decision_model)
    input_hashes = core.verify_model_inputs(
        model, args.selected, args.sensors, args.calibration, args.skip_hash_check
    )
    threshold_ns = float(model["threshold_ns"])
    sensors = core.load_sensors(args.sensors)
    biases = core.load_biases(args.calibration)
    modeled = set(sensors) & set(biases)
    _, _, _, root_key = core.deterministic_crypto_material(args.seed)

    counts = empty_counts()
    unavailable_reasons = {}
    scores = []
    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            counts["rows_read"] += 1
            if row["split"].strip().lower() != "test":
                continue
            counts["test_rows"] += 1
            if not core.truthy(row["eligible_ge4"]):
                continue
            counts["eligible_rows"] += 1

            crypto = core.verify_hmac(row, root_key)
            if crypto == "VERIFIED":
                counts["hmac_verified"] += 1
            physical, score_ns, reason = core.physical_decision(
                row, sensors, biases, modeled, threshold_ns
            )
            counts[physical] += 1
            if score_ns is not None:
                scores.append(score_ns)
            if reason is not None:
                unavailable_reasons[reason] = unavailable_reasons.get(reason, 0) + 1
            final_state = core.fuse(crypto, "VALID", physical)
            counts[final_state] += 1

    wall_seconds = time.perf_counter() - start
    cpu_seconds = time.process_time() - cpu_start
    score_array = np.asarray(scores, dtype=float)
    eligible = counts["eligible_rows"]
    return {
        "input_hashes": input_hashes,
        "threshold_ns": threshold_ns,
        "counts": counts,
        "unavailable_reasons": unavailable_reasons,
        "score_summary_ns": {
            "n": len(scores),
            "q50": float(np.quantile(score_array, 0.50)),
            "q90": float(np.quantile(score_array, 0.90)),
            "q95": float(np.quantile(score_array, 0.95)),
            "q99": float(np.quantile(score_array, 0.99)),
            "maximum": float(np.max(score_array)),
        },
        "timing": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "microseconds_per_eligible_row": wall_seconds * 1e6 / eligible,
            "eligible_rows_per_second": eligible / wall_seconds,
        },
        "peak_rss_mib": core.peak_rss_mib(),
    }


def summarize(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "values": values,
    }


def child(args) -> dict:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--selected",
        str(args.selected),
        "--sensors",
        str(args.sensors),
        "--calibration",
        str(args.calibration),
        "--decision-model",
        str(args.decision_model),
        "--seed",
        str(args.seed),
    ]
    if args.skip_hash_check:
        command.append("--skip-hash-check")
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
        }
    )
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, env=environment
    )
    return json.loads(completed.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--sensors", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--decision-model", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--seed", type=int, default=1103)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--skip-hash-check", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        print(json.dumps(run_worker(args)))
        return
    if args.report is None:
        parser.error("--report is required")
    if args.repetitions < 5:
        parser.error("--repetitions must be at least 5")

    for _ in range(args.warmups):
        child(args)
    runs = [child(args) for _ in range(args.repetitions)]
    baseline = runs[0]
    for run in runs[1:]:
        if run["counts"] != baseline["counts"]:
            raise SystemExit("Non-deterministic threshold-aware counts")
        if run["score_summary_ns"] != baseline["score_summary_ns"]:
            raise SystemExit("Non-deterministic physical scores")

    counts = baseline["counts"]
    physical_conflicts = counts[core.PHYSICALLY_CONFLICTING]
    physical_consistent = counts[core.PHYSICALLY_CONSISTENT]
    physical_unavailable = counts[core.PHYSICAL_EVIDENCE_UNAVAILABLE]
    eligible = counts["eligible_rows"]
    component_variants = {
        "A0_legacy": {"LEGACY_UNASSURED": eligible},
        "A1_full": {
            "VERIFIED": counts["VERIFIED"],
            "CONFLICTING": counts["CONFLICTING"],
            "INSUFFICIENT_EVIDENCE": counts["INSUFFICIENT_EVIDENCE"],
        },
        "A2_crypto_absent": {
            "CONFLICTING": physical_conflicts,
            "INSUFFICIENT_EVIDENCE": eligible - physical_conflicts,
        },
        "A3_physical_absent": {"INSUFFICIENT_EVIDENCE": eligible},
        "A6_trust": {
            "valid_cache": {
                "VERIFIED": physical_consistent,
                "CONFLICTING": physical_conflicts,
                "INSUFFICIENT_EVIDENCE": physical_unavailable,
            },
            "cold_or_expired_cache": {
                "CONFLICTING": physical_conflicts,
                "INSUFFICIENT_EVIDENCE": eligible - physical_conflicts,
            },
            "revoked_record": {"CONFLICTING": eligible},
        },
        "A7_single_source": {
            "crypto_only": {"VERIFIED": eligible},
            "physical_only": {
                "VERIFIED": physical_consistent,
                "CONFLICTING": physical_conflicts,
                "INSUFFICIENT_EVIDENCE": physical_unavailable,
            },
        },
    }

    report = {
        "schema": "sam.phase27a.threshold-aware-integrated.v1",
        "scope": "fresh-process integrated replay with the frozen Phase 25A physical decision inside the SAM fusion path",
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
            "seed": args.seed,
            "warmups": args.warmups,
            "measured_fresh_process_repetitions": args.repetitions,
            "physical_score": "median absolute calibrated direct-TDoA reference-pair residual per observation",
            "physical_threshold_ns": baseline["threshold_ns"],
            "fusion_policy": "conflict dominates; VERIFIED requires valid crypto, valid trust, and PHYSICALLY_CONSISTENT",
        },
        "inputs": {
            "sha256": baseline["input_hashes"],
            "decision_model_sha256": core.sha256_file(args.decision_model),
        },
        "counts": counts,
        "unavailable_reasons": baseline["unavailable_reasons"],
        "score_summary_ns": baseline["score_summary_ns"],
        "component_variants": component_variants,
        "timing_summaries": {
            key: summarize([float(run["timing"][key]) for run in runs])
            for key in (
                "wall_seconds",
                "cpu_seconds",
                "microseconds_per_eligible_row",
                "eligible_rows_per_second",
            )
        },
        "peak_rss_mib": summarize([float(run["peak_rss_mib"]) for run in runs]),
        "interpretation_limits": [
            "The authenticator is deterministic and synthetic but bound to each real LocaRDS observation.",
            "The threshold is a reproducible prototype operating point, not a certified operational threshold.",
            "Timing excludes TESLA disclosure waiting, RF processing, and online trust refresh.",
            "Benign-reference conflicts are policy outcomes and not proof of attacks.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

