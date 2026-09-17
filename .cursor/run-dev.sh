#!/usr/bin/env bash
# Run the parked FastAPI home locally with preview login.
# No Graph / Reporting API key required; catalog mock + Achim User Login.
set -u

cd "$(dirname "$0")/.."   # repo root
# shellcheck disable=SC1091
. .venv/bin/activate

export APP_ENV="${APP_ENV:-preview}"
export SESSION_SECRET="${SESSION_SECRET:-$(python -c 'import secrets; print(secrets.token_hex(24))')}"
export FLASK_SECRET="${FLASK_SECRET:-$SESSION_SECRET}"
export PORT="${PORT:-8080}"

cd app
export PYTHONPATH=.
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT}"
