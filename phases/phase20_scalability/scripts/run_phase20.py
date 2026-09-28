#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path


def summary(values):
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "values": values,
    }


def command(a):
    core = Path(__file__).with_name("phase14_core.py")
    cmd = [
        sys.executable, str(core), "--worker",
        "--selected", str(a.selected),
        "--sensors", str(a.sensors),
        "--calibration", str(a.calibration),
        "--seed", str(a.seed),
        "--expected-selected-sha256", a.expected_selected_sha256,
    ]
    if a.skip_hash_check:
        cmd.append("--skip-hash-check")
    return cmd


def run_batch(a, workers):
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    })
    start = time.perf_counter()
    processes = [
        subprocess.Popen(command(a), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=env)
        for _ in range(workers)
    ]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise SystemExit(f"Worker failed with code {process.returncode}: {stderr}")
        outputs.append(json.loads(stdout))
    batch_wall = time.perf_counter() - start

    first = outputs[0]
    for result in outputs:
        if result["counts"] != first["counts"]:
            raise SystemExit("Concurrent workers returned different frozen counts")
        if result["assurance_states"] != first["assurance_states"]:
            raise SystemExit("Concurrent workers returned different assurance states")

    eligible_each = int(first["counts"]["test_original_ge4_rows"])
    supported_each = int(first["counts"]["physical_supported_rows"])
    total_eligible = eligible_each * workers
    return {
        "workers": workers,
        "batch_wall_seconds": batch_wall,
        "aggregate_eligible_observations": total_eligible,
        "aggregate_supported_observations": supported_each * workers,
        "aggregate_observations_per_second": total_eligible / batch_wall,
        "worker_wall_seconds": [float(x["timing"]["wall_seconds"]) for x in outputs],
        "summed_worker_peak_rss_mib": sum(float(x["memory"]["peak_rss_mib"]) for x in outputs),
        "per_worker_counts": first["counts"],
        "per_worker_assurance_states": first["assurance_states"],
        "validation": first["validation"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selected", type=Path, required=True)
    p.add_argument("--sensors", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1103)
    p.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4])
    p.add_argument("--warmups", type=int, default=1)
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--expected-selected-sha256", default="1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5")
    p.add_argument("--skip-hash-check", action="store_true")
    a = p.parse_args()
    levels = sorted(set(a.concurrency))
    if not levels or levels[0] < 1 or levels[-1] > (os.cpu_count() or 1):
        p.error("concurrency levels must be between 1 and logical CPU count")
    if a.warmups < 0 or a.repetitions < 5:
        p.error("use non-negative warmups and at least 5 repetitions")

    for workers in levels:
        for _ in range(a.warmups):
            run_batch(a, workers)

    raw = {workers: [run_batch(a, workers) for _ in range(a.repetitions)] for workers in levels}
    baseline = statistics.median(x["aggregate_observations_per_second"] for x in raw[1])
    scenarios = []
    for workers in levels:
        runs = raw[workers]
        throughput = [x["aggregate_observations_per_second"] for x in runs]
        batch_wall = [x["batch_wall_seconds"] for x in runs]
        worker_wall = [statistics.median(x["worker_wall_seconds"]) for x in runs]
        memory = [x["summed_worker_peak_rss_mib"] for x in runs]
        median_throughput = statistics.median(throughput)
        speedup = median_throughput / baseline
        scenarios.append({
            "workers": workers,
            "aggregate_throughput_observations_per_second": summary(throughput),
            "batch_wall_seconds": summary(batch_wall),
            "median_worker_wall_seconds_per_batch": summary(worker_wall),
            "summed_worker_peak_rss_mib": summary(memory),
            "speedup_vs_single_worker_median": speedup,
            "parallel_efficiency": speedup / workers,
            "per_worker_eligible_observations": runs[0]["per_worker_counts"]["test_original_ge4_rows"],
            "per_worker_supported_observations": runs[0]["per_worker_counts"]["physical_supported_rows"],
            "per_worker_assurance_states": runs[0]["per_worker_assurance_states"],
        })

    frozen = raw[1][0]
    report = {
        "schema": "sam.phase20.concurrent-scalability.v1",
        "scope": {
            "implemented": "concurrent independent replay stress test of the frozen integrated SAM worker",
            "not_implemented": [
                "aircraft-count or RF-channel simulation",
                "shared live receiver ingestion",
                "operational WAN or ledger consensus",
                "certified airborne hardware",
            ],
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
        },
        "configuration": {
            "seed": a.seed,
            "concurrency_levels": levels,
            "warmups_per_level": a.warmups,
            "measured_repetitions_per_level": a.repetitions,
            "native_threads_per_worker": 1,
            "worker_implementation": "frozen Phase 14 integrated pipeline",
        },
        "frozen_validation": {
            "per_worker_counts": frozen["per_worker_counts"],
            "per_worker_assurance_states": frozen["per_worker_assurance_states"],
            "pair_residual_absolute_q50_ns": frozen["validation"]["absolute_q50_ns"],
            "pair_residual_absolute_q95_ns": frozen["validation"]["absolute_q95_ns"],
        },
        "scenarios": scenarios,
        "interpretation_limits": [
            "Each worker independently replays the same frozen LocaRDS test partition; workers do not share a live input stream.",
            "Aggregate throughput is an offline processing-capacity measurement, not authentication delay or RF-channel capacity.",
            "Speedup and efficiency characterize this Python/Mac multiprocessing implementation.",
            "Summed worker peak RSS is a conservative sum of process peaks and not a direct whole-system memory trace.",
            "Results do not establish certified airborne performance.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
