#!/usr/bin/env bash
# Azure App Service (Python on Oryx) startup command.
#
# Set the App Service "Startup Command" to:  bash /home/site/wwwroot/startup.sh
#
# Responsibilities, in order:
#   1. (Defensive) pip install the deployed requirements.
#   2. Best-effort Litestream: restore precious.db from Azure Blob on a cold
#      instance, then run gunicorn UNDER `litestream replicate` so every write is
#      streamed offsite. This is the durability story for precious.db (rule 5).
#   3. Launch gunicorn with --config=gunicorn.conf.py so the leader-election
#      post_fork hook runs (exactly ONE worker owns the email-distribution loop
#      AND the v3 job worker + scheduler -- no duplicate sends).
#
# CRITICAL: this process also serves the LIVE production app at "/" via the
# dispatcher, so every Litestream step is FAIL-OPEN. If the binary can't be
# fetched, the config is wrong, or a restore fails, we log it and fall back to
# launching gunicorn directly. Litestream must never cause an outage.
#
# NOTE: no `set -e` on purpose -- a non-zero from a best-effort step must not
# abort the boot.
set -u

ROOT="/home/site/wwwroot"
WORKERS="${WEB_CONCURRENCY:-2}"
THREADS="${GUNICORN_THREADS:-8}"
# 230s aligns with Azure App Service's front-end idle cap. Big report exports
# build the .xlsx synchronously in-request (openpyxl styles every cell), so a
# short worker timeout would kill the worker mid-build and surface as a generic
# "could not build" in the browser. Override via the GUNICORN_TIMEOUT app setting.
TIMEOUT="${GUNICORN_TIMEOUT:-230}"
PORT="${PORT:-8000}"
LS_BIN="/home/bin/litestream"
LS_VERSION="${LITESTREAM_VERSION:-v0.3.13}"

GUNICORN_CMD="gunicorn --config=${ROOT}/gunicorn.conf.py --bind=0.0.0.0:${PORT} --workers=${WORKERS} --worker-class=gthread --threads=${THREADS} --timeout=${TIMEOUT} --access-logfile=- --error-logfile=- wsgi:application"

# 1. Defensive dependency install (Oryx usually already did this on deploy).
pip install -q -r "${ROOT}/requirements.txt" || echo "startup: pip install warning (continuing)"

# 2. Litestream (only when a key + config are present).
if [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${ROOT}/litestream.yml" ]; then
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

if [ -x "${LS_BIN}" ] && [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${ROOT}/litestream.yml" ]; then
  mkdir -p "$(dirname "${PRECIOUS_DB_PATH:-/home/site/v3data/precious.db}")" 2>/dev/null || true
  # Restore only when there's no local DB AND a replica exists (never clobber a
  # live local DB). On the persistent /home path this is normally a no-op.
  "${LS_BIN}" restore -config "${ROOT}/litestream.yml" -if-replica-exists -if-db-not-exists "${PRECIOUS_DB_PATH}" \
    || echo "startup: litestream restore skipped/failed (continuing)"
  echo "startup: launching gunicorn under litestream replicate"
  exec "${LS_BIN}" replicate -config "${ROOT}/litestream.yml" -exec "${GUNICORN_CMD}"
fi

# 3. Fallback: no Litestream -> launch gunicorn directly (still --config, so the
#    leader gate is active either way).
echo "startup: litestream not active; launching gunicorn directly"
exec ${GUNICORN_CMD}
