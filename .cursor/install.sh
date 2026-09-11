#!/usr/bin/env bash
# Cloud Agent environment bootstrap: Python deps (in a venv) + built v3 front-end assets.
# Idempotent and non-interactive so it can be re-run or used to bake an environment build.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

# 1. Python venv. The stock image ships python3 without the venv module, so make
#    sure the matching venv package is present before creating .venv.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  PY_MINOR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  sudo apt-get update -q
  sudo apt-get install -y -q "python${PY_MINOR}-venv"
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r webapp/requirements.txt   # superset: Flask + v3 + azure + gunicorn
pip install -q -r v3/requirements.txt        # v3-only extras (pinned ranges)

# 2. v3 front-end assets (esbuild). Needed by the home "/" and "/test" mounts.
if ! command -v npm >/dev/null 2>&1; then
  # Load nvm-managed node when npm is not already on PATH.
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
fi
( cd v3 && npm install --no-audit --no-fund && npm run build )

echo "install.sh: environment ready"
