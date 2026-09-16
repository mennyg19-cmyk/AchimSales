#!/usr/bin/env bash
# Azure Startup Command: bash /home/site/wwwroot/startup.sh
#
# Live Azure python3 in Kudu is Debian 3.11 with no pip. CI vendors
# site-packages into app/deps. sqlite lives on /tmp (not /home SMB WAL).
# Litestream restore/replicate is what survives an Azure recycle.
# Replica blob is home.sqlite — never Flask precious.db.
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

GUNICORN_CMD="${PY} -m gunicorn --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT} --workers ${WORKERS} --timeout ${TIMEOUT} --access-logfile - --error-logfile - main:app"

log() {
  echo "startup $(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >>/home/LogFiles/home-startup.log 2>/dev/null || true
}

log "py=${PY} port=${PORT} db=${APP_DB_PATH}"

if [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${LS_CONFIG}" ]; then
  if [ ! -x "${LS_BIN}" ]; then
    log "fetching litestream ${LS_VERSION}"
    mkdir -p /home/bin
    if curl -fsSL "https://github.com/benbjohnson/litestream/releases/download/${LS_VERSION}/litestream-${LS_VERSION}-linux-amd64.tar.gz" -o /tmp/litestream.tgz; then
      tar -xzf /tmp/litestream.tgz -C /home/bin litestream || log "litestream extract failed"
    else
      log "litestream download failed (continuing without it)"
    fi
  fi
fi

if [ -x "${LS_BIN}" ] && [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${LS_CONFIG}" ]; then
  "${LS_BIN}" restore -config "${LS_CONFIG}" -if-replica-exists -if-db-not-exists "${APP_DB_PATH}" \
    || log "litestream restore skipped/failed (continuing)"
  log "launching gunicorn under litestream replicate"
  exec "${LS_BIN}" replicate -config "${LS_CONFIG}" -exec "${GUNICORN_CMD}"
fi

log "litestream not active; launching gunicorn directly"
exec ${GUNICORN_CMD}
