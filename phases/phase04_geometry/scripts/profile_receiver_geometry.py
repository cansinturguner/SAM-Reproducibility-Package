#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
from statistics import median

EXPECTED_SHA256 = "1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5"
QUANTILES = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0)
RATIO_CANDIDATES = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def finite_float(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def describe(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "quantiles": {}}
    return {
        "n": len(values),
        "median": median(values),
        "quantiles": {f"q{int(q * 100):02d}": percentile(values, q) for q in QUANTILES},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    ap.add_argument("--skip-hash-check", action="store_true")
    args = ap.parse_args()

    actual_hash = sha256_file(args.input)
    if not args.skip_hash_check and actual_hash != args.expected_sha256:
        raise SystemExit(
            f"Input SHA-256 mismatch: expected {args.expected_sha256}, got {actual_hash}"
        )

    total = development = ge4 = 0
    ranks = {}
    missing = {"ratio": 0, "min_baseline_m": 0, "max_baseline_m": 0, "rank": 0}
    values = {
        "ratio_ge3": [], "ratio_ge4": [],
        "min_baseline_m_ge3": [], "min_baseline_m_ge4": [],
        "max_baseline_m_ge3": [], "max_baseline_m_ge4": [],
    }

    with gzip.open(args.input, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "split", "eligible_ge4", "receiverGeometryRank",
            "receiverGeometryRatio", "receiverMinBaselineM", "receiverMaxBaselineM"
        }
        absent = sorted(required - set(reader.fieldnames or []))
        if absent:
            raise SystemExit(f"Missing columns: {', '.join(absent)}")

        for row in reader:
            total += 1
            if row["split"].strip().lower() != "development":
                continue
            development += 1
            is_ge4 = row["eligible_ge4"].strip().lower() in {"true", "1", "yes"}
            ge4 += int(is_ge4)

            rank = finite_float(row["receiverGeometryRank"])
            if rank is None:
                missing["rank"] += 1
            else:
                rank_key = str(int(rank)) if rank.is_integer() else str(rank)
                ranks[rank_key] = ranks.get(rank_key, 0) + 1

            ratio = finite_float(row["receiverGeometryRatio"])
            min_b = finite_float(row["receiverMinBaselineM"])
            max_b = finite_float(row["receiverMaxBaselineM"])
            for name, val, key in (
                ("ratio", ratio, "ratio_ge3"),
                ("min_baseline_m", min_b, "min_baseline_m_ge3"),
                ("max_baseline_m", max_b, "max_baseline_m_ge3"),
            ):
                if val is None:
                    missing[name] += 1
                else:
                    values[key].append(val)
            if is_ge4:
                if ratio is not None:
                    values["ratio_ge4"].append(ratio)
                if min_b is not None:
                    values["min_baseline_m_ge4"].append(min_b)
                if max_b is not None:
                    values["max_baseline_m_ge4"].append(max_b)

    retention = []
    ratios_ge4 = values["ratio_ge4"]
    for threshold in RATIO_CANDIDATES:
        kept = sum(x >= threshold for x in ratios_ge4)
        retention.append({
            "ratio_min_candidate": threshold,
            "ge4_rows_retained": kept,
            "ge4_retention_fraction": kept / len(ratios_ge4) if ratios_ge4 else None,
        })

    report = {
        "phase": "SAM Phase 4 receiver-geometry profiling",
        "selection_scope": "development partition only",
        "input": {"path": str(args.input), "sha256": actual_hash},
        "counts": {
            "all_input_rows_read": total,
            "development_ge3_rows": development,
            "development_ge4_rows": ge4,
            "development_ge3_only_rows": development - ge4,
            "geometry_rank_histogram": dict(sorted(ranks.items())),
            "missing_or_nonfinite": missing,
        },
        "distributions": {name: describe(vals) for name, vals in values.items()},
        "candidate_retention": retention,
        "interpretation": {
            "geometry_ratio": (
                "Descriptive centered-ECEF singular-value ratio from Phase 3; "
                "larger values indicate less degenerate receiver geometry. No final threshold is set here."
            ),
            "test_partition": "Not used to derive these statistics or choose a threshold.",
            "security_label": "No attack or anomaly label is created.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
