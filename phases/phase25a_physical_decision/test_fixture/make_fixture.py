#!/usr/bin/env python3
"""Create a deterministic structural fixture; never use its numbers in the paper."""

from __future__ import annotations

import csv
import gzip
import json
import math
from pathlib import Path

import numpy as np


C = 299_792_458.0
A = 6_378_137.0
E2 = 6.69437999014e-3


def ecef(lat_deg, lon_deg, h):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    return np.array([(n + h) * math.cos(lat) * math.cos(lon), (n + h) * math.cos(lat) * math.sin(lon), (n * (1 - E2) + h) * math.sin(lat)])


def main():
    root = Path(__file__).resolve().parent
    sensors = [
        ("101", 40.00, 29.00, 10.0, 40.0),
        ("102", 40.35, 29.00, 140.0, -25.0),
        ("103", 40.00, 29.45, 260.0, 80.0),
        ("104", 40.40, 29.50, 25.0, -60.0),
        ("105", 40.18, 29.24, 520.0, 15.0),
    ]
    sensor_path = root / "sensors.csv"
    with sensor_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["serial", "latitude", "longitude", "height", "type", "good"])
        for sid, lat, lon, h, _ in sensors:
            w.writerow([sid, lat, lon, h, "fixture", "TRUE"])
    calibration = {
        "selected_model": "bias_only",
        "receiver_parameters": [
            {"sensor": sid, "bias_ns_at_time_center": bias, "drift_ns_per_hour": 0.0}
            for sid, _, _, _, bias in sensors
        ],
    }
    (root / "calibration.json").write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")

    xyz = {sid: ecef(lat, lon, h) for sid, lat, lon, h, _ in sensors}
    bias = {sid: b for sid, _, _, _, b in sensors}
    fields = ["id", "timeAtServer", "aircraft", "latitude", "longitude", "baroAltitude", "geoAltitude", "numMeasurements", "numGoodReceivers", "eligible_ge4", "split", "goodSensorIds", "goodMeasurements"]
    rows = []
    for index in range(240):
        split = "development" if index < 160 else "test"
        aircraft = f"D{index // 8:03d}" if split == "development" else f"T{(index - 160) // 8:03d}"
        lat = 40.10 + 0.002 * (index % 17)
        lon = 29.12 + 0.0025 * (index % 13)
        alt = 8500.0 + 20.0 * (index % 19)
        aircraft_xyz = ecef(lat, lon, alt)
        base = 1_000_000_000_000.0 + index * 1_000_000.0
        noise = [0.0, ((index * 7) % 23 - 11) * 3.0, ((index * 11) % 29 - 14) * 2.5, ((index * 13) % 31 - 15) * 2.0, ((index * 17) % 37 - 18) * 1.5]
        measurements = []
        for j, (sid, _, _, _, _) in enumerate(sensors):
            delay = np.linalg.norm(aircraft_xyz - xyz[sid]) / C * 1e9
            measurements.append([sid, base + delay + bias[sid] + noise[j], -80.0 + j])
        rows.append({
            "id": str(index + 1), "timeAtServer": str(index), "aircraft": aircraft,
            "latitude": lat, "longitude": lon, "baroAltitude": alt, "geoAltitude": alt,
            "numMeasurements": 5, "numGoodReceivers": 5, "eligible_ge4": "True", "split": split,
            "goodSensorIds": json.dumps([x[0] for x in measurements]), "goodMeasurements": json.dumps(measurements),
        })
    with gzip.open(root / "selected.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    with (root / "subset2_aircraft.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["aircraft", "trusted"])
        for name in sorted({row["aircraft"] for row in rows[-80:]}):
            w.writerow([name, "TRUE"])
    with (root / "subset2.csv").open("w", newline="", encoding="utf-8") as f:
        out_fields = ["id", "timeAtServer", "aircraft", "latitude", "longitude", "baroAltitude", "geoAltitude", "measurements"]
        w = csv.DictWriter(f, fieldnames=out_fields); w.writeheader()
        for row in rows[-80:]:
            w.writerow({key: row[key] for key in out_fields[:-1]} | {"measurements": row["goodMeasurements"]})
    print(root)


if __name__ == "__main__":
    main()
