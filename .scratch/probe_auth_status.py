"""Probe whether live/test session cookies are accepted."""
from __future__ import annotations

import os
import sys

import requests

BASE = os.environ.get("PARITY_BASE_URL", "https://reports.achimonline.com")
LIVE = os.environ.get("PARITY_LIVE_COOKIE", "")
TEST = os.environ.get("PARITY_TEST_COOKIE", "")
if not LIVE or not TEST:
    print("Missing PARITY_LIVE_COOKIE / PARITY_TEST_COOKIE")
    sys.exit(2)

r = requests.get(
    f"{BASE}/reports",
    headers={"Cookie": f"session={LIVE}"},
    allow_redirects=False,
    timeout=30,
)
print("LIVE /reports", r.status_code, (r.headers.get("Location") or "")[:100])
if r.status_code in (301, 302, 303, 307, 308) and "login" in (r.headers.get("Location") or "").lower():
    print("AUTH_FAIL live")
    sys.exit(1)

r3 = requests.get(
    f"{BASE}/test/",
    headers={"Cookie": f"v3_session={TEST}"},
    allow_redirects=False,
    timeout=30,
)
print("TEST /test/", r3.status_code, (r3.headers.get("Location") or "")[:120])
if r3.status_code in (301, 302, 303, 307, 308) and "login" in (r3.headers.get("Location") or "").lower():
    print("AUTH_FAIL test")
    sys.exit(1)

print("AUTH_OK")
sys.exit(0)
