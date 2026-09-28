#!/usr/bin/env python3
"""Consolidate the frozen SAM Phase 5D–12 reports without inventing results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def record(path: str) -> dict:
    data = Path(path).read_bytes()
    return {"path": path, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def mean_at_loss(scenarios: list[dict], loss_key: str, loss: float, metric_path: list[str]):
    for item in scenarios:
        if abs(float(item[loss_key]) - loss) < 1e-12:
            value = item
            for key in metric_path:
                value = value[key]
            return value
    raise KeyError(f"loss={loss} not present")


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("phase5d", "phase6", "phase7", "phase8", "phase9", "phase10", "phase11", "phase12"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    paths = {name: getattr(args, name) for name in
             ("phase5d", "phase6", "phase7", "phase8", "phase9", "phase10", "phase11", "phase12")}
    reports = {name: load(path) for name, path in paths.items()}
    p5, p6, p7, p8, p9, p10, p11, p12 = (reports[x] for x in
        ("phase5d", "phase6", "phase7", "phase8", "phase9", "phase10", "phase11", "phase12"))

    required_schemas = {
        "phase8": "sam.phase8.crypto-benchmark.v1",
        "phase9": "sam.phase9.tesla-delayed-auth.v1",
        "phase10": "sam.phase10.identity-trust.v1",
        "phase11": "sam.phase11.evidence-fusion.v1",
        "phase12": "sam.phase12.gating-tesla-ablation.v1",
    }
    for phase, schema in required_schemas.items():
        if reports[phase].get("schema") != schema:
            raise ValueError(f"Unexpected {phase} schema: {reports[phase].get('schema')!r}")

    original = p5["counts"]["test_original_ge4_rows"]
    usable = p5["counts"]["usable_test_rows"]
    if p12["A4_receiver_geometry_gating"]["real_locards_test_original_ge4_rows"] != original:
        raise ValueError("Phase 12 A4 denominator does not match Phase 5D")
    if p12["A4_receiver_geometry_gating"]["rows_supported_by_frozen_modeled_receiver_and_rank_rule"] != usable:
        raise ValueError("Phase 12 A4 numerator does not match Phase 5D")

    loss50_physical = mean_at_loss(
        p6["scenarios"], "independent_receiver_loss_probability", 0.5,
        ["availability_vs_original_ge4", "mean"])
    loss50_direct = mean_at_loss(
        p12["A5_tesla_chain_recovery"]["scenarios"],
        "independent_type_a_and_b1_loss_probability", 0.5,
        ["direct_b1_only", "authentication_availability_vs_received", "mean"])
    loss50_recovery = mean_at_loss(
        p12["A5_tesla_chain_recovery"]["scenarios"],
        "independent_type_a_and_b1_loss_probability", 0.5,
        ["tesla_chain_recovery", "authentication_availability_vs_received", "mean"])

    timing = p8["timing_microseconds_per_message"]
    trust_timing = p10["timing_microseconds_per_operation"]
    full_fast_path_us = (
        p7["summaries"]["wall_microseconds_per_usable_row"]["median"]
        + trust_timing["message_hmac_verification"]["median"]
        + p11["decision_time_microseconds"]["median"]
    )

    report = {
        "schema": "sam.phase13.final-consolidation.v1",
        "scope": {
            "implemented": "traceable consolidation of frozen Phase 5D-12 results and final A0-A7 definitions",
            "not_implemented": [
                "message-level joining of LocaRDS and cryptographic observations",
                "Phase Overlay RF waveform, DO-260C/ED-102B bit-level framing or FEC",
                "raw-IQ overlap recovery",
                "X.509 or global aviation PKI",
                "permissioned-blockchain consensus or ledger writes",
                "certified airborne hardware",
                "attack/anomaly classification",
            ],
            "security_label": "No attack/anomaly dataset, classifier or detection metric is used.",
        },
        "input_reports": {name: record(path) for name, path in paths.items()},
        "evidence_provenance": {
            "real_locards": ["phase5d", "phase6", "phase7"],
            "synthetic_protocol_or_state": ["phase8", "phase9", "phase10", "phase12_A5"],
            "mixed_summary_or_rule_evaluation": ["phase11", "phase12_A4", "phase13"],
            "message_level_join_performed": False,
        },
        "frozen_results": {
            "physical_cross_sensor": {
                "original_test_ge4_rows": original,
                "usable_test_rows": usable,
                "availability": p5["availability"]["fraction"],
                "pair_residual_absolute_q50_ns": p5["pair_residuals"]["absolute_q50_ns"],
                "pair_residual_absolute_q95_ns": p5["pair_residuals"]["absolute_q95_ns"],
                "receiver_loss_50pct_availability_mean": loss50_physical,
            },
            "cryptographic_primitives": {
                "hmac_verification_median_us": timing["hmac_verification"]["median"],
                "ecdsa_verification_median_us": timing["ecdsa_verification"]["median"],
                "negative_protocol_checks_passed": all(p8["correctness"].values()),
            },
            "tesla_delayed_authentication": {
                "messages_per_replicate": p9["configuration"]["transmitted_messages_per_replicate"],
                "loss50_direct_authentication_availability_vs_received_mean": loss50_direct,
                "loss50_chain_recovery_authentication_availability_vs_received_mean": loss50_recovery,
                "loss50_chain_minus_direct_availability": loss50_recovery - loss50_direct,
            },
            "identity_and_trust": {
                "ca_record_verification_median_us": trust_timing["ca_record_verification"]["median"],
                "b2_signature_verification_median_us": trust_timing["b2_signature_verification"]["median"],
                "message_hmac_verification_median_us": trust_timing["message_hmac_verification"]["median"],
                "scenario_states": {x["name"]: x["assurance_state"] for x in p10["trust_service_scenarios"]},
            },
            "fusion": {
                "truth_table_pass_fraction": p11["fusion_truth_table_pass_fraction"],
                "decision_median_us": p11["decision_time_microseconds"]["median"],
            },
        },
        "latency_accounting": {
            "physical_processing_median_us_per_usable_row": p7["summaries"]["wall_microseconds_per_usable_row"]["median"],
            "message_hmac_verification_median_us": trust_timing["message_hmac_verification"]["median"],
            "fusion_decision_median_us": p11["decision_time_microseconds"]["median"],
            "illustrative_sequential_fast_path_sum_us": full_fast_path_us,
            "fast_path_sum_limitation": "Sum combines separately benchmarked prototype operations; it is not a co-executed end-to-end measurement.",
            "tesla_authentication_delay_unit": "seconds",
            "tesla_delay_limitation": "Disclosure-schedule delay is protocol latency and is not added to microsecond compute cost.",
        },
        "logical_communication_sizes_bytes": {
            "type_a_sequence_plus_hmac": 17,
            "b1_disclosed_interval_key": 16,
            "b2_signed_content": p10["logical_communication_bytes_excluding_rf_framing_and_fec"]["signed_b2_content_total"],
            "compact_ca_record": p10["logical_communication_bytes_excluding_rf_framing_and_fec"]["compact_ca_record_total"],
            "excludes": ["RF framing", "FEC", "repetition", "certificates beyond compact prototype", "scheduling"],
        },
        "final_A0_A7": [
            {"id": "A0", "variant": "Legacy baseline", "evidence": "none", "status": "EVALUATED_RULE", "result": "LEGACY_UNASSURED"},
            {"id": "A1", "variant": "Full implemented SAM branches", "evidence": "crypto + trust + physical", "status": "EVALUATED_RULE", "result": "VERIFIED for the all-valid truth-table case"},
            {"id": "A2", "variant": "No cryptographic branch", "evidence": "trust + physical", "status": "EVALUATED_RULE", "result": "INSUFFICIENT_EVIDENCE"},
            {"id": "A3", "variant": "No physical branch", "evidence": "crypto + trust", "status": "EVALUATED_RULE", "result": "INSUFFICIENT_EVIDENCE"},
            {"id": "A4", "variant": "No receiver/geometry gating", "evidence": "real LocaRDS counts", "status": "EVALUATED_AVAILABILITY_ABLATION", "result": f"would admit {original-usable} physically unsupported rows; no verification result assigned"},
            {"id": "A5", "variant": "No TESLA key-chain recovery", "evidence": "paired synthetic loss workload", "status": "EVALUATED_PROTOCOL_ABLATION", "result": f"at 50% loss, direct={loss50_direct:.9f}, recovery={loss50_recovery:.9f}"},
            {"id": "A6", "variant": "Trust service unavailable", "evidence": "deterministic trust-state tests", "status": "EVALUATED_RULE", "result": "valid cache VERIFIED; cold/expired cache INSUFFICIENT_EVIDENCE"},
            {"id": "A7", "variant": "Single-source decision", "evidence": "policy variant", "status": "EVALUATED_POLICY_VARIANT", "result": "relaxed policy can verify from one family; not full-SAM policy"},
        ],
        "claim_boundaries": [
            "A0-A3, A6 and A7 are controlled decision-rule outcomes, not detection-accuracy measurements.",
            "A4 quantifies support availability and does not label unsupported rows as malicious.",
            "A5 quantifies protocol recovery under synthetic independent loss and is not an attack experiment.",
            "No precision, recall, F1, false-positive or false-negative result is produced.",
            "Results characterize the recorded Python/Mac prototype, not certified avionics hardware.",
        ],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": report["schema"],
        "evidence_provenance": report["evidence_provenance"],
        "frozen_results": report["frozen_results"],
        "latency_accounting": report["latency_accounting"],
        "logical_communication_sizes_bytes": report["logical_communication_sizes_bytes"],
        "final_A0_A7": report["final_A0_A7"],
        "claim_boundaries": report["claim_boundaries"],
    }, indent=2))


if __name__ == "__main__":
    main()

