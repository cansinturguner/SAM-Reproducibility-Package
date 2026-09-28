from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


EXPECTED = {
    "sensors": ["serial", "latitude", "longitude", "height", "type", "good"],
    "aircraft": ["aircraft", "trusted"],
    "observations": [
        "id", "timeAtServer", "aircraft", "latitude", "longitude",
        "baroAltitude", "geoAltitude", "numMeasurements", "measurements",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().map({"TRUE": True, "FALSE": False})


def resolve_files(root: Path) -> dict[str, Path]:
    candidates = [root, root / "subset_1"]
    for base in candidates:
        paths = {
            "sensors": base / "set_1_sensors.csv",
            "aircraft": base / "set_1_aircraft.csv",
            "observations": base / "set_1.csv",
        }
        if all(path.is_file() for path in paths.values()):
            return paths
    raise FileNotFoundError(
        f"Could not find set_1.csv, set_1_sensors.csv and set_1_aircraft.csv under {root}"
    )


def check_columns(actual: list[str], expected: list[str], name: str) -> None:
    if actual != expected:
        raise ValueError(f"Unexpected {name} columns. Expected {expected}; received {actual}")


def parse_measurements(value: Any) -> tuple[list[list[Any]], str | None]:
    if pd.isna(value):
        return [], "missing"
    try:
        parsed = json.loads(value)
    except Exception:
        return [], "invalid_json"
    if not isinstance(parsed, list):
        return [], "not_a_list"
    valid: list[list[Any]] = []
    for item in parsed:
        if not isinstance(item, list) or len(item) < 3:
            return [], "invalid_measurement_shape"
        valid.append(item)
    return valid, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream-audit LocaRDS subset 1 for SAM TDoA experiments.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()

    paths = resolve_files(args.root)
    sensors = pd.read_csv(paths["sensors"])
    aircraft = pd.read_csv(paths["aircraft"])
    check_columns(list(sensors.columns), EXPECTED["sensors"], "sensor")
    check_columns(list(aircraft.columns), EXPECTED["aircraft"], "aircraft")

    sensors["good_parsed"] = parse_bool(sensors["good"])
    aircraft["trusted_parsed"] = parse_bool(aircraft["trusted"])
    known_sensors = set(pd.to_numeric(sensors["serial"], errors="coerce").dropna().astype(int))
    good_sensors = set(
        pd.to_numeric(sensors.loc[sensors["good_parsed"] == True, "serial"], errors="coerce")
        .dropna().astype(int)
    )
    trusted_aircraft = set(
        pd.to_numeric(aircraft.loc[aircraft["trusted_parsed"] == True, "aircraft"], errors="coerce")
        .dropna().astype(int)
    )

    totals = Counter()
    declared_hist = Counter()
    parsed_hist = Counter()
    known_hist = Counter()
    good_hist = Counter()
    errors = Counter()
    unique_aircraft: set[int] = set()
    unique_sensors_seen: set[int] = set()
    time_min: float | None = None
    time_max: float | None = None

    reader = pd.read_csv(paths["observations"], chunksize=args.chunk_size, low_memory=False)
    for chunk_number, chunk in enumerate(reader, start=1):
        if chunk_number == 1:
            check_columns(list(chunk.columns), EXPECTED["observations"], "observation")
        totals["rows"] += len(chunk)
        totals["missing_position"] += int(chunk[["latitude", "longitude"]].isna().any(axis=1).sum())
        declared = pd.to_numeric(chunk["numMeasurements"], errors="coerce")
        for value, count in declared.value_counts(dropna=False).items():
            declared_hist[str(value)] += int(count)
        times = pd.to_numeric(chunk["timeAtServer"], errors="coerce").dropna()
        if not times.empty:
            current_min, current_max = float(times.min()), float(times.max())
            time_min = current_min if time_min is None else min(time_min, current_min)
            time_max = current_max if time_max is None else max(time_max, current_max)
        aircraft_ids = pd.to_numeric(chunk["aircraft"], errors="coerce")
        unique_aircraft.update(aircraft_ids.dropna().astype(int).tolist())
        totals["trusted_aircraft_rows"] += int(aircraft_ids.isin(trusted_aircraft).sum())

        for declared_count, raw in zip(declared.tolist(), chunk["measurements"].tolist()):
            measurements, error = parse_measurements(raw)
            if error:
                errors[error] += 1
                continue
            sensor_ids: list[int] = []
            for measurement in measurements:
                try:
                    sensor_ids.append(int(measurement[0]))
                except Exception:
                    errors["invalid_sensor_id"] += 1
            distinct = set(sensor_ids)
            unique_sensors_seen.update(distinct)
            parsed_count = len(measurements)
            known_count = len(distinct & known_sensors)
            good_count = len(distinct & good_sensors)
            parsed_hist[str(parsed_count)] += 1
            known_hist[str(known_count)] += 1
            good_hist[str(good_count)] += 1
            totals["measurements"] += parsed_count
            if pd.notna(declared_count) and int(declared_count) != parsed_count:
                totals["declared_parsed_mismatch"] += 1
            if known_count >= 3:
                totals["rows_known_receivers_ge_3"] += 1
            if known_count >= 4:
                totals["rows_known_receivers_ge_4"] += 1
            if good_count >= 3:
                totals["rows_good_receivers_ge_3"] += 1
            if good_count >= 4:
                totals["rows_good_receivers_ge_4"] += 1
        print(f"Processed chunk {chunk_number}: {totals['rows']:,} rows")

    report = {
        "dataset": "LocaRDS subset 1",
        "source": "https://doi.org/10.5281/zenodo.4739276",
        "files": {
            key: {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for key, path in paths.items()
        },
        "sensor_table": {
            "rows": int(len(sensors)),
            "unique_serials": int(sensors["serial"].nunique()),
            "good_true": int((sensors["good_parsed"] == True).sum()),
            "good_false": int((sensors["good_parsed"] == False).sum()),
            "good_unknown": int(sensors["good_parsed"].isna().sum()),
        },
        "aircraft_table": {
            "rows": int(len(aircraft)),
            "unique_aircraft": int(aircraft["aircraft"].nunique()),
            "trusted_true": int((aircraft["trusted_parsed"] == True).sum()),
            "trusted_false": int((aircraft["trusted_parsed"] == False).sum()),
            "trusted_unknown": int(aircraft["trusted_parsed"].isna().sum()),
        },
        "observation_table": {
            **{key: int(value) for key, value in totals.items()},
            "unique_aircraft_seen": len(unique_aircraft),
            "unique_sensors_seen": len(unique_sensors_seen),
            "time_min": time_min,
            "time_max": time_max,
            "declared_measurement_histogram": dict(sorted(declared_hist.items(), key=lambda x: x[0])),
            "parsed_measurement_histogram": dict(sorted(parsed_hist.items(), key=lambda x: int(x[0]))),
            "known_receiver_histogram": dict(sorted(known_hist.items(), key=lambda x: int(x[0]))),
            "good_receiver_histogram": dict(sorted(good_hist.items(), key=lambda x: int(x[0]))),
            "parse_errors": dict(errors),
        },
        "interpretation": {
            "ge_3": "Candidate pool for direct-TDoA feasibility analysis; geometry and synchronization checks are still required.",
            "ge_4": "Candidate pool for direct-TDoA and MLAT comparison; geometry and synchronization checks are still required.",
            "security_label": "No attack or anomaly label is created.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
