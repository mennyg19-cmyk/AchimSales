#!/usr/bin/env bash
# Azure Startup Command: bash /home/site/wwwroot/startup.sh
#
# Live Azure python3 is Debian 3.11 with no pip. CI vendors site-packages into
# app/deps. Do not exec leftover /home/bin/litestream — that 2023 binary wraps
# gunicorn and exits when the system interpreter has no packages.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-180}"

export APP_DB_PATH="${APP_DB_PATH:-/tmp/homedata/home.sqlite}"
mkdir -p "$(dirname "${APP_DB_PATH}")" 2>/dev/null || true

if [ -d "${ROOT}/deps" ]; then
  export PYTHONPATH="${ROOT}/deps${PYTHONPATH:+:$PYTHONPATH}"
fi

if [ -x "${ROOT}/.venv/bin/python" ]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

echo "startup $(date -u +%Y-%m-%dT%H:%M:%SZ) py=${PY} port=${PORT}" >>/home/LogFiles/home-startup.log 2>/dev/null || true

exec "${PY}" -m gunicorn \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile - \
  main:app
