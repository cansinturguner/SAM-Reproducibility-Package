#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SEED=1103
mkdir -p reports data/processed/locards_subset_1

"$PYTHON_BIN" scripts/verify_inputs.py

run() {
  echo "Running $1"
  shift
  "$PYTHON_BIN" "$@"
}

run phase02 phases/phase02_dataset_audit/scripts/audit_locards.py \
  --root data/raw/locards/subset_1 --output reports/locards_subset_1_audit.json --chunk-size 100000

run phase03 phases/phase03_selection/scripts/select_locards_candidates.py \
  --root data/raw/locards/subset_1 --phase2-report reports/locards_subset_1_audit.json \
  --output-dir data/processed/locards_subset_1 \
  --manifest reports/locards_subset_1_selection_manifest.json \
  --chunk-size 100000 --development-percent 30 --split-seed "$SEED"

SELECTED_SHA256=$("$PYTHON_BIN" -c 'import json; print(json.load(open("reports/locards_subset_1_selection_manifest.json"))["output"]["sha256"])')

run phase04 phases/phase04_geometry/scripts/profile_receiver_geometry.py \
  --input data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --output reports/locards_subset_1_geometry_development.json \
  --expected-sha256 "$SELECTED_SHA256"

run phase05a phases/phase05a_timestamp/scripts/audit_timestamp_semantics.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --output reports/locards_subset_1_timestamp_audit.json --sample-permille 200 --seed "$SEED" \
  --expected-selected-sha256 "$SELECTED_SHA256"

run phase05b phases/phase05b_calibration/scripts/calibrate_receiver_clocks.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --report reports/locards_subset_1_clock_calibration.json \
  --calibration-output data/processed/locards_subset_1/receiver_clock_calibration.json \
  --seed "$SEED" --calibration-percent 70 \
  --expected-selected-sha256 "$SELECTED_SHA256"

run phase05c phases/phase05c_geometry_validation/scripts/validate_geometry_rules.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_geometry_validation.json --seed "$SEED" --calibration-percent 70 \
  --expected-selected-sha256 "$SELECTED_SHA256"

run phase05d phases/phase05d_frozen_test/scripts/run_frozen_test.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_frozen_test.json --bootstrap-replicates 2000 --bootstrap-seed "$SEED" \
  --expected-selected-sha256 "$SELECTED_SHA256"

run phase06 phases/phase06_receiver_loss/scripts/evaluate_receiver_loss.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_receiver_loss.json \
  --loss-probabilities 0,0.1,0.2,0.3,0.4,0.5 --replicates 30 --seed "$SEED" \
  --expected-selected-sha256 "$SELECTED_SHA256"

run phase07 phases/phase07_physical_benchmark/scripts/benchmark_physical_verification.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --output reports/locards_subset_1_phase7_benchmark.json --warmups 1 --repeats 5 \
  --expected-selected-sha256 "$SELECTED_SHA256"

run phase08 phases/phase08_crypto/scripts/run_crypto_verification.py \
  --report reports/sam_phase8_crypto.json --seed "$SEED" --messages 10000 --repetitions 5
run phase08_validation phases/phase08_crypto/scripts/validate_report.py reports/sam_phase8_crypto.json

run phase09 phases/phase09_tesla/scripts/run_tesla_experiment.py \
  --report reports/sam_phase9_tesla.json --seed "$SEED" --duration-seconds 600 \
  --interval-seconds 1 --message-rate 6.2 --replicates 200 \
  --loss-probabilities 0,0.1,0.2,0.3,0.4,0.5
run phase09_validation phases/phase09_tesla/scripts/validate_report.py reports/sam_phase9_tesla.json

run phase10 phases/phase10_identity_trust/scripts/run_identity_trust_experiment.py \
  --report reports/sam_phase10_identity_trust.json --seed "$SEED" \
  --iterations 10000 --repetitions 5 --cache-ttl-seconds 900
run phase10_validation phases/phase10_identity_trust/scripts/validate_report.py reports/sam_phase10_identity_trust.json

run phase11 phases/phase11_fusion/scripts/run_fusion_experiment.py \
  --phase5d reports/locards_subset_1_frozen_test.json --phase8 reports/sam_phase8_crypto.json \
  --phase9 reports/sam_phase9_tesla.json --phase10 reports/sam_phase10_identity_trust.json \
  --report reports/sam_phase11_evidence_fusion.json --iterations 100000 --repetitions 5
run phase11_validation phases/phase11_fusion/scripts/validate_report.py reports/sam_phase11_evidence_fusion.json

run phase12 phases/phase12_ablation/scripts/run_gating_tesla_ablation.py \
  --phase5d reports/locards_subset_1_frozen_test.json --phase9 reports/sam_phase9_tesla.json \
  --report reports/sam_phase12_gating_tesla_ablation.json
run phase12_validation phases/phase12_ablation/scripts/validate_report.py reports/sam_phase12_gating_tesla_ablation.json

run phase13 phases/phase13_consolidation/scripts/consolidate_results.py \
  --phase5d reports/locards_subset_1_frozen_test.json \
  --phase6 reports/locards_subset_1_receiver_loss.json \
  --phase7 reports/locards_subset_1_phase7_benchmark.json \
  --phase8 reports/sam_phase8_crypto.json --phase9 reports/sam_phase9_tesla.json \
  --phase10 reports/sam_phase10_identity_trust.json \
  --phase11 reports/sam_phase11_evidence_fusion.json \
  --phase12 reports/sam_phase12_gating_tesla_ablation.json \
  --report reports/sam_phase13_final_consolidation.json
run phase13_validation phases/phase13_consolidation/scripts/validate_report.py reports/sam_phase13_final_consolidation.json

run phase14 phases/phase14_integrated/scripts/run_integrated_pipeline.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase14_integrated_pipeline.json --seed "$SEED" --warmups 1 --repetitions 30 \
  --expected-selected-sha256 "$SELECTED_SHA256"
run phase14_validation phases/phase14_integrated/scripts/validate_report.py reports/sam_phase14_integrated_pipeline.json

run phase15 phases/phase15_trust_network/scripts/run_trust_network.py \
  --report reports/sam_phase15_trust_network.json --seed "$SEED" \
  --rtt-ms 0,10,50,100,250 --concurrency 1,8,32 \
  --requests-per-scenario 64 --repetitions 5 --cache-ttl-seconds 900
run phase15_validation phases/phase15_trust_network/scripts/validate_report.py reports/sam_phase15_trust_network.json

run phase16 phases/phase16_overhead/scripts/evaluate_overhead.py \
  --report reports/sam_phase16_communication_overhead.json --seed "$SEED" \
  --duration-seconds 3600 --message-rates 2,6.2,10 --aircraft-counts 1,50,200 --b2-period-seconds 60
run phase16_validation phases/phase16_overhead/scripts/validate_report.py reports/sam_phase16_communication_overhead.json

run phase17 phases/phase17_trust_refresh/scripts/run_phase17.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase17_integrated_trust_refresh_v2.json \
  --seed "$SEED" --repetitions 5 --retry-interval-seconds 60 \
  --expected-selected-sha256 "$SELECTED_SHA256"
run phase17_validation phases/phase17_trust_refresh/scripts/validate_report.py reports/sam_phase17_integrated_trust_refresh_v2.json

run phase18 phases/phase18_conformance/scripts/run_phase18.py \
  --report reports/sam_phase18_protocol_conformance.json --seed "$SEED" --iterations 10000 --repetitions 5
run phase18_validation phases/phase18_conformance/scripts/validate_report.py reports/sam_phase18_protocol_conformance.json

run phase19a phases/phase19a_baselines/scripts/run_phase19a.py \
  --report reports/sam_phase19a_authentication_baselines.json --seed "$SEED" \
  --message-count 10000 --repetitions 10 --message-rate 6.2
run phase19a_validation phases/phase19a_baselines/scripts/validate_report.py reports/sam_phase19a_authentication_baselines.json

run phase19b phases/phase19b_boundary/scripts/run_phase19b.py \
  --phase14 reports/sam_phase14_integrated_pipeline.json \
  --phase17 reports/sam_phase17_integrated_trust_refresh_v2.json \
  --phase19a reports/sam_phase19a_authentication_baselines.json \
  --report reports/sam_phase19b_system_boundary.json --seed "$SEED" --bootstrap-replicates 10000
run phase19b_validation phases/phase19b_boundary/scripts/validate_report.py reports/sam_phase19b_system_boundary.json

run phase20 phases/phase20_scalability/scripts/run_phase20.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase20_concurrent_scalability.json --seed "$SEED" \
  --concurrency 1 2 4 --warmups 1 --repetitions 5 \
  --expected-selected-sha256 "$SELECTED_SHA256"
run phase20_validation phases/phase20_scalability/scripts/validate_report.py reports/sam_phase20_concurrent_scalability.json

run phase21 phases/phase21_component_latency/scripts/run_phase21.py \
  --selected data/processed/locards_subset_1/trusted_good_ge3.csv.gz \
  --sensors data/raw/locards/subset_1/set_1_sensors.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase21_component_latency.json --seed "$SEED" \
  --warmup-rows 1000 --repetitions 5 \
  --expected-selected-sha256 "$SELECTED_SHA256"
run phase21_validation phases/phase21_component_latency/scripts/validate_report.py reports/sam_phase21_component_latency.json

run phase22 phases/phase22_external/scripts/run_phase22.py \
  --observations data/raw/locards/subset_2/set_2.csv \
  --sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --primary reports/locards_subset_1_frozen_test.json \
  --report reports/sam_phase22_external_validation.json --seed "$SEED" --bootstrap-replicates 2000
run phase22_validation phases/phase22_external/scripts/validate_report.py reports/sam_phase22_external_validation.json

run phase22b phases/phase22b_tail/scripts/run_phase22b.py \
  --observations data/raw/locards/subset_2/set_2.csv \
  --sensors data/raw/locards/subset_2/set_2_sensors.csv \
  --aircraft data/raw/locards/subset_2/set_2_aircraft.csv \
  --calibration data/processed/locards_subset_1/receiver_clock_calibration.json \
  --report reports/sam_phase22b_tail_audit.json
run phase22b_validation phases/phase22b_tail/scripts/validate_report.py reports/sam_phase22b_tail_audit.json

run phase23 phases/phase23_cabba_comparison/scripts/run_phase23.py \
  --report reports/sam_phase23_cabba_comparison.json --seed "$SEED" \
  --message-count 10000 --repetitions 10 --message-rate 6.2
run phase23_validation phases/phase23_cabba_comparison/scripts/validate_report.py \
  reports/sam_phase23_cabba_comparison.json

run phase24 phases/phase24_rf_waveform_feasibility/scripts/run_phase24.py \
  --report reports/sam_phase24_rf_waveform_feasibility_v2.json --seed "$SEED" \
  --packets-per-ebno 10000 --highest-ebno-packets 20000 \
  --ebno-db 8 10 12 14 15 16 18
run phase24_validation phases/phase24_rf_waveform_feasibility/scripts/validate_report.py \
  reports/sam_phase24_rf_waveform_feasibility_v2.json

echo "All implemented SAM phases completed and validated."
