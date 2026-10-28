#!/usr/bin/env bash
set -euo pipefail
python phases/phase36_fusion_policy_sensitivity/scripts/run_phase36.py \
  --phase34-report reports/sam_phase34_joint_branch_replay.json \
  --report reports/sam_phase36_fusion_policy_sensitivity.json
python phases/phase36_fusion_policy_sensitivity/scripts/validate_report.py \
  reports/sam_phase36_fusion_policy_sensitivity.json
