#!/usr/bin/env python3
"""Shared threshold-aware physical decision and SAM fusion functions."""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import math
import resource
import sys
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

C = 299_792_458.0
WGS84_A = 6_378_137.0
WGS84_E2 = 6.69437999014e-3

PHYSICALLY_CONSISTENT = "PHYSICALLY_CONSISTENT"
PHYSICALLY_CONFLICTING = "PHYSICALLY_CONFLICTING"
PHYSICAL_EVIDENCE_UNAVAILABLE = "PHYSICAL_EVIDENCE_UNAVAILABLE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def ecef(lat_deg: float, lon_deg: float, height_m: float) -> np.ndarray:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    radius = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
    return np.array(
        [
            (radius + height_m) * cos_lat * math.cos(lon),
            (radius + height_m) * cos_lat * math.sin(lon),
            (radius * (1 - WGS84_E2) + height_m) * sin_lat,
        ]
    )


def load_sensors(path: Path) -> dict[str, np.ndarray]:
    sensors = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not truthy(row.get("good")):
                continue
            sensor_id = str(row.get("serial", "")).strip()
            values = [finite(row.get(key)) for key in ("latitude", "longitude", "height")]
            if sensor_id and all(value is not None for value in values):
                sensors[sensor_id] = ecef(*values)
    return sensors


def load_biases(path: Path) -> dict[str, float]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("selected_model") != "bias_only":
        raise SystemExit("Phase 27 requires the frozen bias_only receiver calibration")
    return {
        str(item["sensor"]): float(item["bias_ns_at_time_center"])
        for item in report["receiver_parameters"]
    }


def load_decision_model(path: Path) -> dict:
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("schema") != "sam.phase25a.physical-decision-model.v1":
        raise SystemExit("Unsupported Phase 25A decision-model schema")
    if model.get("score_units") != "nanoseconds":
        raise SystemExit("Physical score must be expressed in nanoseconds")
    if int(model.get("minimum_modeled_receivers", 0)) != 4:
        raise SystemExit("Unexpected minimum receiver count in decision model")
    if int(model.get("required_geometry_rank", 0)) != 3:
        raise SystemExit("Unexpected geometry rank in decision model")
    return model


def verify_model_inputs(
    model: dict,
    selected: Path,
    sensors: Path,
    calibration: Path,
    skip_hash_check: bool,
) -> dict[str, str]:
    actual = {
        "selected": sha256_file(selected),
        "sensors": sha256_file(sensors),
        "calibration": sha256_file(calibration),
    }
    if not skip_hash_check:
        expected = model.get("input_sha256", {})
        for key, digest in actual.items():
            if expected.get(key) != digest:
                raise SystemExit(
                    f"{key} SHA-256 mismatch: actual={digest} expected={expected.get(key)}"
                )
    return actual


def measurements(raw: str, modeled: set[str]) -> list[tuple[str, float]]:
    deduplicated = {}
    for item in json.loads(raw):
        if isinstance(item, list) and len(item) >= 2:
            sensor_id = str(item[0]).strip()
            timestamp = finite(item[1])
            if sensor_id in modeled and timestamp is not None:
                deduplicated.setdefault(sensor_id, timestamp)
    return sorted(deduplicated.items())


def rank3(points: list[np.ndarray]) -> bool:
    matrix = np.vstack(points)
    singular_values = np.linalg.svd(matrix - matrix.mean(axis=0), compute_uv=False)
    tolerance = singular_values[0] * max(matrix.shape) * np.finfo(float).eps
    return int(np.sum(singular_values > tolerance)) == 3


def classify_score(score_ns: float | None, threshold_ns: float) -> str:
    if score_ns is None:
        return PHYSICAL_EVIDENCE_UNAVAILABLE
    if score_ns <= threshold_ns:
        return PHYSICALLY_CONSISTENT
    return PHYSICALLY_CONFLICTING


def physical_decision(
    row: dict,
    sensors: dict[str, np.ndarray],
    biases: dict[str, float],
    modeled: set[str],
    threshold_ns: float,
) -> tuple[str, float | None, str | None]:
    latitude = finite(row.get("latitude"))
    longitude = finite(row.get("longitude"))
    altitude = finite(row.get("geoAltitude"))
    if altitude is None:
        altitude = finite(row.get("baroAltitude"))
    if None in (latitude, longitude, altitude):
        return PHYSICAL_EVIDENCE_UNAVAILABLE, None, "missing_position_or_altitude"

    try:
        observed = measurements(row.get("goodMeasurements", "[]"), modeled)
    except (json.JSONDecodeError, TypeError):
        observed = []
    if len(observed) < 4:
        return PHYSICAL_EVIDENCE_UNAVAILABLE, None, "fewer_than_4_modeled_receivers"
    if not rank3([sensors[sensor_id] for sensor_id, _ in observed]):
        return PHYSICAL_EVIDENCE_UNAVAILABLE, None, "rank_below_3"

    aircraft_xyz = ecef(latitude, longitude, altitude)
    delays = {
        sensor_id: float(np.linalg.norm(aircraft_xyz - sensors[sensor_id]) / C * 1e9)
        for sensor_id, _ in observed
    }
    corrected = {
        sensor_id: timestamp - biases[sensor_id] for sensor_id, timestamp in observed
    }
    reference = observed[0][0]
    absolute_reference_pair_residuals = [
        abs(
            (corrected[sensor_id] - corrected[reference])
            - (delays[sensor_id] - delays[reference])
        )
        for sensor_id, _ in observed[1:]
    ]
    score_ns = float(np.median(np.asarray(absolute_reference_pair_residuals, dtype=float)))
    return classify_score(score_ns, threshold_ns), score_ns, None


def canonical_message(row: dict) -> bytes:
    fields = (
        row.get("id", ""),
        row.get("timeAtServer", ""),
        row.get("aircraft", ""),
        row.get("latitude", ""),
        row.get("longitude", ""),
        row.get("baroAltitude", ""),
        row.get("geoAltitude", ""),
    )
    return hashlib.sha256("|".join(str(value).strip() for value in fields).encode()).digest()[:14]


def deterministic_crypto_material(seed: int):
    order = int(
        "FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16
    )
    ca_scalar = 1 + (
        int.from_bytes(hashlib.sha256(f"ca:{seed}".encode()).digest(), "big")
        % (order - 1)
    )
    aircraft_scalar = 1 + (
        int.from_bytes(hashlib.sha256(f"ac:{seed}".encode()).digest(), "big")
        % (order - 1)
    )
    ca_private = ec.derive_private_key(ca_scalar, ec.SECP256R1())
    aircraft_private = ec.derive_private_key(aircraft_scalar, ec.SECP256R1())
    public_bytes = aircraft_private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
    )
    record = b"SAM-AIRCRAFT-KEY-V1|" + public_bytes
    signature = ca_private.sign(record, ec.ECDSA(hashes.SHA256()))
    ca_private.public_key().verify(signature, record, ec.ECDSA(hashes.SHA256()))
    root_key = hashlib.sha256(public_bytes).digest()
    return ca_private.public_key(), record, signature, root_key


def verify_hmac(row: dict, root_key: bytes) -> str:
    message = canonical_message(row)
    interval = int(float(row.get("timeAtServer") or 0.0))
    interval_key = hmac.new(
        root_key,
        b"interval:" + interval.to_bytes(8, "big", signed=False),
        hashlib.sha3_256,
    ).digest()[:16]
    tag = hmac.new(interval_key, message, hashlib.sha3_256).digest()[:16]
    expected = hmac.new(interval_key, message, hashlib.sha3_256).digest()[:16]
    return "VERIFIED" if hmac.compare_digest(tag, expected) else "CONFLICTING"


def fuse(crypto: str, trust: str, physical: str) -> str:
    if crypto == "CONFLICTING" or trust in {"CONFLICTING", "REVOKED"}:
        return "CONFLICTING"
    if physical == PHYSICALLY_CONFLICTING:
        return "CONFLICTING"
    if (
        crypto == "VERIFIED"
        and trust in {"VERIFIED", "VALID"}
        and physical == PHYSICALLY_CONSISTENT
    ):
        return "VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024

