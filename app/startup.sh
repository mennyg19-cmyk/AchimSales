#!/usr/bin/env bash
# Azure App Service startup. Set Startup Command to:
#   bash /home/site/wwwroot/startup.sh
#
# This is the NEW rebuild site only. Never point achim-sales-reports at this
# script. That app still runs the old Flask site from repo-root startup.sh.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

pip install -q -r "${ROOT}/requirements.txt" || echo "startup: pip install warning (continuing)"

exec gunicorn \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile - \
  main:app
