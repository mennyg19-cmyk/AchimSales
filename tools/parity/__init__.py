"""Live vs /test report parity runner.

Runs the same params on live (/) and /test, downloads Excel from each, and
writes a key-matched data diff (not cell-position) for manual review.

Auth (option #2 — no browser):
  PARITY_AUTH=cookie   (default for prod)
    PARITY_LIVE_COOKIE   session cookie value, or full Cookie header fragment
    PARITY_TEST_COOKIE   v3_session cookie value
  PARITY_AUTH=dev      (local only; needs DEV_BYPASS_AUTH / auth_mode=dev)
    signs in as admin/developer via /dev-login and /test/login/dev

Usage:
  python -m tools.parity
  python -m tools.parity --report ordered --param period=last_month
  python -m tools.parity --base-url https://reports.achimonline.com
"""

from __future__ import annotations
