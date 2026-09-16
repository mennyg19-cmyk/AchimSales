"""Generate overdue-customer notifications from a fresh mirror.

Run right after a mirror rebuild. For each active user, find the overdue
customers in their scope (privileged = all; others = their granted salesman
keys), then create one `overdue_customer` notification per account, skipping
excluded accounts, accounts that already have an undismissed alert, and accounts
dismissed within the cooldown window (LIVE parity: 7 days).
"""

from __future__ import annotations

import logging

from report_engine.lib import salesman_key
from web.auth.principal import _PRIVILEGED
from web.dashboard.metrics import STATUS_OVERDUE
from web.data.repositories.dashboard import DashboardRepository
from web.data.repositories.exclusions import ExclusionRepository
from web.data.repositories.notifications import OVERDUE, NotificationRepository
from web.data.repositories.users import UserRepository

log = logging.getLogger(__name__)

COOLDOWN_DAYS = 7


def generate_overdue_notifications(db) -> int:
    """Returns the number of notifications created across all users."""
    dash = DashboardRepository(db).all()
    overdue = [r for r in dash if r.status == STATUS_OVERDUE]
    if not overdue:
        return 0

    users = UserRepository(db)
    notifs = NotificationRepository(db)
    exclusions = ExclusionRepository(db)
    created = 0

    for user in users.list_all():
        if not user.is_active:
            continue
        if user.role in _PRIVILEGED:
            allowed = None  # sees all overdue customers
        else:
            allowed = users.get_salesman_access(user.id)
            if not allowed:
                continue  # no scope -> nothing to notify

        excluded = exclusions.get(user.id)
        cooldown = notifs.recently_dismissed_accounts(user.id, OVERDUE, COOLDOWN_DAYS)
        for r in overdue:
            acct = r.customer_account
            if acct in excluded or acct in cooldown:
                continue
            if allowed is not None and salesman_key(r.sales_group) not in allowed:
                continue
            if notifs.has_undismissed_account(user.id, OVERDUE, acct):
                continue
            notifs.create(user.id, OVERDUE,
                          {"customer_account": acct, "customer_name": r.customer_name})
            created += 1

    log.info("overdue notifications created: %d", created)
    return created


def diagnose_overdue(db, user) -> dict:
    """Dry-run of the overdue pipeline for one user (notification diagnostic)."""
    dash = DashboardRepository(db).all()
    overdue = [r for r in dash if r.status == STATUS_OVERDUE]
    notifs = NotificationRepository(db)
    exclusions = ExclusionRepository(db)
    if user.role in _PRIVILEGED:
        allowed = None
    else:
        allowed = UserRepository(db).get_salesman_access(user.id)
    excluded = exclusions.get(user.id)
    cooldown = notifs.recently_dismissed_accounts(user.id, OVERDUE, COOLDOWN_DAYS)
    would_create: list[dict] = []
    would_skip: list[dict] = []
    scoped = []
    for r in overdue:
        if allowed is not None and salesman_key(r.sales_group) not in allowed:
            continue
        scoped.append(r)
        acct = r.customer_account
        reasons = []
        if acct in excluded:
            reasons.append("excluded")
        if acct in cooldown:
            reasons.append("dismissed recently")
        if notifs.has_undismissed_account(user.id, OVERDUE, acct):
            reasons.append("already notified")
        item = {"customer_account": acct, "customer_name": r.customer_name,
                "sales_group": r.sales_group}
        if reasons:
            would_skip.append({**item, "reason": ", ".join(reasons)})
        else:
            would_create.append(item)
    active = notifs.list_undismissed(user.id, OVERDUE)
    return {
        "matched_customers": len(dash) if allowed is None else len(
            [r for r in dash if salesman_key(r.sales_group) in (allowed or set())]
        ),
        "overdue_in_scope": len(scoped),
        "would_create": would_create,
        "would_skip": would_skip,
        "excluded": sorted(excluded),
        "cooldown": sorted(cooldown),
        "active_notifications": [
            {"id": n.id, "customer_account": n.payload.get("customer_account"),
             "created_at": n.created_at}
            for n in active
        ],
        "last_refreshed": DashboardRepository(db).last_refreshed(),
    }
