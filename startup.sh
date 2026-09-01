#!/usr/bin/env bash
# Azure App Service (Python on Oryx) startup command.
#
# Set the App Service "Startup Command" to:  bash /home/site/wwwroot/startup.sh
#
# Responsibilities, in order:
#   1. (Defensive) pip install the deployed requirements.
#   2. Litestream restore + replicate the ONE home-site database (required when
#      APP_ENV=prod). Canonical env: SITE_PRECIOUS_DB_PATH / LITESTREAM_AZURE_SITE_PATH.
#      BETA_* names are aliases until Azure is renamed.
#   3. Launch tools/supervise-web.sh under Litestream: bootstrap, then Gunicorn
#      (HTTP) and python -m web.worker_main (jobs + scheduler) as siblings.
#      If either process exits, the supervisor stops the other so the platform
#      restarts the unit. One App Service instance while SQLite is used.
#
# CRITICAL: in APP_ENV=prod this process must not serve an empty precious.db.
# Restore failure, missing Litestream settings, a zero-byte/corrupt file, or a
# database with no users abort boot. Local APP_ENV=dev still falls back to
# gunicorn without Litestream.
#
# NOTE: no `set -e` on purpose -- a non-zero from a best-effort step must
# not abort the boot. Prod Litestream failures use explicit `exit 1`.
set -u

ROOT="${STARTUP_ROOT:-/home/site/wwwroot}"
WORKERS="${WEB_CONCURRENCY:-2}"
THREADS="${GUNICORN_THREADS:-8}"
# 230s aligns with Azure App Service's front-end idle cap. Big report exports
# build the .xlsx synchronously in-request (openpyxl styles every cell), so a
# short worker timeout would kill the worker mid-build and surface as a generic
# "could not build" in the browser. Override via the GUNICORN_TIMEOUT app setting.
TIMEOUT="${GUNICORN_TIMEOUT:-230}"
PORT="${PORT:-8000}"
# Same as v3/web/config.py: strip + lowercase. Unknown values refuse boot.
APP_ENV="${APP_ENV:-prod}"
APP_ENV="$(printf '%s' "${APP_ENV}" | tr '[:upper:]' '[:lower:]')"
APP_ENV="${APP_ENV#"${APP_ENV%%[![:space:]]*}"}"
APP_ENV="${APP_ENV%"${APP_ENV##*[![:space:]]}"}"
if [ -z "${APP_ENV}" ]; then
  APP_ENV=prod
fi
if [ "${APP_ENV}" != "dev" ] && [ "${APP_ENV}" != "prod" ]; then
  echo "startup: APP_ENV must be 'dev' or 'prod', got ${APP_ENV}"
  exit 1
fi
export APP_ENV
LS_BIN="${LITESTREAM_BIN:-/home/bin/litestream}"
LS_VERSION="${LITESTREAM_VERSION:-v0.3.13}"
# sha256 of litestream-v0.3.13-linux-amd64.tar.gz (GitHub release asset).
LS_SHA256="${LITESTREAM_SHA256:-eb75a3de5cab03875cdae9f5f539e6aedadd66607003d9b1e7a9077948818ba0}"
PYTHON="${PYTHON:-python3}"

GUNICORN_CMD="gunicorn --config=${ROOT}/gunicorn.conf.py --bind=0.0.0.0:${PORT} --workers=${WORKERS} --worker-class=gthread --threads=${THREADS} --timeout=${TIMEOUT} --access-logfile=- --error-logfile=- wsgi:application"
export GUNICORN_CMD
export STARTUP_ROOT="${ROOT}"
export PYTHONPATH="${ROOT}/v3:${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
SUPERVISE_CMD="bash ${ROOT}/tools/supervise-web.sh"

# 1. Defensive dependency install (Oryx usually already did this on deploy).
if [ -z "${STARTUP_SKIP_PIP:-}" ]; then
  pip install -q -r "${ROOT}/requirements.txt" || echo "startup: pip install warning (continuing)"
fi

# Canonical SITE_* from BETA_* aliases (Azure still has BETA_* today).
if [ -z "${SITE_PRECIOUS_DB_PATH:-}" ] && [ -n "${BETA_PRECIOUS_DB_PATH:-}" ]; then
  export SITE_PRECIOUS_DB_PATH="${BETA_PRECIOUS_DB_PATH}"
fi
if [ -z "${SITE_CACHE_DB_PATH:-}" ] && [ -n "${BETA_CACHE_DB_PATH:-}" ]; then
  export SITE_CACHE_DB_PATH="${BETA_CACHE_DB_PATH}"
fi
if [ -z "${LITESTREAM_AZURE_SITE_PATH:-}" ] && [ -n "${LITESTREAM_AZURE_BETA_PATH:-}" ]; then
  export LITESTREAM_AZURE_SITE_PATH="${LITESTREAM_AZURE_BETA_PATH}"
fi

PRECIOUS="${SITE_PRECIOUS_DB_PATH:-}"

# 2. Litestream (required in prod).
if [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${ROOT}/litestream.yml" ]; then
  if [ ! -x "${LS_BIN}" ]; then
    echo "startup: fetching litestream ${LS_VERSION}"
    mkdir -p /home/bin
    if curl -fsSL "https://github.com/benbjohnson/litestream/releases/download/${LS_VERSION}/litestream-${LS_VERSION}-linux-amd64.tar.gz" -o /tmp/litestream.tgz; then
      if ! echo "${LS_SHA256}  /tmp/litestream.tgz" | sha256sum -c -; then
        echo "startup: litestream checksum mismatch; refusing that binary"
        rm -f /tmp/litestream.tgz
      else
        tar -xzf /tmp/litestream.tgz -C /home/bin litestream || echo "startup: litestream extract failed"
      fi
    else
      echo "startup: litestream download failed"
    fi
  fi
fi

if [ "${APP_ENV}" = "prod" ]; then
  if [ -z "${PRECIOUS}" ]; then
    echo "startup: SITE_PRECIOUS_DB_PATH or BETA_PRECIOUS_DB_PATH is required when APP_ENV=prod"
    exit 1
  fi
  case "${PRECIOUS}" in
    /home/*)
      echo "startup: serving db on /home (${PRECIOUS}); refusing prod boot (SQLite WAL cannot use the Azure Files share)"
      exit 1
      ;;
  esac
  if [ -z "${LITESTREAM_AZURE_ACCOUNT_NAME:-}" ] || [ -z "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] \
     || [ -z "${LITESTREAM_AZURE_CONTAINER:-}" ] || [ -z "${LITESTREAM_AZURE_SITE_PATH:-}" ]; then
    echo "startup: LITESTREAM_AZURE_ACCOUNT_NAME, ACCOUNT_KEY, CONTAINER, and SITE_PATH (or BETA_PATH alias) are required when APP_ENV=prod"
    exit 1
  fi
  if [ ! -x "${LS_BIN}" ] || [ ! -f "${ROOT}/litestream.yml" ]; then
    echo "startup: Litestream is required when APP_ENV=prod; refusing boot"
    exit 1
  fi
fi

if [ -x "${LS_BIN}" ] && [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${ROOT}/litestream.yml" ]; then
  if [ -z "${PRECIOUS}" ]; then
    echo "startup: serving db path unset; refusing litestream restore"
    if [ "${APP_ENV}" = "prod" ]; then
      exit 1
    fi
  else
    mkdir -p "$(dirname "${PRECIOUS}")" 2>/dev/null || true
    FAIL_MARKER="$(dirname "${PRECIOUS}")/.litestream-restore-failed"
    rm -f "${FAIL_MARKER}" 2>/dev/null || true
    # Restore only when there's no local DB AND a replica exists (never clobber a
    # live local DB). One serving file only — leftover /test PRECIOUS_DB_PATH is
    # not restored.
    "${LS_BIN}" restore -config "${ROOT}/litestream.yml" -if-replica-exists -if-db-not-exists "${PRECIOUS}" \
      || echo "startup: litestream restore skipped/failed"
    if [ ! -s "${PRECIOUS}" ]; then
      echo "startup: serving db missing or empty after restore"
      if [ "${APP_ENV}" = "prod" ]; then
        mkdir -p "$(dirname "${FAIL_MARKER}")" 2>/dev/null || true
        touch "${FAIL_MARKER}" 2>/dev/null || true
        echo "startup: refusing prod boot with empty durable state"
        exit 1
      fi
    elif [ "${APP_ENV}" = "prod" ]; then
      if ! "${PYTHON}" -m web.data.precious_integrity before "${PRECIOUS}"; then
        echo "startup: serving db failed integrity check after restore"
        mkdir -p "$(dirname "${FAIL_MARKER}")" 2>/dev/null || true
        touch "${FAIL_MARKER}" 2>/dev/null || true
        echo "startup: refusing prod boot with empty durable state"
        exit 1
      fi
    fi
  fi
  echo "startup: launching gunicorn + worker under litestream replicate"
  exec "${LS_BIN}" replicate -config "${ROOT}/litestream.yml" -exec "${SUPERVISE_CMD}"
fi

# 3. Fallback: no Litestream. Dev only.
if [ "${APP_ENV}" = "prod" ]; then
  echo "startup: litestream not active; refusing prod boot"
  exit 1
fi
echo "startup: litestream not active; launching gunicorn + worker directly"
exec ${SUPERVISE_CMD}
