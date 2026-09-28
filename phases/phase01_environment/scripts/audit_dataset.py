from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


OPENSKY_STATE_VECTOR_COLUMNS = {
    "time",
    "icao24",
    "lat",
    "lon",
    "velocity",
    "heading",
    "vertrate",
    "callsign",
    "onground",
    "spi",
    "squawk",
    "baroaltitude",
    "geoaltitude",
    "lastposupdate",
    "lastcontact",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def audit(path: Path) -> dict[str, Any]:
    frame = pd.read_csv(path, low_memory=False)
    columns = list(frame.columns)
    result: dict[str, Any] = {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "rows": int(len(frame)),
        "columns": columns,
        "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "missing_percent": {
            column: round(float(value), 4)
            for column, value in (frame.isna().mean() * 100).items()
        },
        "unique_values": {
            column: int(value) for column, value in frame.nunique(dropna=True).items()
        },
        "duplicate_rows": int(frame.duplicated().sum()),
        "derived_or_unknown_columns": sorted(set(columns) - OPENSKY_STATE_VECTOR_COLUMNS),
        "matches_opensky_state_vector_core": OPENSKY_STATE_VECTOR_COLUMNS.issubset(columns),
        "provenance_status": "UNVERIFIED",
        "label_interpretation": "NOT_ASSUMED",
    }
    if "icao24" in frame:
        result["unique_aircraft"] = int(frame["icao24"].nunique(dropna=True))
    if "time" in frame:
        times = pd.to_numeric(frame["time"], errors="coerce")
        if times.notna().any():
            result["time_min_utc"] = pd.to_datetime(times.min(), unit="s", utc=True).isoformat()
            result["time_max_utc"] = pd.to_datetime(times.max(), unit="s", utc=True).isoformat()
            unique_times = sorted(times.dropna().unique())
            gaps = pd.Series(unique_times).diff().dropna()
            result["time_step_mode_seconds"] = scalar(gaps.mode().iloc[0]) if not gaps.empty else None
    if "label" in frame:
        counts = frame["label"].value_counts(dropna=False).sort_index()
        result["label_counts"] = {str(scalar(k)): int(v) for k, v in counts.items()}
        result["warnings"] = [
            "The meaning and creation method of label values are undocumented.",
            "Do not use label values for security, attack, or anomaly claims until provenance is recovered.",
        ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a candidate SAM experiment CSV without interpreting labels.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
