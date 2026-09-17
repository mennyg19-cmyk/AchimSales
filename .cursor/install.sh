#!/usr/bin/env bash
# Cloud Agent bootstrap for the parked FastAPI home (app/).
# Idempotent so it can bake an environment build.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

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
pip install -q -r app/requirements.txt

# CodeGraph CLI + project index (structural lookup for agents / walkthroughs)
export PATH="$HOME/.local/bin:$PATH"
if ! command -v codegraph >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
if [ -d .codegraph ]; then
  codegraph sync || true
else
  codegraph init || true
fi

echo "install.sh: environment ready"
