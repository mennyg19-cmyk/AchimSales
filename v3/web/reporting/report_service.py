"""Report service: the connective layer between routes and the pure builders.

`builder_for(report_key)` returns a `runner.Builder` closure
`(filter_params) -> {report_key, tabs, row_count}` that:
    1. translates filter params -> SP params (web.reporting.params),
    2. fetches rows from the on-prem Reporting API (http_client),
    3. adapts rows -> typed facts (report_engine.sources),
    4. runs the pure builder (report_engine.reports),
    5. wraps the tabs into the viewer payload.

Multi-source reports own their extra fetches here (not in the builder):
    * invoiced     -> a second YTD fetch feeds the monthly commissions pivot,
    * number_4     -> released_products supplies Book Price (optional),
    * customer_activity -> customer_master is the universe (mirror fallback).
The builders stay pure and source-agnostic; this is where I/O lives.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable

from report_engine.dates import sp_datetime, today_eastern
from report_engine.reports import customer_activity as rpt_customer_activity
from report_engine.reports import invoiced as rpt_invoiced
from report_engine.reports import number_4 as rpt_number_4
from report_engine.reports import ordered as rpt_ordered
from report_engine.reports import salesman as rpt_salesman
from report_engine.sources import customer_master as src_customers
from report_engine.sources import invoice_lines as src_lines
from report_engine.sources import invoiced as src_invoiced
from report_engine.sources import ordered as src_ordered
from report_engine.sources import released_products as src_released
from web.reporting import params as P
from web.reporting.http_client import ReportingApiError
from web.reporting.runner import Builder

log = logging.getLogger(__name__)

# Optional fallback that returns customer_master-shaped rows from a local
# mirror when the live SP is unreachable (owner decision #15).
CustomerMirror = Callable[[], list[dict]]


def _resolved_year(params: dict) -> int:
    raw = (params or {}).get("year")
    try:
        return int(raw) if raw not in (None, "") else today_eastern().year
    except (TypeError, ValueError):
        return today_eastern().year


class ReportService:
    def __init__(self, client, salesmen_repo, *, customer_mirror: CustomerMirror | None = None):
        self.client = client
        self.salesmen_repo = salesmen_repo
        self.customer_mirror = customer_mirror

    # -- public -----------------------------------------------------------

    def builder_for(self, report_key: str) -> Builder:
        orchestrate = _ORCHESTRATORS.get(report_key)
        if orchestrate is None:
            raise KeyError(f"No report service for {report_key!r}")
        return lambda params: orchestrate(self, params or {})

    # -- shared helpers ---------------------------------------------------

    def _salesmen(self) -> dict:
        return self.salesmen_repo.all_as_facts()

    def _rows(self, report_id: str, sp_params: dict) -> list[dict]:
        return self.client.run_report(report_id, sp_params).rows

    @staticmethod
    def _payload(report_key: str, tabs: list[dict], row_count: int, **extra) -> dict:
        return {"report_key": report_key, "tabs": tabs, "row_count": row_count, **extra}

    def _customer_universe(self) -> list:
        """Live customer_master each run; fall back to the local mirror if down."""
        try:
            rows = self._rows("customer_master", {})
            return src_customers.to_facts(rows)
        except ReportingApiError:
            log.warning("customer_master SP unreachable; using mirror fallback")
            if self.customer_mirror is not None:
                return src_customers.to_facts(self.customer_mirror())
            return []

    def _book_prices(self) -> dict | None:
        """released_products SalesPrice map for Book Price; None if unavailable."""
        try:
            return src_released.to_book_price_map(self._rows("released_products", {}))
        except ReportingApiError:
            log.warning("released_products unreachable; Book Price will be blank")
            return None


# --------------------------------------------------------------------------- #
# Per-report orchestration (module-level so the closure stays thin)
# --------------------------------------------------------------------------- #

def _orch_ordered(svc: ReportService, params: dict) -> dict:
    rows = svc._rows("salesline_release", P.translate("ordered", params))
    tabs = rpt_ordered.build(src_ordered.to_facts(rows))
    return svc._payload("ordered", tabs, len(rows))


def _orch_invoiced(svc: ReportService, params: dict) -> dict:
    rows = svc._rows("invoiced_order_charges", P.translate("invoiced", params))
    facts = src_invoiced.to_facts(rows)

    year = _resolved_year(params)
    today = today_eastern()
    end = today if year == today.year else date(year, 12, 31)
    ytd_rows = svc._rows("invoiced_order_charges", {
        "InvoiceDateFrom": sp_datetime(date(year, 1, 1), end_of_day=False),
        "InvoiceDateTo": sp_datetime(end, end_of_day=True),
    })
    tabs = rpt_invoiced.build(
        facts, salesmen=svc._salesmen(),
        ytd_facts=src_invoiced.to_facts(ytd_rows), year=year, end_month=end.month,
    )
    return svc._payload("invoiced", tabs, len(rows))


def _orch_salesman(svc: ReportService, params: dict) -> dict:
    rows = svc._rows("invoiced_order_charges", P.translate("salesman", params))
    tabs = rpt_salesman.build(src_invoiced.to_facts(rows),
                              salesmen=svc._salesmen(), year=_resolved_year(params))
    return svc._payload("salesman", tabs, len(rows))


def _orch_number_4(svc: ReportService, params: dict) -> dict:
    rows = svc._rows("invoice_lines", P.translate("number_4", params))
    tabs = rpt_number_4.build(src_lines.to_facts(rows), today=today_eastern(),
                              salesmen=svc._salesmen(), book_prices=svc._book_prices())
    return svc._payload("number_4", tabs, len(rows))


def _orch_customer_activity(svc: ReportService, params: dict) -> dict:
    order_rows = svc._rows("salesline_release", P.translate("customer_activity", params))
    tabs = rpt_customer_activity.build(
        svc._customer_universe(), src_ordered.to_facts(order_rows),
        salesmen=svc._salesmen(), scope=params,
    )
    return svc._payload("customer_activity", tabs, len(order_rows))


_ORCHESTRATORS: dict[str, Callable[[ReportService, dict], dict]] = {
    "ordered": _orch_ordered,
    "invoiced": _orch_invoiced,
    "salesman": _orch_salesman,
    "number_4": _orch_number_4,
    "customer_activity": _orch_customer_activity,
}
