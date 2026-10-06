#!/usr/bin/env python3
"""Audit the Mendeley ADS-B injection dataset before any SAM use."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from collections import Counter
from pathlib import Path


PUBLISHED_LABELS = {
    "0": "legitimate",
    "1": "path modification",
    "2": "ghost injection",
    "3": "velocity drift",
}
LABEL_CANDIDATES = ("label", "class", "attack", "attack_type", "target")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalized(name: str) -> str:
    return "".join(ch.lower() for ch in str(name) if ch.isalnum())


def sniff(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(65536)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def find_label_column(fieldnames, requested):
    if requested:
        if requested not in fieldnames:
            raise SystemExit(f"Requested label column not found: {requested}")
        return requested
    by_normalized = {normalized(x): x for x in fieldnames}
    for candidate in LABEL_CANDIDATES:
        if normalized(candidate) in by_normalized:
            return by_normalized[normalized(candidate)]
    return None


def inspect_csv(path: Path, requested_label=None):
    dialect = sniff(path)
    rows = 0
    missing = Counter()
    labels = Counter()
    exact_row_hashes = set()
    duplicates = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = reader.fieldnames or []
        label_column = find_label_column(fieldnames, requested_label)
        for row in reader:
            rows += 1
            canonical = "\x1f".join(str(row.get(k, "")) for k in fieldnames).encode("utf-8")
            digest = hashlib.sha256(canonical).digest()
            if digest in exact_row_hashes:
                duplicates += 1
            else:
                exact_row_hashes.add(digest)
            for key in fieldnames:
                value = row.get(key)
                if value is None or not str(value).strip() or str(value).strip().lower() in {"nan", "na", "null", "none"}:
                    missing[key] += 1
            if label_column:
                raw = str(row.get(label_column, "")).strip()
                try:
                    number = float(raw)
                    key = str(int(number)) if math.isfinite(number) and number.is_integer() else raw
                except ValueError:
                    key = raw
                labels[key] += 1
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "delimiter": dialect.delimiter,
        "rows": rows,
        "columns": fieldnames,
        "column_count": len(fieldnames),
        "label_column": label_column,
        "label_counts": dict(sorted(labels.items())),
        "missing_counts": dict(missing),
        "exact_duplicate_rows": duplicates,
    }


def feature_evidence(columns):
    n = {normalized(x): x for x in columns}

    def matches(tokens):
        return sorted({original for key, original in n.items() if any(token in key for token in tokens)})

    receiver_id = matches(("receiverid", "sensorid", "receiverserial", "sensorserial", "stationid"))
    reception_time = matches(("toa", "timeofarrival", "receptiontime", "receivetime", "timestamp"))
    receiver_lat = matches(("receiverlatitude", "sensorlatitude", "stationlatitude", "receiverlat", "sensorlat"))
    receiver_lon = matches(("receiverlongitude", "sensorlongitude", "stationlongitude", "receiverlon", "sensorlon"))
    message_id = matches(("messageid", "frameid", "packetid", "observationid"))
    return {
        "receiver_identifier_candidates": receiver_id,
        "reception_timestamp_candidates": reception_time,
        "receiver_latitude_candidates": receiver_lat,
        "receiver_longitude_candidates": receiver_lon,
        "shared_message_identifier_candidates": message_id,
        "direct_tdoa_minimum_fields_detected": bool(receiver_id and reception_time and receiver_lat and receiver_lon and message_id),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-csv", type=Path, required=True)
    p.add_argument("--receiver-messages-csv", type=Path)
    p.add_argument("--label-column")
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()

    primary = inspect_csv(a.dataset_csv, a.label_column)
    auxiliary = inspect_csv(a.receiver_messages_csv) if a.receiver_messages_csv else None
    combined_columns = primary["columns"] + (auxiliary["columns"] if auxiliary else [])
    evidence = feature_evidence(combined_columns)
    observed_labels = set(primary["label_counts"])
    labels_match = observed_labels == set(PUBLISHED_LABELS)
    row_count_matches = primary["rows"] == 22316
    label_mapping = {key: {"published_meaning": PUBLISHED_LABELS[key], "observed_rows": primary["label_counts"].get(key, 0)} for key in PUBLISHED_LABELS}

    predictor_count = primary["column_count"] - (1 if primary["label_column"] else 0)
    report = {
        "schema": "sam.phase25c.injection-dataset-audit.v2",
        "source": {
            "title": "ADS-B Message Injection Attacks Dataset",
            "doi": "10.17632/6fhw732ccz.1",
            "version": 1,
            "license": "CC BY 4.0",
            "published_description": {
                "rows": 22316,
                "features": 17,
                "labels": PUBLISHED_LABELS,
            },
        },
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": platform.python_version()},
        "files": {"dataset": primary, "receiver_messages": auxiliary},
        "published_metadata_checks": {
            "row_count_matches_22316": row_count_matches,
            "observed_label_set_matches_0_1_2_3": labels_match,
            "observed_total_column_count": primary["column_count"],
            "observed_predictor_feature_count": predictor_count,
            "predictor_feature_count_matches_17": predictor_count == 17,
            "total_columns_match_17_features_plus_label": primary["column_count"] == 18 and primary["label_column"] is not None,
            "label_mapping": label_mapping,
        },
        "direct_tdoa_field_audit": evidence,
        "suitability": {
            "labeled_message_or_injection_evaluation": "potentially suitable" if row_count_matches and labels_match else "not yet established",
            "sam_direct_tdoa_physical_branch": "potentially suitable; inspect grouping cardinality and coordinate units" if evidence["direct_tdoa_minimum_fields_detected"] else "not suitable from the detected columns",
            "automatic_integration_performed": False,
        },
        "interpretation_limits": [
            "This phase audits the downloaded files; it does not infer absent fields from the dataset title or article.",
            "Published labels support evaluation only for the attack-generation process represented by this dataset.",
            "A labeled message dataset is not automatically suitable for multi-receiver direct-TDoA evaluation.",
            "The dataset is not redistributed by this reproducibility package.",
        ],
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"published_metadata_checks": report["published_metadata_checks"], "direct_tdoa_field_audit": evidence, "suitability": report["suitability"]}, indent=2))


if __name__ == "__main__":
    main()
