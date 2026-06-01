"""Dashboard read model: tiles + the scoped/filtered customer table.

Pure-ish view layer over the precomputed `dashboard_customers` cache. Applies
the viewer's salesman scope (None = privileged/unrestricted) and removes their
excluded customers from the tile counts (matching LIVE: excluded rows are kept
in the table flagged `excluded`, but never counted in the tiles).
"""

from __future__ import annotations

from dataclasses import dataclass

from report_engine.lib import salesman_key
from web.dashboard.metrics import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_NEW,
    STATUS_OVERDUE,
)
from web.data.repositories.dashboard import DashboardCustomer, DashboardRepository


@dataclass(frozen=True)
class DashboardSummary:
    total: int
    new: int
    active: int
    overdue: int
    inactive: int


def _in_scope(row: DashboardCustomer, allowed: set[str] | None) -> bool:
    if allowed is None:
        return True
    return salesman_key(row.sales_group) in allowed


class DashboardService:
    def __init__(self, repo: DashboardRepository):
        self.repo = repo

    def view(self, *, allowed_keys: set[str] | None, excluded: set[str]):
        """Return (summary, rows). `rows` keep excluded customers flagged so the
        table can show + style them; the summary counts only included rows."""
        rows = [r for r in self.repo.all() if _in_scope(r, allowed_keys)]
        included = [r for r in rows if r.customer_account not in excluded]
        summary = DashboardSummary(
            total=len(included),
            new=sum(1 for r in included if r.status == STATUS_NEW),
            active=sum(1 for r in included if r.status == STATUS_ACTIVE),
            overdue=sum(1 for r in included if r.status == STATUS_OVERDUE),
            inactive=sum(1 for r in included if r.status == STATUS_INACTIVE),
        )
        return summary, rows

    def last_refreshed(self) -> str | None:
        return self.repo.last_refreshed()
