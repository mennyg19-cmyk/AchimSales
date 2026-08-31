#!/usr/bin/env bash
# Azure App Service (Python on Oryx) startup command.
#
# Set the App Service "Startup Command" to:  bash /home/site/wwwroot/startup.sh
#
# Responsibilities, in order:
#   1. (Defensive) pip install the deployed requirements.
#   2. Litestream restore + replicate (required when APP_ENV=prod).
#   3. Launch tools/supervise-web.sh under Litestream: bootstrap, then Gunicorn
#      (HTTP) and python -m web.worker_main (jobs + scheduler) as siblings.
#      If either process exits, the supervisor stops the other so the platform
#      restarts the unit. One App Service instance while SQLite is used.
#
# CRITICAL: in APP_ENV=prod this process must not serve an empty precious.db.
# Restore failure or missing Litestream settings abort boot. Local APP_ENV=dev
# still falls back to gunicorn without Litestream.
#
# NOTE: no `set -e` on purpose -- a non-zero from a best-effort seed step must
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
APP_ENV="${APP_ENV:-prod}"
LS_BIN="${LITESTREAM_BIN:-/home/bin/litestream}"
LS_VERSION="${LITESTREAM_VERSION:-v0.3.13}"
# sha256 of litestream-v0.3.13-linux-amd64.tar.gz (GitHub release asset).
LS_SHA256="${LITESTREAM_SHA256:-eb75a3de5cab03875cdae9f5f539e6aedadd66607003d9b1e7a9077948818ba0}"

GUNICORN_CMD="gunicorn --config=${ROOT}/gunicorn.conf.py --bind=0.0.0.0:${PORT} --workers=${WORKERS} --worker-class=gthread --threads=${THREADS} --timeout=${TIMEOUT} --access-logfile=- --error-logfile=- wsgi:application"
export GUNICORN_CMD
export STARTUP_ROOT="${ROOT}"
export PYTHONPATH="${ROOT}/v3:${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
SUPERVISE_CMD="bash ${ROOT}/tools/supervise-web.sh"

# 1. Defensive dependency install (Oryx usually already did this on deploy).
if [ -z "${STARTUP_SKIP_PIP:-}" ]; then
  pip install -q -r "${ROOT}/requirements.txt" || echo "startup: pip install warning (continuing)"
fi

# 1b. One-time move off the /home SMB share onto local disk (rule 5).
#     SQLite's WAL mode can't share its index across processes on an SMB share,
#     so the background worker couldn't see jobs the web workers enqueued -- runs
#     queued forever and never called the Reporting API. The DB now lives on local
#     disk (PRECIOUS_DB_PATH points off /home). On the FIRST boot after the move,
#     seed the local DB once from the old /home copy using SQLite's online backup
#     (a consistent snapshot even if /home has a pending WAL). A marker on the
#     persistent share makes this run exactly once, so later cold starts restore
#     the CURRENT data from the Litestream replica instead of overwriting it with
#     the now-frozen /home file. Only precious.db is seeded; cache.db is disposable.
HOME_SEED_DB="/home/site/v3data/precious.db"
SEED_MARKER="/home/site/v3data/.migrated-to-local"
PRECIOUS="${PRECIOUS_DB_PATH:-/home/site/v3data/precious.db}"
case "${PRECIOUS}" in
  /home/*) echo "startup: precious.db still on /home (${PRECIOUS}); no local seed" ;;
  *)
    if [ ! -f "${PRECIOUS}" ] && [ ! -f "${SEED_MARKER}" ] && [ -f "${HOME_SEED_DB}" ]; then
      echo "startup: seeding local precious.db from ${HOME_SEED_DB}"
      mkdir -p "$(dirname "${PRECIOUS}")" 2>/dev/null || true
      # Dated safety copy of the source on the persistent share before anything.
      cp -f "${HOME_SEED_DB}" "/home/site/v3data/precious.premigrate.$(date +%Y%m%d%H%M%S).db" 2>/dev/null || true
      # Back up to a TEMP path and only publish it to the real path AFTER the
      # once-only marker is durably set. That ordering guarantees "real DB exists
      # => marker exists", so a wiped /tmp on a later cold start can never re-seed
      # from the now-stale /home file over a newer timeline. A boot killed
      # mid-backup leaves only the temp file, so the real path stays absent and
      # the Litestream restore below can take over.
      SEED_TMP="${PRECIOUS}.seed.tmp"
      rm -f "${SEED_TMP}" 2>/dev/null || true
      if python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); s.close(); d.close()" "${HOME_SEED_DB}" "${SEED_TMP}" \
         && touch "${SEED_MARKER}" && [ -f "${SEED_MARKER}" ]; then
        mv -f "${SEED_TMP}" "${PRECIOUS}"
        echo "startup: one-time local seed complete; marker set"
        python3 -c "import sqlite3; c=sqlite3.connect('${PRECIOUS}'); print('startup: seeded precious.db users=%d jobs=%d' % (c.execute('SELECT COUNT(*) FROM users').fetchone()[0], c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]))" 2>/dev/null || true
      else
        echo "startup: local seed incomplete; leaving real path empty so the replica restore can take over"
        rm -f "${SEED_TMP}" 2>/dev/null || true
      fi
    fi
    ;;
esac

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
  if [ ! -x "${LS_BIN}" ] || [ -z "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] || [ ! -f "${ROOT}/litestream.yml" ]; then
    echo "startup: Litestream is required when APP_ENV=prod; refusing boot"
    exit 1
  fi
fi

if [ -x "${LS_BIN}" ] && [ -n "${LITESTREAM_AZURE_ACCOUNT_KEY:-}" ] && [ -f "${ROOT}/litestream.yml" ]; then
  mkdir -p "$(dirname "${PRECIOUS}")" 2>/dev/null || true
  FAIL_MARKER="$(dirname "${PRECIOUS}")/.litestream-restore-failed"
  rm -f "${FAIL_MARKER}" 2>/dev/null || true
  # Restore only when there's no local DB AND a replica exists (never clobber a
  # live local DB). On the persistent /home path this is normally a no-op; after
  # the one-time seed above the local DB already exists, so this also no-ops.
  "${LS_BIN}" restore -config "${ROOT}/litestream.yml" -if-replica-exists -if-db-not-exists "${PRECIOUS}" \
    || echo "startup: litestream restore skipped/failed"
  if [ ! -f "${PRECIOUS}" ]; then
    echo "startup: precious.db missing after restore"
    if [ "${APP_ENV}" = "prod" ]; then
      mkdir -p "$(dirname "${FAIL_MARKER}")" 2>/dev/null || true
      touch "${FAIL_MARKER}" 2>/dev/null || true
      echo "startup: refusing prod boot with empty durable state"
      exit 1
    fi
  fi
  BETA_PRECIOUS="${BETA_PRECIOUS_DB_PATH:-}"
  if [ -n "${BETA_PRECIOUS}" ]; then
    case "${BETA_PRECIOUS}" in
      /home/*) echo "startup: beta precious.db on /home (${BETA_PRECIOUS}); skip restore" ;;
      *)
        mkdir -p "$(dirname "${BETA_PRECIOUS}")" 2>/dev/null || true
        "${LS_BIN}" restore -config "${ROOT}/litestream.yml" -if-replica-exists -if-db-not-exists "${BETA_PRECIOUS}" \
          || echo "startup: beta litestream restore skipped/failed"
        if [ "${APP_ENV}" = "prod" ] && [ ! -f "${BETA_PRECIOUS}" ]; then
          echo "startup: beta precious.db missing after restore; refusing boot"
          exit 1
        fi
        ;;
    esac
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
