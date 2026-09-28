#!/usr/bin/env python3
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

C = 299_792_458.0
WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3
EXPECTED_SELECTED_SHA256 = "1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5"
SCALES_TO_SECONDS = {
    "raw_unit_is_nanosecond": 1e-9,
    "raw_unit_is_microsecond": 1e-6,
    "raw_unit_is_millisecond": 1e-3,
    "raw_unit_is_second": 1.0,
}


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


def truthy(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def geodetic_to_ecef(lat_deg, lon_deg, height_m):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    return (
        (n + height_m) * cos_lat * math.cos(lon),
        (n + height_m) * cos_lat * math.sin(lon),
        (n * (1.0 - WGS84_E2) + height_m) * sin_lat,
    )


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def describe(values):
    values = sorted(values)
    return {
        "n": len(values),
        "q01": percentile(values, 0.01),
        "q05": percentile(values, 0.05),
        "q50": percentile(values, 0.50),
        "q95": percentile(values, 0.95),
        "q99": percentile(values, 0.99),
        "min": values[0] if values else None,
        "max": values[-1] if values else None,
    }


def circular_difference(a, b, period):
    d = a - b
    return (d + period / 2.0) % period - period / 2.0


def selected_by_hash(row_id, aircraft, seed, permille):
    token = f"{seed}|{row_id}|{aircraft}".encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 1000
    return bucket < permille


def load_good_sensors(path):
    sensors = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not truthy(row.get("good")):
                continue
            sid = str(row.get("serial", "")).strip()
            lat = finite_float(row.get("latitude"))
            lon = finite_float(row.get("longitude"))
            height = finite_float(row.get("height"))
            if sid and None not in (lat, lon, height):
                sensors[sid] = geodetic_to_ecef(lat, lon, height)
    return sensors


def parse_measurements(raw):
    parsed = json.loads(raw)
    out = []
    for item in parsed:
        if not isinstance(item, list) or len(item) < 2:
            continue
        sid = str(item[0]).strip()
        ts = finite_float(item[1])
        if sid and ts is not None:
            out.append((sid, ts))
    dedup = {}
    for sid, ts in out:
        dedup.setdefault(sid, ts)
    return sorted(dedup.items(), key=lambda x: x[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True, type=Path)
    ap.add_argument("--sensors", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--sample-permille", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1103)
    ap.add_argument("--expected-selected-sha256", default=EXPECTED_SELECTED_SHA256)
    ap.add_argument("--skip-hash-check", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.sample_permille <= 1000:
        raise SystemExit("--sample-permille must be between 1 and 1000")

    selected_hash = sha256_file(args.selected)
    if not args.skip_hash_check and selected_hash != args.expected_selected_sha256:
        raise SystemExit(
            f"Selected input SHA-256 mismatch: expected {args.expected_selected_sha256}, got {selected_hash}"
        )
    sensors = load_good_sensors(args.sensors)
    if not sensors:
        raise SystemExit("No good sensors with valid coordinates were loaded")

    candidate_errors_ns = defaultdict(list)
    pair_errors_best_later = defaultdict(list)
    retained_rows = []
    raw_timestamps = []
    raw_spans = []
    counts = defaultdict(int)

    with gzip.open(args.selected, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "id", "aircraft", "split", "eligible_ge4", "latitude", "longitude",
            "geoAltitude", "baroAltitude", "goodMeasurements"
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise SystemExit(f"Missing columns: {', '.join(missing)}")
        for row in reader:
            counts["rows_read"] += 1
            if row["split"].strip().lower() != "development":
                continue
            counts["development_rows"] += 1
            if not truthy(row["eligible_ge4"]):
                continue
            counts["development_ge4_rows"] += 1
            if not selected_by_hash(row["id"], row["aircraft"], args.seed, args.sample_permille):
                continue
            counts["hash_sampled_rows"] += 1

            lat = finite_float(row["latitude"])
            lon = finite_float(row["longitude"])
            alt = finite_float(row["geoAltitude"])
            if alt is None:
                alt = finite_float(row["baroAltitude"])
            if None in (lat, lon, alt):
                counts["rows_missing_aircraft_position"] += 1
                continue
            try:
                measurements = [(sid, ts) for sid, ts in parse_measurements(row["goodMeasurements"]) if sid in sensors]
            except (json.JSONDecodeError, TypeError):
                counts["measurement_parse_errors"] += 1
                continue
            if len(measurements) < 4:
                counts["rows_with_fewer_than_4_loaded_good_sensors"] += 1
                continue

            aircraft_xyz = geodetic_to_ecef(lat, lon, alt)
            propagation = {sid: distance(aircraft_xyz, sensors[sid]) / C for sid, _ in measurements}
            reference_sid, reference_ts = measurements[0]
            raw_timestamps.extend(ts for _, ts in measurements)
            raw_spans.append(max(ts for _, ts in measurements) - min(ts for _, ts in measurements))
            comparisons = []
            for sid, ts in measurements[1:]:
                predicted = propagation[sid] - propagation[reference_sid]
                raw_delta = ts - reference_ts
                comparisons.append((reference_sid, sid, raw_delta, predicted))
                for scale_name, scale in SCALES_TO_SECONDS.items():
                    observed_no_wrap = raw_delta * scale
                    candidate_errors_ns[f"{scale_name}|no_wrap"].append(
                        abs(observed_no_wrap - predicted) * 1e9
                    )
                    period_raw = 60.0 / scale
                    observed_wrap = circular_difference(ts, reference_ts, period_raw) * scale
                    candidate_errors_ns[f"{scale_name}|wrap_60_seconds"].append(
                        abs(observed_wrap - predicted) * 1e9
                    )
            retained_rows.append(comparisons)
            counts["usable_sampled_rows"] += 1
            counts["receiver_pair_comparisons"] += len(comparisons)

    candidates = []
    for name, errors in candidate_errors_ns.items():
        summary = describe(errors)
        candidates.append({"candidate": name, "absolute_residual_ns": summary})
    candidates.sort(key=lambda x: (math.inf if x["absolute_residual_ns"]["q50"] is None else x["absolute_residual_ns"]["q50"]))
    best_name = candidates[0]["candidate"] if candidates else None

    if best_name:
        scale_name, wrap_name = best_name.split("|")
        scale = SCALES_TO_SECONDS[scale_name]
        for row_pairs in retained_rows:
            for ref_sid, sid, raw_delta, predicted in row_pairs:
                if wrap_name == "wrap_60_seconds":
                    observed = circular_difference(raw_delta, 0.0, 60.0 / scale) * scale
                else:
                    observed = raw_delta * scale
                pair_errors_best_later[f"{ref_sid}->{sid}"].append((observed - predicted) * 1e9)

    pair_medians = []
    for pair, errors in pair_errors_best_later.items():
        if len(errors) >= 20:
            s = sorted(errors)
            pair_medians.append({
                "pair": pair,
                "n": len(s),
                "signed_residual_ns_median": percentile(s, 0.5),
                "signed_residual_ns_q05": percentile(s, 0.05),
                "signed_residual_ns_q95": percentile(s, 0.95),
            })
    pair_medians.sort(key=lambda x: (-x["n"], x["pair"]))

    report = {
        "phase": "SAM Phase 5A timestamp consistency audit",
        "scope": "development and eligible_ge4 rows only",
        "inputs": {
            "selected_path": str(args.selected),
            "selected_sha256": selected_hash,
            "sensors_path": str(args.sensors),
            "good_sensors_loaded": len(sensors),
        },
        "sampling": {
            "method": "deterministic SHA-256 row bucket",
            "seed": args.seed,
            "sample_permille": args.sample_permille,
        },
        "counts": dict(counts),
        "raw_timestamp_profile": {
            "values": describe(raw_timestamps),
            "within_message_span": describe(raw_spans),
        },
        "candidate_interpretations": candidates,
        "empirical_best_candidate": best_name,
        "pair_residual_profile_for_best_candidate": {
            "minimum_observations_per_pair": 20,
            "pairs_reported": len(pair_medians),
            "pairs": pair_medians[:100],
        },
        "interpretation_limits": [
            "The empirically best candidate is not a documentation claim.",
            "Large pair-specific residuals indicate that receiver clock-bias calibration may be required.",
            "No test-partition rows are used.",
            "No attack or anomaly label is created.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
