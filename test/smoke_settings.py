"""End-to-end smoke test for the unified Users & Permissions admin.

Run from the repo root:

    python -m test.smoke_settings

Boots the Flask app in dev mode (disabled scheduler), seeds an admin in
the session, and exercises every endpoint that backs the merged
Users/Salesman-map admin section.

Design contract being verified:
  * Adding a salesman creates the salesman row AND a linked app_users
    row (role=salesman, salesman_key=<key>).
  * Salesmen without an email are rejected.
  * Renaming a salesman's email cascades to the linked user.
  * Deleting a user with role=salesman drops the linked salesman row.
  * Deleting a salesman drops the linked user.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Always run with the scheduler off and an isolated DB so we don't
# clobber a real test/app.db on the dev box.
os.environ.setdefault("V2_DISABLE_SCHEDULER", "1")
os.environ.setdefault("V2_AUTH_MODE", "dev")
os.environ.setdefault("V2_FLASK_SECRET", "smoke-only-do-not-use")
# Make the app boot at the root path so test_client URLs are simple.
os.environ.setdefault("V2_URL_PREFIX", "")

_TMP = Path(tempfile.mkdtemp(prefix="v2-smoke-"))
os.environ["V2_APP_DB"] = str(_TMP / "smoke.db")
os.environ["V2_ADMIN_EMAILS"] = "smoke-admin@achimonline.com"

# Pythonpath shim so `import test.*` works when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from test.webapp.app import create_app  # noqa: E402

ADMIN_EMAIL = "smoke-admin@achimonline.com"

OK   = "[OK]"
FAIL = "[FAIL]"
INFO = "[..]"


def _print(tag: str, msg: str) -> None:
    print(f"{tag} {msg}")


def _login(client, email: str = ADMIN_EMAIL) -> None:
    """Use the dev-bypass sign-in to seat an admin session."""
    r = client.post("/login/dev", data={"email": email, "name": "Smoke Admin"})
    assert r.status_code in (200, 302), f"dev login failed: {r.status_code} {r.data!r}"


def _expect_ok(label: str, resp) -> dict:
    if resp.status_code != 200:
        _print(FAIL, f"{label}: HTTP {resp.status_code} {resp.data[:200]!r}")
        sys.exit(1)
    try:
        body = resp.get_json()
    except Exception:
        body = None
    if not body or body.get("error"):
        _print(FAIL, f"{label}: error in body: {body!r}")
        sys.exit(1)
    _print(OK, f"{label}: ok")
    return body


def _expect_status(label: str, resp, expected: int) -> dict:
    if resp.status_code != expected:
        _print(FAIL, f"{label}: HTTP {resp.status_code} (expected {expected}) {resp.data[:200]!r}")
        sys.exit(1)
    _print(OK, f"{label}: {expected} as expected")
    try:
        return resp.get_json() or {}
    except Exception:
        return {}


def main() -> None:
    _print(INFO, f"using temp DB: {os.environ['V2_APP_DB']}")
    app = create_app()
    app.testing = True
    client = app.test_client()

    _login(client)

    # Settings page renders. Salesman map should NOT be a separate
    # section anymore -- it lives inside Users & Permissions.
    r = client.get("/settings")
    assert r.status_code == 200, f"GET /settings -> {r.status_code}"
    body = r.get_data(as_text=True)
    for needle in ("Users &amp; permissions", "Per-report access", "Add master schedule"):
        if needle not in body:
            _print(FAIL, f"settings.html missing: {needle}")
            sys.exit(1)
    if "Salesman map" in body:
        _print(FAIL, "settings.html still has the standalone 'Salesman map' section")
        sys.exit(1)
    if "Manage master schedules" in body:
        _print(FAIL, "settings.html still links out to the master schedules page")
        sys.exit(1)
    _print(OK, "settings page renders with inline master schedules")

    # /api/settings/admin/users returns the perm grid + report meta + salesmen.
    body = _expect_ok("GET admin/users", client.get("/api/settings/admin/users"))
    for k in ("perm_grid", "report_meta", "salesmen"):
        if k not in body:
            _print(FAIL, f"GET admin/users missing key: {k}")
            sys.exit(1)
    _print(INFO, f"perm_grid has {len(body['perm_grid'])} user(s) at start")

    # ----- Salesman without email is rejected -----
    r = client.post(
        "/api/settings/admin/salesmen",
        data=json.dumps({
            "key": "noemail", "number": "001",
            "full_name": "No Email Person",
        }),
        content_type="application/json",
    )
    _expect_status("POST admin/salesmen (no email)", r, 400)

    # ----- Add a real salesman -- this should also create the user -----
    body = _expect_ok(
        "POST admin/salesmen (add)",
        client.post(
            "/api/settings/admin/salesmen",
            data=json.dumps({
                "key": "smoketest",
                "number": "999",
                "full_name": "Smoke Test Salesman",
                "display_name": "SmokeTest",
                "email": "smoketest@achimonline.com",
                "commission_pct": 7.5,
                "active": True,
            }),
            content_type="application/json",
        ),
    )
    sm_keys = [s["key"] for s in body.get("salesmen", [])]
    assert "smoketest" in sm_keys, sm_keys
    # Linked user must exist.
    user_emails = {u["email"] for u in body["perm_grid"]}
    assert "smoketest@achimonline.com" in user_emails, (
        "salesman add did not create a user; perm_grid emails: " + repr(user_emails)
    )
    sm_user = next(u for u in body["perm_grid"]
                   if u["email"] == "smoketest@achimonline.com")
    assert sm_user["role"] == "salesman", sm_user
    assert sm_user["salesman_key"] == "smoketest", sm_user
    assert sm_user["sm_number"] == "999", sm_user
    assert abs((sm_user.get("commission_pct") or 0) - 7.5) < 0.01, sm_user
    _print(OK, "salesman add created the linked user")

    # ----- Update salesman email -- must rename the user too -----
    body = _expect_ok(
        "POST admin/salesmen (rename email)",
        client.post(
            "/api/settings/admin/salesmen",
            data=json.dumps({
                "key": "smoketest",
                "number": "999",
                "full_name": "Smoke Test Salesman (renamed)",
                "display_name": "SmokeTest",
                "email": "smoketest2@achimonline.com",
                "commission_pct": 9.99,
                "active": True,
            }),
            content_type="application/json",
        ),
    )
    user_emails = {u["email"] for u in body["perm_grid"]}
    assert "smoketest@achimonline.com" not in user_emails, (
        "old email still present: " + repr(user_emails)
    )
    assert "smoketest2@achimonline.com" in user_emails, (
        "renamed email missing: " + repr(user_emails)
    )
    _print(OK, "salesman email rename cascaded to the user row")

    # ----- Add a NON-salesman user (admin) via /users/add -----
    body = _expect_ok(
        "POST admin/users/add (manager)",
        client.post(
            "/api/settings/admin/users/add",
            data=json.dumps({
                "email": "manager@achimonline.com",
                "role": "manager",
                "display_name": "Manager Person",
                "is_external": False,
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "manager@achimonline.com")
    assert perm["role"] == "manager", perm

    # ----- /users/add with role=salesman is rejected (use /salesmen) -----
    r = client.post(
        "/api/settings/admin/users/add",
        data=json.dumps({
            "email": "another@achimonline.com",
            "role": "salesman",
        }),
        content_type="application/json",
    )
    _expect_status("POST admin/users/add (role=salesman, no key)", r, 400)

    # ----- Adding the same email twice -> 409 -----
    r = client.post(
        "/api/settings/admin/users/add",
        data=json.dumps({
            "email": "manager@achimonline.com",
            "role": "manager",
        }),
        content_type="application/json",
    )
    _expect_status("POST admin/users/add (duplicate)", r, 409)

    # ----- Manager assignment -----
    body = _expect_ok(
        "POST admin/users/salesman-access",
        client.post(
            "/api/settings/admin/users/salesman-access",
            data=json.dumps({
                "email": "manager@achimonline.com",
                "keys": ["smoketest"],
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "manager@achimonline.com")
    assert "smoketest" in perm["allowed_salesmen"], perm

    # ----- Per-report deny override + clear -----
    body = _expect_ok(
        "POST admin/users/report-access (deny)",
        client.post(
            "/api/settings/admin/users/report-access",
            data=json.dumps({
                "email": "manager@achimonline.com",
                "report_key": "ordered",
                "allowed": False,
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "manager@achimonline.com")
    assert perm["reports"].get("ordered") is False, perm["reports"]

    body = _expect_ok(
        "POST admin/users/report-access (clear)",
        client.post(
            "/api/settings/admin/users/report-access",
            data=json.dumps({
                "email": "manager@achimonline.com",
                "report_key": "ordered",
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "manager@achimonline.com")
    assert perm["reports"].get("ordered") is True, perm["reports"]

    # ----- Self-demotion blocked -----
    r = client.post(
        "/api/settings/admin/users",
        data=json.dumps({"email": ADMIN_EMAIL, "role": "salesman"}),
        content_type="application/json",
    )
    _expect_status("POST admin/users (self-demotion)", r, 400)

    # ----- Run log -----
    from test.webapp.db import log_report_run
    log_report_run(
        user_email=ADMIN_EMAIL, report_key="ordered", report_name="Ordered Report",
        params={"period": "this_month"}, rows_returned=42, duration_ms=1234,
        status="success",
    )
    body = _expect_ok(
        "GET admin/report-log",
        client.get("/api/settings/admin/report-log"),
    )
    assert body["rows"], "report-log returned no rows after insert"

    # ----- Non-admin -> 403 -----
    with client.session_transaction() as s:
        u = s.get("v2_user") or {}
        u["is_admin"] = False
        u["email"] = "outsider@achimonline.com"
        u["name"] = "Outsider"
        s["v2_user"] = u
    r = client.get("/api/settings/admin/users",
                   headers={"Accept": "application/json"})
    _expect_status("GET admin/users (non-admin)", r, 403)
    _login(client)

    # ----- Delete the user via /users/delete -- since they're a       -----
    # salesman, the linked salesman row must also be gone.
    body = _expect_ok(
        "POST admin/users/delete (salesman cascade)",
        client.post(
            "/api/settings/admin/users/delete",
            data=json.dumps({"email": "smoketest2@achimonline.com"}),
            content_type="application/json",
        ),
    )
    sm_keys = [s["key"] for s in body["salesmen"]]
    assert "smoketest" not in sm_keys, (
        "salesman row was not cascaded on user delete: " + repr(sm_keys)
    )
    user_emails = {u["email"] for u in body["perm_grid"]}
    assert "smoketest2@achimonline.com" not in user_emails

    # ----- Delete the manager user -----
    body = _expect_ok(
        "POST admin/users/delete (manager)",
        client.post(
            "/api/settings/admin/users/delete",
            data=json.dumps({"email": "manager@achimonline.com"}),
            content_type="application/json",
        ),
    )
    user_emails = {u["email"] for u in body["perm_grid"]}
    assert "manager@achimonline.com" not in user_emails

    # ----- Salesman delete also drops the user (re-add then delete via /salesmen) -----
    _expect_ok(
        "POST admin/salesmen (re-add for delete test)",
        client.post(
            "/api/settings/admin/salesmen",
            data=json.dumps({
                "key": "smoke3",
                "full_name": "Smoke Three",
                "email": "smoke3@achimonline.com",
            }),
            content_type="application/json",
        ),
    )
    body = _expect_ok(
        "POST admin/salesmen/delete",
        client.post(
            "/api/settings/admin/salesmen/delete",
            data=json.dumps({"key": "smoke3"}),
            content_type="application/json",
        ),
    )
    sm_keys = [s["key"] for s in body["salesmen"]]
    assert "smoke3" not in sm_keys
    user_emails = {u["email"] for u in body["perm_grid"]}
    assert "smoke3@achimonline.com" not in user_emails, (
        "user row not cascaded on salesman delete: " + repr(user_emails)
    )

    print()
    _print(OK, "All settings smoke-tests passed.")


if __name__ == "__main__":
    main()
