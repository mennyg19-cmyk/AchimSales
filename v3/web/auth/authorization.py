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
from web.auth.principal import _PRIVILEGED, Principal
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
        if self._is_privileged(u):
            return True
        # Non-privileged: FAIL CLOSED. Visible only with an explicit allow row.
        # NOTE: the live "default visible set" / global-visibility model is a
        # business policy pending human sign-off (see REVIEW-LOG); until then we
        # default-deny rather than guess a broader rule.
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT allowed FROM user_report_access WHERE user_id = ? AND report_key = ?",
                (u.id, report_key),
            ).fetchone()
        return bool(row and row["allowed"])

    def assert_can_view_report(self, p: Principal, report_key: str) -> None:
        if not self.can_view_report(p, report_key):
            raise Forbidden(f"Not authorized for report {report_key!r}")

    # --- SharePoint ---------------------------------------------------------

    def has_sharepoint_access(self, p: Principal) -> bool:
        u = self._active_user(p)
        if u is None:
            return False
        if self._is_privileged(u):
            return True
        return bool(u.sharepoint_access)
