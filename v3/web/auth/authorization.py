"""THE single authorization / scope layer (rule 6).

One object answers every "may this principal see this thing?" question:
report access, customer/salesman scope, and SharePoint. Routes never re-implement
these checks - they call `assert_*` (raises Forbidden) or the boolean helpers.

SECURITY: the session is trusted only for IDENTITY (email). Role, active-status,
scope, and flags are RE-RESOLVED from the database on every check, so revoking a
role or disabling a user takes effect immediately (no stale-cookie escalation -
matches live behaviour in test/webapp/auth.py). Unknown/inactive users are denied
everything (fail closed).
"""

from __future__ import annotations

from report_engine import registry
from report_engine.lib import salesman_key
from report_engine.registry import ReportStatus
from web.auth.principal import _PRIVILEGED, ROLE_DEVELOPER, ROLE_MANAGER, Principal
from web.data.connection import Database
from web.data.repositories.users import User, UserRepository


class Forbidden(Exception):
    """Raised when a principal lacks access. Mapped to HTTP 403 by the app."""

    status_code = 403


class Authorization:
    def __init__(self, db: Database):
        self.db = db
        self.users = UserRepository(db)

    def _active_user(self, p: Principal | None) -> User | None:
        """The live DB row, or None if unknown/inactive (deny). Never the cookie."""
        if p is None or not p.email:
            return None
        u = self.users.get_by_email(p.email)
        return u if (u and u.is_active) else None

    @staticmethod
    def _is_privileged(u: User) -> bool:
        return u.role in _PRIVILEGED

    def is_privileged(self, p: Principal | None) -> bool:
        """Live (DB-resolved) privilege check - never trusts the session role."""
        u = self._active_user(p)
        return bool(u and self._is_privileged(u))

    def is_manager(self, p: Principal | None) -> bool:
        u = self._active_user(p)
        return bool(u and u.role == ROLE_MANAGER)

    def is_developer(self, p: Principal | None) -> bool:
        """Live DB role is developer. Never the session/cookie role."""
        u = self._active_user(p)
        return bool(u and u.role == ROLE_DEVELOPER)

    def can_see_company_schedules(self, p: Principal | None) -> bool:
        """Admins, developers, and managers see the shared company list."""
        return self.is_privileged(p) or self.is_manager(p)

    def user_id(self, p: Principal | None) -> int | None:
        u = self._active_user(p)
        return u.id if u else None

    def can_edit_master(self, p: Principal | None, *, owner_user_id: int | None,
                        run_as_user_id: int | None) -> bool:
        """Privileged: always. Manager: only if they created it or it runs as them."""
        if self.is_privileged(p):
            return True
        if not self.is_manager(p):
            return False
        uid = self.user_id(p)
        if uid is None:
            return False
        return uid == owner_user_id or uid == run_as_user_id

    def may_see_commissions(self, p: Principal | None) -> bool:
        """Commissions is a company tab. Salesmen never see it; managers and admins do."""
        return self.is_privileged(p) or self.is_manager(p)

    # --- salesman / customer scope -----------------------------------------

    def visible_salesman_keys(self, p: Principal) -> set[str] | None:
        """Keys the principal may see. None = UNRESTRICTED (privileged + active)."""
        u = self._active_user(p)
        if u is None:
            return set()  # unknown/inactive -> sees nothing
        if self._is_privileged(u):
            return None
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT salesman_key FROM user_salesman_access WHERE user_id = ?", (u.id,)
            ).fetchall()
        return {r["salesman_key"] for r in rows}

    def can_view_customer(self, p: Principal, customer_sales_group: str | None) -> bool:
        keys = self.visible_salesman_keys(p)
        if keys is None:
            return True
        return salesman_key(customer_sales_group) in keys

    def assert_can_view_customer(self, p: Principal, customer_sales_group: str | None) -> None:
        if not self.can_view_customer(p, customer_sales_group):
            raise Forbidden("Not authorized for this customer")

    # --- report access ------------------------------------------------------

    def can_view_report(self, p: Principal, report_key: str) -> bool:
        spec = registry.get(report_key)
        if spec is None or spec.status is not ReportStatus.BUILT:
            return False  # unknown or backlog reports are never viewable (no fake stubs)
        u = self._active_user(p)
        if u is None:
            return False
        # Company-wide admin reports: salesmen and managers never get them, even
        # with an explicit allow row.
        if getattr(spec, "privileged_only", False) and not self._is_privileged(u):
            return False
        with self.db.precious() as conn:
            override = conn.execute(
                "SELECT allowed FROM user_report_access WHERE user_id = ? AND report_key = ?",
                (u.id, report_key),
            ).fetchone()
            glob = conn.execute(
                "SELECT enabled FROM report_config WHERE report_key = ?", (report_key,),
            ).fetchone()
        # Per-user override wins (Live). Else a missing report_config row is on.
        if override is not None:
            return bool(override["allowed"])
        if glob is not None and not glob["enabled"]:
            return False
        if self._is_privileged(u):
            return True
        return self._role_default_report_visible(u.role, spec)

    @staticmethod
    def _role_default_report_visible(role: str, spec) -> bool:
        """Legacy 'inherit' default: managers see all; salesmen see salesman-filter
        reports only. (admin/developer never reach here - they're privileged.)"""
        if role == ROLE_MANAGER:
            return True
        return bool(spec.salesman_default)

    def assert_can_view_report(self, p: Principal, report_key: str) -> None:
        if not self.can_view_report(p, report_key):
            raise Forbidden(f"Not authorized for report {report_key!r}")

    def assert_report_runnable(self, p: Principal, report_key: str) -> None:
        """Gate the run/result/export path. Re-resolves access live.

        Builders now apply per-salesman scope filtering at execution time, so
        non-privileged users are no longer blocked. They see only facts whose
        sales_group matches their visible_salesman_keys (Phase 1 scoping).
        """
        if not report_key:
            raise Forbidden("Missing report")
        self.assert_can_view_report(p, report_key)

    # --- deferred delivery (durable jobs + scheduled runs) ------------------

    def principal_for_user_id(self, user_id: int | None) -> Principal | None:
        """The live principal for a stored owner id, or None if gone/inactive.

        Used by the job worker + scheduler to RE-RESOLVE the owner at execution
        time instead of trusting whatever identity/scope was captured at enqueue
        (which can be stale after a role change or a disable)."""
        if user_id is None:
            return None
        u = self.users.get_by_id(user_id)
        if u is None or not u.is_active:
            return None
        return Principal(email=u.email, name=u.display_name or u.email, role=u.role)

    def authorize_delivery(self, p: Principal | None, report_key: str,
                           *, sharepoint: bool) -> set[str] | None:
        """Gate a deferred delivery and return the live salesman scope.

        Fails closed exactly like an interactive run: verifies the owner is still
        active and has report access, plus SharePoint permission when applicable.
        Returns visible_salesman_keys for the builder's scope filter. This prevents
        a queued/scheduled send from delivering data the owner is no longer allowed
        to see."""
        if p is None:
            raise Forbidden("Delivery owner is unknown or inactive")
        self.assert_report_runnable(p, report_key)
        if sharepoint and not self.has_sharepoint_access(p):
            raise Forbidden("SharePoint delivery is not permitted for this user")
        return self.visible_salesman_keys(p)

    # --- SharePoint ---------------------------------------------------------

    def has_sharepoint_access(self, p: Principal) -> bool:
        u = self._active_user(p)
        if u is None:
            return False
        if self._is_privileged(u):
            return True
        return bool(u.sharepoint_access)

    def can_see_company_views(self, p: Principal | None) -> bool:
        """Named company views on Home / Saved views / the wizard.

        Admins and developers always see them. Everyone else needs the flag.
        """
        u = self._active_user(p)
        if u is None:
            return False
        if self._is_privileged(u):
            return True
        return bool(u.can_see_company_views)
