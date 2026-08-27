#!/usr/bin/env bash
# Fail if session-cookie export files are tracked. Prints paths only, never file contents.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
tracked="$(git ls-files -- '.scratch/parity-cookies.env' '.scratch/**/*cookie*' '*parity-cookies.env' || true)"
if [ -n "$tracked" ]; then
  echo "Tracked session export files are forbidden:"
  printf '%s\n' "$tracked"
  exit 1
fi
echo "No tracked session export files."
