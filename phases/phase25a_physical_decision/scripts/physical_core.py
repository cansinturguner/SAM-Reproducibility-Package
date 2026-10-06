#!/usr/bin/env python3
"""Shared physical-evidence helpers for SAM Phase 25A/25B."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

C = 299_792_458.0
WGS84_A = 6_378_137.0
WGS84_E2 = 6.69437999014e-3
EARTH_MEAN_RADIUS_M = 6_371_008.8
EXPECTED_SELECTED_SHA256 = "1a4cf881073ec0d4450b76026b6d4e2ecbb9765482382ce7989aa515f8cdadb5"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def finite(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def ecef(lat_deg: float, lon_deg: float, height_m: float) -> np.ndarray:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    return np.array([
        (n + height_m) * cos_lat * math.cos(lon),
        (n + height_m) * cos_lat * math.sin(lon),
        (n * (1.0 - WGS84_E2) + height_m) * sin_lat,
    ])


def ecef_to_geodetic(xyz: np.ndarray) -> tuple[float, float, float]:
    x, y, z = [float(v) for v in xyz]
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(10):
        sin_lat = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        h = p / max(math.cos(lat), 1e-15) - n
        lat_next = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
        if abs(lat_next - lat) < 1e-13:
            lat = lat_next
            break
        lat = lat_next
    sin_lat = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    h = p / max(math.cos(lat), 1e-15) - n
    return math.degrees(lat), math.degrees(lon), h


def destination_point(lat_deg: float, lon_deg: float, distance_m: float, bearing_rad: float) -> tuple[float, float]:
    if distance_m == 0:
        return lat_deg, lon_deg
    lat1, lon1 = math.radians(lat_deg), math.radians(lon_deg)
    delta = distance_m / EARTH_MEAN_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta)
        + math.cos(lat1) * math.sin(delta) * math.cos(bearing_rad)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing_rad) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    lon2 = (lon2 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
    return math.degrees(lat2), math.degrees(lon2)


def load_sensors(path: Path) -> dict[str, np.ndarray]:
    out = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not truthy(row.get("good")):
                continue
            sid = str(row.get("serial", "")).strip()
            vals = [finite(row.get(k)) for k in ("latitude", "longitude", "height")]
            if sid and all(v is not None for v in vals):
                out[sid] = ecef(*vals)
    return out


def load_biases(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("selected_model") != "bias_only":
        raise SystemExit("Phase 25 requires the frozen Phase 5B bias_only clock model")
    out = {}
    for item in data.get("receiver_parameters", []):
        drift = float(item.get("drift_ns_per_hour", 0.0))
        if abs(drift) > 1e-12:
            raise SystemExit("Frozen bias_only calibration contains non-zero drift")
        out[str(item["sensor"])] = float(item["bias_ns_at_time_center"])
    if len(out) < 4:
        raise SystemExit("Calibration contains fewer than four modeled receivers")
    return out


def parse_measurements(raw: str, allowed: set[str]) -> list[tuple[str, float]]:
    dedup = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sid = str(item[0]).strip()
            timestamp = finite(item[1])
            if sid in allowed and timestamp is not None:
                dedup.setdefault(sid, timestamp)
    return sorted(dedup.items())


def geometry_rank(points: list[np.ndarray]) -> int:
    x = np.vstack(points)
    singular = np.linalg.svd(x - x.mean(axis=0), compute_uv=False)
    tol = singular[0] * max(x.shape) * np.finfo(float).eps
    return int(np.sum(singular > tol))


def aircraft_group(aircraft: str, seed: int, calibration_percent: int) -> str:
    token = f"{seed}|{aircraft}".encode()
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    return "calibration" if bucket < calibration_percent else "validation"


def row_position(row: dict) -> tuple[float, float, float] | None:
    lat, lon = finite(row.get("latitude")), finite(row.get("longitude"))
    alt = finite(row.get("geoAltitude"))
    if alt is None:
        alt = finite(row.get("baroAltitude"))
    if None in (lat, lon, alt):
        return None
    return float(lat), float(lon), float(alt)


def physical_inputs(row: dict, sensors: dict[str, np.ndarray], biases: dict[str, float], measurement_field: str):
    position = row_position(row)
    if position is None:
        return None, "missing_position"
    modeled = set(sensors) & set(biases)
    try:
        measurements = parse_measurements(row.get(measurement_field, ""), modeled)
    except (json.JSONDecodeError, TypeError):
        return None, "measurement_parse_error"
    if len(measurements) < 4:
        return None, "fewer_than_4_modeled_receivers"
    if geometry_rank([sensors[sid] for sid, _ in measurements]) != 3:
        return None, "geometry_rank_below_3"
    corrected = {sid: ts - biases[sid] for sid, ts in measurements}
    return {
        "position": position,
        "measurements": measurements,
        "corrected": corrected,
    }, None


def residuals_for_claimed_position(inputs, claimed_position, sensors: dict[str, np.ndarray]) -> np.ndarray:
    claimed_xyz = ecef(*claimed_position)
    measurements = inputs["measurements"]
    corrected = inputs["corrected"]
    delays = {sid: float(np.linalg.norm(claimed_xyz - sensors[sid]) / C * 1e9) for sid, _ in measurements}
    ref = measurements[0][0]
    return np.asarray([
        (corrected[sid] - corrected[ref]) - (delays[sid] - delays[ref])
        for sid, _ in measurements[1:]
    ], dtype=float)


def row_score(residuals: np.ndarray) -> float:
    """Robust observation score frozen for Phase 25: median absolute residual."""
    if residuals.size == 0:
        raise ValueError("row_score requires at least one residual")
    return float(np.median(np.abs(residuals)))


def higher_quantile(values, q: float) -> float:
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        raise ValueError("quantile requires at least one value")
    return float(np.quantile(x, q, method="higher"))


def aircraft_cluster_fraction_ci(counts: dict[str, tuple[int, int]], replicates: int, seed: int) -> dict:
    """Row-weighted fraction with aircraft-cluster bootstrap uncertainty."""
    ids = sorted(counts)
    if not ids:
        return {"estimate": None, "ci95_low": None, "ci95_high": None, "replicates": replicates, "seed": seed}
    numerator = sum(counts[x][0] for x in ids)
    denominator = sum(counts[x][1] for x in ids)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(replicates):
        sampled = rng.choice(ids, size=len(ids), replace=True)
        draw_num = sum(counts[x][0] for x in sampled)
        draw_den = sum(counts[x][1] for x in sampled)
        if draw_den:
            draws.append(draw_num / draw_den)
    return {
        "method": "aircraft-cluster bootstrap with replacement; row-weighted fraction",
        "estimate": numerator / denominator if denominator else None,
        "ci95_low": float(np.quantile(draws, 0.025)) if draws else None,
        "ci95_high": float(np.quantile(draws, 0.975)) if draws else None,
        "replicates": replicates,
        "seed": seed,
        "aircraft": len(ids),
    }


def deterministic_bearing(seed: int, row_id: str, distance_m: float) -> float:
    digest = hashlib.sha256(f"{seed}|{row_id}|{distance_m:.6f}".encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / 2**64
    return 2.0 * math.pi * unit
