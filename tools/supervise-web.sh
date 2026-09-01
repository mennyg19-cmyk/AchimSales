#!/usr/bin/env bash
# Start Gunicorn and the job worker as siblings. If either exits, stop the
# other so Azure restarts the whole unit. Litestream is the outer process.
#
# Env:
#   STARTUP_ROOT / ROOT   repo root (default: this script's parent)
#   GUNICORN_CMD          required: full gunicorn command
#   WORKER_CMD            default: python -m web.worker_main
#   BOOTSTRAP_CMD         default: python -m web.bootstrap
#   PYTHON                default: python
set -u

ROOT="${STARTUP_ROOT:-${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}}"
cd "$ROOT"
export PYTHONPATH="${ROOT}/v3:${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

PYTHON="${PYTHON:-python}"
BOOTSTRAP_CMD="${BOOTSTRAP_CMD:-${PYTHON} -m web.bootstrap}"
WORKER_CMD="${WORKER_CMD:-${PYTHON} -m web.worker_main}"
GUNICORN_CMD="${GUNICORN_CMD:?supervise-web: GUNICORN_CMD is required}"

echo "supervise: bootstrap"
# shellcheck disable=SC2086
if ! ${BOOTSTRAP_CMD}; then
  echo "supervise: bootstrap failed"
  exit 1
fi

GUNI_PID=""
WORK_PID=""

term_children() {
  if [ -n "${GUNI_PID}" ]; then kill "${GUNI_PID}" 2>/dev/null || true; fi
  if [ -n "${WORK_PID}" ]; then kill "${WORK_PID}" 2>/dev/null || true; fi
}

trap 'echo "supervise: signal; stopping children"; term_children; wait; exit 143' INT TERM

# shellcheck disable=SC2086
${GUNICORN_CMD} &
GUNI_PID=$!
# shellcheck disable=SC2086
${WORKER_CMD} &
WORK_PID=$!
echo "supervise: gunicorn pid=${GUNI_PID} worker pid=${WORK_PID}"

while kill -0 "${GUNI_PID}" 2>/dev/null && kill -0 "${WORK_PID}" 2>/dev/null; do
  sleep 1
done

EXIT=1
if kill -0 "${GUNI_PID}" 2>/dev/null; then
  wait "${WORK_PID}"
  EXIT=$?
else
  wait "${GUNI_PID}"
  EXIT=$?
fi

echo "supervise: a child exited (${EXIT}); stopping the other"
term_children
wait 2>/dev/null || true
exit "${EXIT}"
