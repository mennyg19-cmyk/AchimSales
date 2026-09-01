"""Customer mirror refresh: rebuild the dashboard customer aggregates.

Pulls the customer universe (customer_master) and the all-time order history
(salesline_release, go-live..today) from the Reporting API, groups orders per
customer, runs the cadence metrics, and rebuilds `dashboard_customers` in one
full refresh. This is the v3 analogue of LIVE's `refresh_cache()`, but sourced
from the Reporting API (like the test app) rather than the CLI D365 clients.
"""

from __future__ import annotations

import logging
from datetime import date

from web.dashboard.metrics import compute_metrics
from web.data.repositories.dashboard import DashboardCustomer, DashboardRepository
from report_engine.lib import iso_date

log = logging.getLogger(__name__)


def _parse_date(s: str) -> date | None:
    iso = iso_date(s)
    if not iso or len(iso) != 10 or iso[4] != "-":
        return None
    try:
        return date.fromisoformat(iso)
    except ValueError:
        return None


class MirrorService:
    """Rebuilds dashboard aggregates from the report service's fetches.

    `customers_fetch` returns CustomerFact list; `orders_fetch` returns
    OrderLineFact list over the all-time window. Injected so this stays testable
    without the live API.
    """

    def __init__(self, *, customers_fetch, orders_fetch, repo: DashboardRepository):
        self._customers = customers_fetch
        self._orders = orders_fetch
        self.repo = repo

    def rebuild(self, *, today: date | None = None) -> int:
        today = today or date.today()
        customers = list(self._customers())
        orders = list(self._orders())

        dates_by_acct: dict[str, list[date]] = {}
        for o in orders:
            acct = o.customer_account
            d = _parse_date(o.order_date)
            if acct and d is not None:
                dates_by_acct.setdefault(acct, []).append(d)

        records: list[DashboardCustomer] = []
        for c in customers:
            acct = c.customer_account
            if not acct:
                continue
            order_dates = dates_by_acct.get(acct, [])
            m = compute_metrics(order_dates, today=today)
            records.append(DashboardCustomer(
                customer_account=acct, customer_name=c.customer_name,
                sales_group=c.sales_group or "",
                last_order_date=m.last_order_date.isoformat() if m.last_order_date else None,
                order_count=len(order_dates), avg_gap_days=m.avg_gap_days,
                gap_stdev=m.gap_stdev, overdue_threshold=m.overdue_threshold,
                days_since_last=m.days_since_last, status=m.status,
            ))

        written = self.repo.replace_all(records)
        log.info("dashboard mirror rebuilt: %d customers", written)
        return written

    def rebuild_customers_only(self) -> int:
        """Write customer_master into the mirror with empty cadence metrics.

        Home site keeps dashboard.refresh off (no all-time orders pull) but
        salesman/customer dropdowns still need this table.
        """
        customers = list(self._customers())
        records: list[DashboardCustomer] = []
        for c in customers:
            acct = c.customer_account
            if not acct:
                continue
            records.append(DashboardCustomer(
                customer_account=acct, customer_name=c.customer_name,
                sales_group=c.sales_group or "",
                last_order_date=None, order_count=0, avg_gap_days=None,
                gap_stdev=None, overdue_threshold=None, days_since_last=None,
                status="new",
            ))
        written = self.repo.replace_all(records)
        log.info("lookups mirror rebuilt: %d customers", written)
        return written
