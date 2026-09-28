#!/bin/zsh
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  print "Python 3 is not installed. Install Python 3.11 or 3.12 from python.org, then rerun this script."
  exit 1
fi

python3 - <<'PY'
import platform, sys
if sys.version_info < (3, 11) or sys.version_info >= (3, 13):
    raise SystemExit("Use Python 3.11 or 3.12 for the frozen SAM environment.")
if platform.machine() not in {"arm64", "aarch64"}:
    print("Warning: this setup was prepared for Apple Silicon; continuing on", platform.machine())
print("Python:", sys.version.split()[0])
print("Architecture:", platform.machine())
PY

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python scripts/verify_environment.py
