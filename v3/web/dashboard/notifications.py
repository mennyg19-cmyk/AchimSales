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
