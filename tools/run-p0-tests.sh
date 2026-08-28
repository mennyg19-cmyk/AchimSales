#!/usr/bin/env bash
# P0 / single-site tests used by CI and the Azure production build job.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/v3"
python -m pytest \
  tests/test_odata_scope.py \
  tests/test_config.py \
  tests/test_smoke.py \
  tests/test_precious_repair.py \
  tests/test_session_authz.py \
  tests/test_seed_users_grants.py \
  tests/test_auth.py \
  tests/test_magic_link.py \
  tests/test_public_origin.py \
  tests/test_report_sources.py \
  tests/test_security_headers.py \
  tests/test_frontend.py \
  tests/test_blueprints.py::test_devtools_forbidden_for_admin_and_ok_for_developer \
  -q --tb=short
cd "$ROOT"
PYTHONPATH="$ROOT" python -m pytest \
  tests/test_excel_formula.py \
  tests/test_wsgi_dispatch.py \
  --noconftest -q --tb=short
