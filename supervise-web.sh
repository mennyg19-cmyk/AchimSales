#!/usr/bin/env bash
# Run the HTTP server and durable v3 worker as one App Service unit.
set -u

ROOT="${ROOT:-/home/site/wwwroot}"
WORKERS="${WEB_CONCURRENCY:-2}"
THREADS="${GUNICORN_THREADS:-8}"
TIMEOUT="${GUNICORN_TIMEOUT:-230}"
PORT="${PORT:-8000}"

cd "${ROOT}"
gunicorn --config="${ROOT}/gunicorn.conf.py" --bind="0.0.0.0:${PORT}" \
  --workers="${WORKERS}" --worker-class=gthread --threads="${THREADS}" \
  --timeout="${TIMEOUT}" --access-logfile=- --error-logfile=- wsgi:application &
web_pid=$!
PYTHONPATH="${ROOT}/v3${PYTHONPATH:+:${PYTHONPATH}}" python3 -m web.jobs.worker_main &
worker_pid=$!

stop_children() {
  kill -TERM "${web_pid}" "${worker_pid}" 2>/dev/null || true
  wait "${web_pid}" 2>/dev/null || true
  wait "${worker_pid}" 2>/dev/null || true
}

shutdown() {
  stop_children
  exit 0
}

trap shutdown SIGTERM SIGINT
wait -n "${web_pid}" "${worker_pid}"
stop_children
exit 1
