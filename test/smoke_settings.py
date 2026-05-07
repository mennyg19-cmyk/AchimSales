"""End-to-end smoke test for the new settings admin endpoints.

Run from the repo root:

    python -m test.smoke_settings

Boots the Flask app in dev mode (disabled scheduler), seeds an admin in
the session, and exercises every new endpoint we just added.
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


def main() -> None:
    _print(INFO, f"using temp DB: {os.environ['V2_APP_DB']}")
    app = create_app()
    app.testing = True
    client = app.test_client()

    _login(client)

    # Settings page renders with the new sections.
    r = client.get("/settings")
    assert r.status_code == 200, f"GET /settings -> {r.status_code}"
    body = r.get_data(as_text=True)
    for needle in ("Salesman map", "Users &amp; permissions", "Per-report access"):
        if needle not in body:
            _print(FAIL, f"settings.html missing: {needle}")
            sys.exit(1)
    _print(OK, "settings page renders with new sections")

    # /api/settings/admin/users returns the perm grid + report metadata.
    body = _expect_ok("GET admin/users", client.get("/api/settings/admin/users"))
    assert "perm_grid" in body and "report_meta" in body, body
    _print(INFO, f"perm_grid has {len(body['perm_grid'])} user(s)")

    # Add a salesman.
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
                "subscriptions": {"ordered": True, "invoiced": False},
            }),
            content_type="application/json",
        ),
    )
    sm_keys = [s["key"] for s in body.get("salesmen", [])]
    assert "smoketest" in sm_keys, sm_keys

    # Update the salesman.
    body = _expect_ok(
        "POST admin/salesmen (update)",
        client.post(
            "/api/settings/admin/salesmen",
            data=json.dumps({
                "key": "smoketest",
                "number": "999",
                "full_name": "Smoke Test Salesman (updated)",
                "email": "smoketest@achimonline.com",
                "commission_pct": 9.99,
                "active": True,
            }),
            content_type="application/json",
        ),
    )
    sm = next(s for s in body["salesmen"] if s["key"] == "smoketest")
    assert sm["full_name"].endswith("(updated)"), sm

    # Add a salesman user (role=salesman, salesman_key=smoketest).
    body = _expect_ok(
        "POST admin/users/add",
        client.post(
            "/api/settings/admin/users/add",
            data=json.dumps({
                "email": "salesperson@achimonline.com",
                "role": "salesman",
                "salesman_key": "smoketest",
                "display_name": "Sales Person",
                "is_external": False,
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "salesperson@achimonline.com")
    assert perm["role"] == "salesman", perm
    assert perm["salesman_key"] == "smoketest", perm
    assert perm["sm_name"] is not None, perm

    # Adding the same email again should 409.
    r = client.post(
        "/api/settings/admin/users/add",
        data=json.dumps({
            "email": "salesperson@achimonline.com",
            "role": "salesman",
            "salesman_key": "smoketest",
        }),
        content_type="application/json",
    )
    assert r.status_code == 409, f"expected 409, got {r.status_code}"
    _print(OK, "POST admin/users/add (duplicate): 409 as expected")

    # Promote them to manager + assign a salesman.
    body = _expect_ok(
        "POST admin/users (role=manager)",
        client.post(
            "/api/settings/admin/users",
            data=json.dumps({
                "email": "salesperson@achimonline.com",
                "role": "manager",
                "salesman_key": None,
                "active": True,
            }),
            content_type="application/json",
        ),
    )
    body = _expect_ok(
        "POST admin/users/salesman-access",
        client.post(
            "/api/settings/admin/users/salesman-access",
            data=json.dumps({
                "email": "salesperson@achimonline.com",
                "keys": ["smoketest"],
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "salesperson@achimonline.com")
    assert "smoketest" in perm["allowed_salesmen"], perm

    # Add a per-report deny override.
    body = _expect_ok(
        "POST admin/users/report-access (deny)",
        client.post(
            "/api/settings/admin/users/report-access",
            data=json.dumps({
                "email": "salesperson@achimonline.com",
                "report_key": "ordered",
                "allowed": False,
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "salesperson@achimonline.com")
    assert perm["reports"].get("ordered") is False, perm["reports"]

    # Clear the override.
    body = _expect_ok(
        "POST admin/users/report-access (clear)",
        client.post(
            "/api/settings/admin/users/report-access",
            data=json.dumps({
                "email": "salesperson@achimonline.com",
                "report_key": "ordered",
            }),
            content_type="application/json",
        ),
    )
    perm = next(u for u in body["perm_grid"]
                if u["email"] == "salesperson@achimonline.com")
    assert perm["reports"].get("ordered") is True, perm["reports"]

    # Validation: salesman role without a key is rejected.
    r = client.post(
        "/api/settings/admin/users",
        data=json.dumps({
            "email": "salesperson@achimonline.com",
            "role": "salesman",
            "salesman_key": None,
        }),
        content_type="application/json",
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.data!r}"
    _print(OK, "POST admin/users (salesman without key): 400 as expected")

    # Self-demotion is blocked.
    r = client.post(
        "/api/settings/admin/users",
        data=json.dumps({"email": ADMIN_EMAIL, "role": "salesman"}),
        content_type="application/json",
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.data!r}"
    _print(OK, "self-demotion: 400 as expected")

    # Run-log endpoint returns rows after a fake insert.
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
    _print(INFO, f"run-log has {len(body['rows'])} entry/entries")

    # Non-admin gets 403.
    with client.session_transaction() as s:
        u = s.get("v2_user") or {}
        u["is_admin"] = False
        u["email"] = "outsider@achimonline.com"
        u["name"] = "Outsider"
        s["v2_user"] = u
    r = client.get("/api/settings/admin/users",
                   headers={"Accept": "application/json"})
    assert r.status_code == 403, f"expected 403, got {r.status_code}"
    _print(OK, "non-admin: 403 as expected")

    # Delete the salesman + the user we created.
    _login(client)
    body = _expect_ok(
        "POST admin/users/delete",
        client.post(
            "/api/settings/admin/users/delete",
            data=json.dumps({"email": "salesperson@achimonline.com"}),
            content_type="application/json",
        ),
    )
    body = _expect_ok(
        "POST admin/salesmen/delete",
        client.post(
            "/api/settings/admin/salesmen/delete",
            data=json.dumps({"key": "smoketest"}),
            content_type="application/json",
        ),
    )
    assert all(s["key"] != "smoketest" for s in body["salesmen"])

    print()
    _print(OK, "All settings smoke-tests passed.")


if __name__ == "__main__":
    main()
