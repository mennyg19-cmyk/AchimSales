#!/usr/bin/env bash
# FastAPI home boot. Repo-root startup.sh execs this file, so Azure's existing
# Startup Command (`bash /home/site/wwwroot/startup.sh`) starts this site.
#
# No `set -e`: Litestream download/restore is fail-open. Production still
# refuses to boot without LITESTREAM_AZURE_ACCOUNT_KEY (config.validate_boot).
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-180}"
LS_BIN="/home/bin/litestream"
LS_VERSION="${LITESTREAM_VERSION:-v0.3.13}"
LS_CONFIG="${ROOT}/litestream.yml"

# Local disk, not /home SMB (SQLite WAL). Override with APP_DB_PATH.
export APP_DB_PATH="${APP_DB_PATH:-/tmp/homedata/home.sqlite}"
mkdir -p "$(dirname "${APP_DB_PATH}")" 2>/dev/null || true

# Azure Oryx may not put a `gunicorn` binary on PATH. Same interpreter as boot-diag.
GUNICORN_CMD="python3 -m gunicorn --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --workers ${WORKERS} --timeout ${TIMEOUT} --access-logfile - --error-logfile - main:app"

echo "startup $(date -u +%Y-%m-%dT%H:%M:%SZ) port=${PORT} python=$(command -v python3)" >>/home/LogFiles/home-startup.log 2>/dev/null || true
python3 -m pip install -q -r "${ROOT}/requirements.txt" || echo "startup: pip install warning (continuing)"

if [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${LS_CONFIG}" ]; then
  if [ ! -x "${LS_BIN}" ]; then
    echo "startup: fetching litestream ${LS_VERSION}"
    mkdir -p /home/bin
    if curl -fsSL "https://github.com/benbjohnson/litestream/releases/download/${LS_VERSION}/litestream-${LS_VERSION}-linux-amd64.tar.gz" -o /tmp/litestream.tgz; then
      tar -xzf /tmp/litestream.tgz -C /home/bin litestream || echo "startup: litestream extract failed"
    else
      echo "startup: litestream download failed (continuing without it)"
    fi
  fi
fi

if [ -x "${LS_BIN}" ] && [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${LS_CONFIG}" ]; then
  "${LS_BIN}" restore -config "${LS_CONFIG}" -if-replica-exists -if-db-not-exists "${APP_DB_PATH}" \
    || echo "startup: litestream restore skipped/failed (continuing)"
  echo "startup: launching gunicorn under litestream replicate"
  exec "${LS_BIN}" replicate -config "${LS_CONFIG}" -exec "${GUNICORN_CMD}"
fi

echo "startup: litestream not active; launching gunicorn directly"
exec ${GUNICORN_CMD}
