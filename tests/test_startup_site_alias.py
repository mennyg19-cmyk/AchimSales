"""Whitespace-only SITE_* must not override PRECIOUS_/CACHE_ (startup vs Flask)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTUP = ROOT / "startup.sh"


def _export_trimmed_alias_source() -> str:
    text = STARTUP.read_text(encoding="utf-8")
    start = text.index("_export_trimmed_alias()")
    end = text.index("\n}", start) + 2
    return text[start:end]


def _alias_precious(site_value: str | None, fallback: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PRECIOUS_DB_PATH": fallback,
    }
    if site_value is not None:
        env["SITE_PRECIOUS_DB_PATH"] = site_value
    script = _export_trimmed_alias_source() + """
set -u
_export_trimmed_alias "${SITE_PRECIOUS_DB_PATH:-}" PRECIOUS_DB_PATH
printf '%s\\n' "$PRECIOUS_DB_PATH"
"""
    completed = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_whitespace_only_site_precious_keeps_fallback():
    assert _alias_precious("   ", "/tmp/fallback-precious.db") == "/tmp/fallback-precious.db"


def test_padded_site_precious_exports_trimmed_path():
    assert _alias_precious(" /tmp/site-precious.db ", "/tmp/fallback-precious.db") == (
        "/tmp/site-precious.db"
    )
