#!/usr/bin/env python3
"""Validate the Phase 26 report and truth-table artifact."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"Phase 26 validation failed: {message}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    report_path = repo_root / "reports" / "sam_phase26_formal_assurance_logic.json"
    csv_path = repo_root / "reports" / "sam_phase26_formal_assurance_truth_table.csv"
    if not report_path.is_file() or not csv_path.is_file():
        fail("required report artifact is missing")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if report.get("schema") != "sam.phase26.formal-assurance-logic.v1":
        fail("unexpected schema")
    if len(rows) != 48:
        fail(f"expected 48 secured-policy rows, observed {len(rows)}")
    if len({(r["crypto"], r["trust"], r["physical"]) for r in rows}) != 48:
        fail("truth table contains duplicate or missing state combinations")
    if not all(r["matches_specification"] == "True" for r in rows):
        fail("implementation/specification mismatch")

    counts = Counter(r["decision"] for r in rows)
    expected_counts = {
        "CONFLICTING": 30,
        "INSUFFICIENT_EVIDENCE": 17,
        "VERIFIED": 1,
    }
    if dict(counts) != expected_counts:
        fail(f"unexpected decision distribution: {dict(counts)}")
    if report.get("decision_distribution") != expected_counts:
        fail("JSON and CSV decision distributions differ")
    if not all(report.get("properties", {}).values()):
        fail("one or more policy properties failed")
    if not all(item.get("passed") for item in report.get("transition_checks", [])):
        fail("one or more transition checks failed")
    mutations = report.get("mutation_checks", [])
    if len(mutations) != 4 or not all(item.get("killed") for item in mutations):
        fail("mutation checks did not reject every faulty policy")
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if digest != report.get("artifacts", {}).get("truth_table_sha256"):
        fail("truth-table SHA-256 mismatch")
    if report.get("overall_pass") is not True:
        fail("overall_pass is not true")

    print("SAM Phase 26 formal assurance logic validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

