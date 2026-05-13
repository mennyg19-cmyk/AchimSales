#!/usr/bin/env bash
# Azure App Service (Python on Oryx) reads this file as the startup
# command when the "Startup Command" config field is left blank.
#
# We need gthread workers (NOT the Oryx default sync workers) so a
# single in-flight request -- e.g. the dashboard's 25-second SQL
# build, or a long-running refresh-status poll -- doesn't tie up the
# whole worker and force every other tab into the "this page isn't
# working" timeout. WAL-mode SQLite plus the per-request connection
# cache in test/webapp/db.py makes multi-threaded reads safe.
#
# Two sync workers x eight threads each = 16 concurrent requests,
# which is plenty for the user base.

set -e

WORKERS="${WEB_CONCURRENCY:-2}"
THREADS="${GUNICORN_THREADS:-8}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"
PORT="${PORT:-8000}"

exec gunicorn \
    --bind=0.0.0.0:"${PORT}" \
    --workers="${WORKERS}" \
    --worker-class=gthread \
    --threads="${THREADS}" \
    --timeout="${TIMEOUT}" \
    --access-logfile=- \
    --error-logfile=- \
    wsgi:application
