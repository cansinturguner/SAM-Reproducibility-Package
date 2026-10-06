#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -x ".venv/bin/python" ]]; then
  phase26_python=".venv/bin/python"
else
  phase26_python="python3"
fi

"$phase26_python" phases/phase26_formal_assurance_logic/scripts/run_phase26.py
"$phase26_python" phases/phase26_formal_assurance_logic/scripts/validate_report.py

