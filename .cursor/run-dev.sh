#!/usr/bin/env bash
# Run the full D365 Sales Reports dispatcher locally with dev auth bypass.
# Serves: / (v3 beta home), /legacy (OData webapp), /test (v3 SQL sandbox),
# /test-next (rebuild preview). No D365/Graph credentials are required; data
# calls degrade gracefully and the UI still renders.
set -u

cd "$(dirname "$0")/.."   # repo root
# shellcheck disable=SC1091
. .venv/bin/activate

# Dev signing secret: generated per boot so nothing secret is committed, and it
# satisfies the >=16 char rule the v3/rebuild configs enforce.
export FLASK_SECRET="${FLASK_SECRET:-$(python -c 'import secrets; print(secrets.token_hex(24))')}"
export FLASK_SECRET_KEY="${FLASK_SECRET_KEY:-$FLASK_SECRET}"

# Legacy webapp (/legacy)
export DEV_BYPASS_AUTH=1

# v3 home (/) + /test sandbox
export APP_ENV=dev
export AUTH_MODE=dev
export BETA_MOUNT_ENABLED=1
export V3_MOUNT_ENABLED=1

# rebuild preview (/test-next)
export REBUILD_MOUNT_ENABLED=1
export REBUILD_APP_ENV=dev
export REBUILD_AUTH_MODE=dev

export PORT="${PORT:-5002}"

exec gunicorn --bind=0.0.0.0:"${PORT}" --workers=1 --worker-class=gthread \
  --threads=8 --timeout=230 --access-logfile=- --error-logfile=- wsgi:application
