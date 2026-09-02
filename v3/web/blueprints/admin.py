"""Admin: user/access + salesman management (privileged only).

Every route re-resolves privilege from the DB via Authorization (never the
session role) and fails closed. Mutations are JSON APIs consumed by admin.ts;
the page itself is server-rendered with the current state so it works without
JS too. Kept separate from settings.py so the thin per-user settings stay thin.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from report_engine import registry
from report_engine.lib import salesman_key
from web.auth.decorators import require_login
from web.auth.principal import ROLE_ADMIN, ROLE_DEVELOPER, ROLE_SALESMAN, VALID_ROLES
from web.auth.session import current_principal
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.users import UserRepository

admin_bp = Blueprint("admin", __name__)


def _db():
    return current_app.config["DB"]


def _guard():
    """None if OK; an (error, status) response tuple if not privileged."""
    if not current_app.config["AUTHZ"].is_privileged(current_principal()):
        return jsonify({"error": "Forbidden"}), 403
    return None


def _users() -> UserRepository:
    return UserRepository(_db())


def _salesmen() -> SalesmanRepository:
    return SalesmanRepository(_db())


def _user_dict(u) -> dict:
    return {
        "id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role,
        "is_active": u.is_active, "is_external": u.is_external,
        "dashboard_enabled": u.dashboard_enabled, "sharepoint_access": u.sharepoint_access,
        "test_access": u.test_access, "can_see_company_views": u.can_see_company_views,
        "sales_group": u.sales_group,
    }


def _sync_salesman_access_from_group(repo, user_id: int, sales_group: str) -> None:
    key = salesman_key(sales_group)
    repo.set_salesman_access(user_id, [key] if key else [])


# --- page -------------------------------------------------------------------

@admin_bp.get("/admin/users")
@require_login
def users_page():
    blocked = _guard()
    if blocked:
        return blocked
    users = _users().list_all()
    built = sorted(registry.built_reports(), key=lambda s: s.title)
    return render_template(
        "admin_users.html", active_tab="settings", users=users,
        roles=VALID_ROLES, reports=[{"key": s.key, "title": s.title} for s in built],
        salesmen=_salesmen().list_all(),
    )


# --- user CRUD --------------------------------------------------------------

@admin_bp.get("/api/admin/users")
@require_login
def list_users():
    blocked = _guard()
    if blocked:
        return blocked
    return jsonify({"users": [_user_dict(u) for u in _users().list_all()]})


@admin_bp.post("/api/admin/users")
@require_login
def create_user():
    blocked = _guard()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    role = (body.get("role") or "salesman").strip().lower()
    if "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": "Invalid role"}), 400
    repo = _users()
    u = repo.create(
        email, role=role, display_name=(body.get("display_name") or "").strip(),
        is_external=bool(body.get("is_external")),
        sales_group=str(body.get("sales_group") or "").strip(),
    )
    if role == ROLE_SALESMAN and u.sales_group:
        _sync_salesman_access_from_group(repo, u.id, u.sales_group)
    elif role not in (ROLE_ADMIN, ROLE_DEVELOPER) and not repo.get_salesman_access(u.id):
        matched = _salesmen().keys_for_email(email)
        if matched:
            repo.set_salesman_access(u.id, matched)
    return jsonify(_user_dict(repo.get_by_id(u.id) or u)), 201


@admin_bp.put("/api/admin/users/<int:user_id>")
@require_login
def update_user(user_id: int):
    blocked = _guard()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    role = body.get("role")
    if role is not None and role not in VALID_ROLES:
        return jsonify({"error": "Invalid role"}), 400
    repo = _users()
    target = repo.get_by_id(user_id)
    if target is None:
        return jsonify({"error": "Unknown user"}), 404
    sales_group = None
    if "sales_group" in body:
        sales_group = str(body.get("sales_group") or "").strip()
    repo.update(
        user_id, role=role,
        is_active=body.get("is_active"), is_external=body.get("is_external"),
        dashboard_enabled=body.get("dashboard_enabled"),
        sharepoint_access=body.get("sharepoint_access"), test_access=body.get("test_access"),
        can_see_company_views=body.get("can_see_company_views"),
        sales_group=sales_group,
    )
    new_role = role if role is not None else target.role
    if sales_group is not None and new_role == ROLE_SALESMAN:
        _sync_salesman_access_from_group(repo, user_id, sales_group)
    return jsonify(_user_dict(repo.get_by_id(user_id)))


@admin_bp.delete("/api/admin/users/<int:user_id>")
@require_login
def delete_user(user_id: int):
    blocked = _guard()
    if blocked:
        return blocked
    repo = _users()
    target = repo.get_by_id(user_id)
    if target is None:
        return jsonify({"error": "Unknown user"}), 404
    if target.email == current_principal().email:
        return jsonify({"error": "You cannot delete your own account"}), 400
    repo.delete(user_id)
    return jsonify({"deleted": user_id})


# --- per-user scope ---------------------------------------------------------

@admin_bp.get("/api/admin/users/<int:user_id>/salesman-access")
@require_login
def get_salesman_access(user_id: int):
    blocked = _guard()
    if blocked:
        return blocked
    return jsonify({"keys": sorted(_users().get_salesman_access(user_id))})


@admin_bp.post("/api/admin/users/<int:user_id>/salesman-access")
@require_login
def set_salesman_access(user_id: int):
    blocked = _guard()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    keys = body.get("keys") or []
    if not isinstance(keys, list):
        return jsonify({"error": "keys must be a list"}), 400
    _users().set_salesman_access(user_id, [str(k) for k in keys])
    return jsonify({"keys": sorted(_users().get_salesman_access(user_id))})


@admin_bp.get("/api/admin/sales-groups")
@require_login
def list_sales_groups():
    """Same salesman list as report filters (`LookupService.salesmen()`).

    Privileged-only so Users & access is not tied to a report key (Ordered
    off would 403 `/api/reports/ordered/salesmen`).
    """
    blocked = _guard()
    if blocked:
        return blocked
    items = current_app.config["LOOKUP_SERVICE"].salesmen()
    return jsonify({"ok": True, "items": items})


@admin_bp.get("/api/admin/users/<int:user_id>/report-access")
@require_login
def get_report_access(user_id: int):
    blocked = _guard()
    if blocked:
        return blocked
    # Only explicit overrides are stored; a key absent here means "inherit".
    overrides = _users().get_report_access(user_id)
    return jsonify({"access": {k: ("allow" if v else "deny") for k, v in overrides.items()}})


@admin_bp.post("/api/admin/users/<int:user_id>/report-access")
@require_login
def set_report_access(user_id: int):
    blocked = _guard()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    if registry.get(report_key) is None:
        return jsonify({"error": "Unknown report"}), 400
    # Tri-state per the legacy model: inherit (clear the row -> role default),
    # allow, or deny. Back-compat: a bare {allowed: bool} still works.
    access = (body.get("access") or "").strip().lower()
    if not access:
        # Back-compat: a bare {allowed: bool}. A request with NEITHER field is
        # malformed - never default to a destructive "deny" write.
        if "allowed" not in body:
            return jsonify({"error": "access must be inherit|allow|deny"}), 400
        access = "allow" if body.get("allowed") else "deny"
    if access == "inherit":
        _users().clear_report_access(user_id, report_key)
    elif access in ("allow", "deny"):
        _users().set_report_access(user_id, report_key, access == "allow")
    else:
        return jsonify({"error": "access must be inherit|allow|deny"}), 400
    return jsonify({"report_key": report_key, "access": access})


# --- salesman edit ----------------------------------------------------------

@admin_bp.put("/api/admin/salesmen/<key>")
@require_login
def update_salesman(key: str):
    blocked = _guard()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    fields: dict = {}
    for name in ("number", "full_name", "display_name", "email"):
        if name in body:
            fields[name] = str(body[name]).strip()
    if "is_active" in body:
        fields["is_active"] = bool(body["is_active"])
    if not _salesmen().update(key, **fields):
        return jsonify({"error": "Unknown salesman or no editable fields"}), 404
    return jsonify({"key": key, **fields})


# --- export history (admin-only) -------------------------------------------

@admin_bp.get("/api/admin/exports")
@require_login
def export_history():
    """Browse past exports (admin only). Supports ?report_key= and ?owner= filters."""
    blocked = _guard()
    if blocked:
        return blocked
    from web.data.repositories.exports import ExportRepository

    exports = ExportRepository(current_app.config["DB"])
    report_key = request.args.get("report_key") or None
    owner = request.args.get("owner") or None
    metas = exports.history(report_key=report_key, owner_email=owner, limit=200)
    return jsonify({"exports": [
        {"job_id": m.job_id, "report_key": m.report_key, "filename": m.filename,
         "size_bytes": m.size_bytes, "built_at": m.built_at,
         "export_type": m.export_type, "owner_email": m.owner_email}
        for m in metas
    ]})
