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
#   3. Launch the HTTP-only Gunicorn process and its sibling v3 worker under a
#      small supervisor. The worker owns v3 migrations, seeds, scheduling, and jobs.
#
# CRITICAL: this process also serves the site home (Beta) at "/" via the
# dispatcher, so every Litestream step is FAIL-OPEN. If the binary can't be
# fetched, the config is wrong, or a restore fails, we log it and fall back to
# launching gunicorn directly. Litestream must never cause an outage.
#
# NOTE: no `set -e` on purpose -- a non-zero from a best-effort step must not
# abort the boot.
set -u

ROOT="/home/site/wwwroot"
LS_BIN="/home/bin/litestream"
LS_VERSION="${LITESTREAM_VERSION:-v0.3.13}"

SUPERVISOR_CMD="${ROOT}/supervise-web.sh"

# 1. Defensive dependency install (Oryx usually already did this on deploy).
pip install -q -r "${ROOT}/requirements.txt" || echo "startup: pip install warning (continuing)"

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
  mkdir -p "$(dirname "${PRECIOUS}")" 2>/dev/null || true
  # Restore only when there's no local DB AND a replica exists (never clobber a
  # live local DB). On the persistent /home path this is normally a no-op; after
  # the one-time seed above the local DB already exists, so this also no-ops.
  "${LS_BIN}" restore -config "${ROOT}/litestream.yml" -if-replica-exists -if-db-not-exists "${PRECIOUS}" \
    || echo "startup: litestream restore skipped/failed (continuing)"
  BETA_PRECIOUS="${BETA_PRECIOUS_DB_PATH:-}"
  if [ -n "${BETA_PRECIOUS}" ]; then
    case "${BETA_PRECIOUS}" in
      /home/*) echo "startup: beta precious.db on /home (${BETA_PRECIOUS}); skip restore" ;;
      *)
        mkdir -p "$(dirname "${BETA_PRECIOUS}")" 2>/dev/null || true
        "${LS_BIN}" restore -config "${ROOT}/litestream.yml" -if-replica-exists -if-db-not-exists "${BETA_PRECIOUS}" \
          || echo "startup: beta litestream restore skipped/failed (continuing)"
        ;;
    esac
  fi
  echo "startup: launching web supervisor under litestream replicate"
  exec "${LS_BIN}" replicate -config "${ROOT}/litestream.yml" -exec "${SUPERVISOR_CMD}"
fi

# 3. Fallback: no Litestream -> launch the supervised web unit directly.
echo "startup: litestream not active; launching web supervisor directly"
exec "${SUPERVISOR_CMD}"
