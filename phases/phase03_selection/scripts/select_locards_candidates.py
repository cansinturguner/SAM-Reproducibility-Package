from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = [
    "id", "timeAtServer", "aircraft", "latitude", "longitude",
    "baroAltitude", "geoAltitude", "numMeasurements", "numGoodReceivers",
    "eligible_ge4", "split", "goodSensorIds", "goodMeasurements",
    "receiverMinBaselineM", "receiverMaxBaselineM", "receiverGeometryRank",
    "receiverGeometryRatio", "rawTimestampSpan", "rawSignalMin", "rawSignalMax",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_files(root: Path) -> dict[str, Path]:
    for base in (root, root / "subset_1"):
        paths = {
            "sensors": base / "set_1_sensors.csv",
            "aircraft": base / "set_1_aircraft.csv",
            "observations": base / "set_1.csv",
        }
        if all(path.is_file() for path in paths.values()):
            return paths
    raise FileNotFoundError(f"LocaRDS files not found below {root}")


def parse_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().map({"TRUE": True, "FALSE": False})


def parse_measurements(raw: Any) -> list[list[Any]]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or any(not isinstance(item, list) or len(item) < 3 for item in parsed):
        raise ValueError("Invalid measurement list")
    return parsed


def aircraft_split(aircraft: int, seed: int, development_percent: int) -> str:
    token = f"{seed}:{aircraft}".encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    return "development" if bucket < development_percent else "test"


def geodetic_to_ecef(lat_deg: float, lon_deg: float, height_m: float) -> np.ndarray:
    a = 6378137.0
    e2 = 6.69437999014e-3
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    n = a / np.sqrt(1.0 - e2 * np.sin(lat) ** 2)
    return np.array([
        (n + height_m) * np.cos(lat) * np.cos(lon),
        (n + height_m) * np.cos(lat) * np.sin(lon),
        (n * (1.0 - e2) + height_m) * np.sin(lat),
    ])


def geometry(sensor_ids: list[int], sensor_ecef: dict[int, np.ndarray]) -> tuple[float, float, int, float]:
    points = np.vstack([sensor_ecef[sensor] for sensor in sensor_ids])
    distances = [float(np.linalg.norm(points[i] - points[j])) for i, j in combinations(range(len(points)), 2)]
    centered = points - points.mean(axis=0)
    singular = np.linalg.svd(centered, compute_uv=False)
    rank = int(np.linalg.matrix_rank(centered))
    ratio = float(singular[-1] / singular[0]) if singular[0] > 0 else 0.0
    return min(distances), max(distances), rank, ratio


def validate_phase2(report_path: Path, paths: dict[str, Path]) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key, path in paths.items():
        expected_size = int(report["files"][key]["size_bytes"])
        if path.stat().st_size != expected_size:
            raise ValueError(f"Size mismatch for {key}: expected {expected_size}, got {path.stat().st_size}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Select source-grounded LocaRDS candidates for SAM physical verification.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase2-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--development-percent", type=int, default=30)
    parser.add_argument("--split-seed", type=int, default=1103)
    args = parser.parse_args()
    if not 1 <= args.development_percent <= 99:
        raise ValueError("development-percent must be between 1 and 99")

    paths = resolve_files(args.root)
    phase2 = validate_phase2(args.phase2_report, paths)
    sensors = pd.read_csv(paths["sensors"])
    aircraft_table = pd.read_csv(paths["aircraft"])
    sensors["good_parsed"] = parse_bool(sensors["good"])
    aircraft_table["trusted_parsed"] = parse_bool(aircraft_table["trusted"])
    good_rows = sensors.loc[
        (sensors["good_parsed"] == True)
        & sensors[["latitude", "longitude", "height"]].notna().all(axis=1)
    ].copy()
    good_ids = set(pd.to_numeric(good_rows["serial"], errors="raise").astype(int))
    trusted_ids = set(
        pd.to_numeric(
            aircraft_table.loc[aircraft_table["trusted_parsed"] == True, "aircraft"],
            errors="raise",
        ).astype(int)
    )
    sensor_ecef = {
        int(row.serial): geodetic_to_ecef(float(row.latitude), float(row.longitude), float(row.height))
        for row in good_rows.itertuples(index=False)
    }
    split_map = {aircraft: aircraft_split(aircraft, args.split_seed, args.development_percent) for aircraft in trusted_ids}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "trusted_good_ge3.csv.gz"
    wrote_header = False
    counts = Counter()
    aircraft_by_split = {"development": set(), "test": set()}

    with gzip.open(output_path, "wt", encoding="utf-8", newline="") as output_handle:
        reader = pd.read_csv(paths["observations"], chunksize=args.chunk_size, low_memory=False)
        for chunk_number, chunk in enumerate(reader, start=1):
            counts["input_rows"] += len(chunk)
            aircraft_numeric = pd.to_numeric(chunk["aircraft"], errors="coerce")
            trusted_chunk = chunk.loc[aircraft_numeric.isin(trusted_ids)].copy()
            counts["trusted_rows"] += len(trusted_chunk)
            selected: list[dict[str, Any]] = []
            for row in trusted_chunk.itertuples(index=False):
                try:
                    measurements = parse_measurements(row.measurements)
                except Exception:
                    counts["parse_errors"] += 1
                    continue
                by_sensor: dict[int, list[Any]] = {}
                for measurement in measurements:
                    try:
                        sensor_id = int(measurement[0])
                    except Exception:
                        counts["invalid_sensor_id"] += 1
                        continue
                    if sensor_id in good_ids and sensor_id not in by_sensor:
                        by_sensor[sensor_id] = measurement
                    elif sensor_id in by_sensor:
                        counts["duplicate_good_sensor_measurements"] += 1
                if len(by_sensor) < 3:
                    continue
                sensor_ids = sorted(by_sensor)
                good_measurements = [by_sensor[sensor] for sensor in sensor_ids]
                min_baseline, max_baseline, rank, ratio = geometry(sensor_ids, sensor_ecef)
                raw_times = [float(item[1]) for item in good_measurements]
                raw_signals = [float(item[2]) for item in good_measurements]
                split = split_map[int(row.aircraft)]
                aircraft_by_split[split].add(int(row.aircraft))
                record = {
                    "id": int(row.id),
                    "timeAtServer": float(row.timeAtServer),
                    "aircraft": int(row.aircraft),
                    "latitude": float(row.latitude),
                    "longitude": float(row.longitude),
                    "baroAltitude": None if pd.isna(row.baroAltitude) else float(row.baroAltitude),
                    "geoAltitude": None if pd.isna(row.geoAltitude) else float(row.geoAltitude),
                    "numMeasurements": int(row.numMeasurements),
                    "numGoodReceivers": len(sensor_ids),
                    "eligible_ge4": len(sensor_ids) >= 4,
                    "split": split,
                    "goodSensorIds": json.dumps(sensor_ids, separators=(",", ":")),
                    "goodMeasurements": json.dumps(good_measurements, separators=(",", ":")),
                    "receiverMinBaselineM": min_baseline,
                    "receiverMaxBaselineM": max_baseline,
                    "receiverGeometryRank": rank,
                    "receiverGeometryRatio": ratio,
                    "rawTimestampSpan": max(raw_times) - min(raw_times),
                    "rawSignalMin": min(raw_signals),
                    "rawSignalMax": max(raw_signals),
                }
                selected.append(record)
                counts["selected_ge3"] += 1
                counts["selected_ge4"] += int(record["eligible_ge4"])
                counts[f"selected_{split}"] += 1
                counts[f"selected_ge4_{split}"] += int(record["eligible_ge4"])
            if selected:
                pd.DataFrame(selected, columns=OUTPUT_COLUMNS).to_csv(
                    output_handle, index=False, header=not wrote_header
                )
                wrote_header = True
            print(
                f"Processed chunk {chunk_number}: {counts['input_rows']:,} input; "
                f"{counts['selected_ge3']:,} selected >=3; {counts['selected_ge4']:,} selected >=4"
            )
    if not wrote_header:
        raise RuntimeError("No rows satisfied trusted aircraft and >=3 good receiver criteria")

    manifest = {
        "dataset": "LocaRDS subset 1",
        "source": "https://doi.org/10.5281/zenodo.4739276",
        "phase2_report": str(args.phase2_report),
        "phase2_observation_sha256": phase2["files"]["observations"]["sha256"],
        "selection_rules": [
            "aircraft trusted flag equals TRUE",
            "sensor good flag equals TRUE",
            "sensor latitude, longitude and height are present",
            "at least three distinct good sensors",
            "no attack or anomaly label is created",
            "raw timestamp and signal units are not inferred",
        ],
        "split": {
            "unit": "aircraft identifier",
            "method": "deterministic SHA-256 bucket",
            "seed": args.split_seed,
            "development_percent_target": args.development_percent,
            "development_aircraft": len(aircraft_by_split["development"]),
            "test_aircraft": len(aircraft_by_split["test"]),
            "aircraft_overlap": len(aircraft_by_split["development"] & aircraft_by_split["test"]),
        },
        "counts": {key: int(value) for key, value in counts.items()},
        "output": {
            "path": str(output_path),
            "size_bytes": output_path.stat().st_size,
            "sha256": sha256(output_path),
            "columns": OUTPUT_COLUMNS,
        },
        "geometry_fields": {
            "receiverMinBaselineM": "minimum three-dimensional ECEF distance between selected sensors",
            "receiverMaxBaselineM": "maximum three-dimensional ECEF distance between selected sensors",
            "receiverGeometryRank": "rank of centered receiver ECEF coordinate matrix",
            "receiverGeometryRatio": "smallest/largest singular-value ratio; descriptive only, no threshold applied",
        },
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    print(f"Wrote {args.manifest}")


if __name__ == "__main__":
    main()
