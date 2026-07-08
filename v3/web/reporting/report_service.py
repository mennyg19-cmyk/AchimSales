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
    * number_4     -> one or two rolling-12 SPs, picked by the mode filter,
    * customer_activity -> customer_master is the universe (mirror fallback).
The builders stay pure and source-agnostic; this is where I/O lives.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable

from report_engine.dates import D365_GO_LIVE, month_chunks, sp_datetime, today_eastern
from report_engine.reports import customer_activity as rpt_customer_activity
from report_engine.reports import invoiced as rpt_invoiced
from report_engine.reports import number_4 as rpt_number_4
from report_engine.reports import ordered as rpt_ordered
from report_engine.reports import salesman as rpt_salesman
from report_engine.sources import customer_master as src_customers
from report_engine.sources import invoiced as src_invoiced
from report_engine.sources import ordered as src_ordered
from report_engine.lib import filter_facts_by_scope
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
        return lambda params, visible_keys: orchestrate(self, params or {}, visible_keys)

    # -- shared helpers ---------------------------------------------------

    def _salesmen(self) -> dict:
        return self.salesmen_repo.all_as_facts()

    def _rows(self, report_id: str, sp_params: dict) -> list[dict]:
        return self.client.run_report(report_id, sp_params).rows

    def _facts(self, report_id: str, sp_params: dict, adapter, visible_keys) -> list:
        """Fetch SP rows, adapt to facts, and scope-filter -- in one scope.

        The raw row dicts (every SP column) only live inside this method, so
        Python can reclaim that memory before the builder starts. Keeps peak
        memory at roughly one copy of the data instead of two.
        """
        rows = self._rows(report_id, sp_params)
        return filter_facts_by_scope(adapter(rows), visible_keys)

    def _facts_chunked(self, report_id: str, base_sp: dict, adapter, visible_keys,
                       *, from_key: str, to_key: str, start: date, end: date) -> list:
        """Fetch a big window one month at a time, then concatenate the facts.

        A full-window pull (e.g. a whole year of order lines) can be too big for
        the on-prem Reporting API to return inside its timeout, so the single
        request fails and you get nothing. Splitting the date window into
        month-sized requests keeps each response small enough to come back. The
        month chunks use the same day boundaries the daily reports use, so the
        stitched-together result is the same set of rows as one call - none
        dropped, none double-counted. Each chunk's raw rows are adapted (and
        released) before the next request, so peak memory stays near one month
        instead of the whole window. Rows come back grouped month-by-month
        (chronological), which the builders aggregate order-independently.
        """
        facts: list = []
        for chunk_start, chunk_end in month_chunks(start, end):
            sp = dict(base_sp)
            sp[from_key] = sp_datetime(chunk_start, end_of_day=False)
            sp[to_key] = sp_datetime(chunk_end, end_of_day=True)
            facts.extend(filter_facts_by_scope(adapter(self._rows(report_id, sp)), visible_keys))
        return facts

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

    # -- dashboard mirror feeds (public; used by the mirror refresh) -------

    def customer_universe(self) -> list:
        """CustomerFact universe for the dashboard mirror (customer_master)."""
        return self._customer_universe()

    def all_orders(self) -> list:
        """All-time OrderLineFacts (go-live..today) for cadence metrics.

        Chunked by month: all-time is the biggest salesline_release pull there is,
        so a single call would blow the API timeout.
        """
        return self._facts_chunked(
            "salesline_release", P.translate("customer_activity", {}),
            src_ordered.to_facts, None,
            from_key="CreatedDateTimeFrom", to_key="CreatedDateTimeTo",
            start=D365_GO_LIVE, end=today_eastern())

    def customer_orders(self, account: str) -> list:
        """All-time OrderLineFacts for one customer (dashboard customer detail)."""
        sp = P.translate("ordered", {"period": "all_time", "customers": [account]})
        return src_ordered.to_facts(self._rows("salesline_release", sp))

    def last_order_facts(self, account: str) -> list:
        """Full-history OrderLineFacts for one customer (Customer's Last Order).

        Anchors the window to go-live..today explicitly (like customer_activity)
        so the "last invoiced order" is found over the customer's whole history,
        not just the SP's default window.
        """
        sp = {
            "CreatedDateTimeFrom": sp_datetime(D365_GO_LIVE, end_of_day=False),
            "CreatedDateTimeTo": sp_datetime(today_eastern(), end_of_day=True),
            "CustomerAccount": account,
        }
        return src_ordered.to_facts(self._rows("salesline_release", sp))


# --------------------------------------------------------------------------- #
# Per-report orchestration (module-level so the closure stays thin)
# --------------------------------------------------------------------------- #

def _orch_ordered(svc: ReportService, params: dict, visible_keys) -> dict:
    report_id = P.report_id_for("ordered")  # rpt.usp_ordered_report
    base_sp = P.translate("ordered", params)
    start, end = P.resolve_window(params)
    # A bounded period (daily/MTD/YTD/last month/custom) is fetched month-by-month
    # so a big YTD doesn't blow the API timeout. Open-ended (all_time/blank) keeps
    # the single call so the SP's own default window is unchanged.
    if start and end:
        facts = svc._facts_chunked(
            report_id, base_sp, src_ordered.to_facts_ordered_report, visible_keys,
            from_key="CreatedDateTimeFrom", to_key="CreatedDateTimeTo",
            start=start, end=end)
    else:
        facts = svc._facts(report_id, base_sp, src_ordered.to_facts_ordered_report, visible_keys)
    # The new SP's CustomerAccount is a single exact match, so a multi-customer
    # selection isn't pushed down -- post-filter it here (same as invoiced).
    accounts = _selected_accounts(params)
    if len(accounts) > 1:
        facts = [f for f in facts if f.customer_account in accounts]
    # build() consumes the facts list to keep peak memory down on big runs, so
    # capture the count first.
    row_count = len(facts)
    tabs = rpt_ordered.build(facts)
    return svc._payload("ordered", tabs, row_count)


def _selected_accounts(params: dict) -> set[str]:
    """Customer accounts selected in the filter, as a set of trimmed strings."""
    c = (params or {}).get("customers")
    if isinstance(c, (list, tuple, set)):
        return {str(x).strip() for x in c if str(x).strip()}
    if c:
        return {s.strip() for s in str(c).split(",") if s.strip()}
    return set()


def _orch_invoiced(svc: ReportService, params: dict, visible_keys) -> dict:
    report_id = P.report_id_for("invoiced")
    sp = P.translate("invoiced", params)
    facts = svc._facts(report_id, sp, src_invoiced.to_facts, visible_keys)

    _, period_end = P.resolve_window(params)
    end = period_end or today_eastern()
    year = end.year
    ytd_sp = dict(sp)
    ytd_sp["InvoiceDateFrom"] = date(year, 1, 1).isoformat()
    ytd_sp["InvoiceDateTo"] = end.isoformat()
    ytd_facts = svc._facts(report_id, ytd_sp, src_invoiced.to_facts, visible_keys)

    accounts = _selected_accounts(params)
    if len(accounts) > 1:
        facts = [f for f in facts if f.customer_account in accounts]
        ytd_facts = [f for f in ytd_facts if f.customer_account in accounts]

    tabs = rpt_invoiced.build(
        facts, salesmen=svc._salesmen(),
        ytd_facts=ytd_facts, year=year, end_month=end.month,
    )
    return svc._payload("invoiced", tabs, len(facts))


def _orch_salesman(svc: ReportService, params: dict, visible_keys) -> dict:
    facts = svc._facts("invoiced_order_charges", P.translate("salesman", params),
                       src_invoiced.to_facts, visible_keys)
    tabs = rpt_salesman.build(facts, salesmen=svc._salesmen(), year=_resolved_year(params))
    return svc._payload("salesman", tabs, len(facts))


def _orch_number_4(svc: ReportService, params: dict, visible_keys) -> dict:
    """Number 4 = the finished rolling-12 pivots straight from the SPs.

    The mode filter decides which view(s) to fetch: By Customer, By Item, or
    Both (two SP calls, two tabs). The SPs do all the math (monthly pivots,
    totals, Book Price join), so there's no fact adapter -- rows are cleaned,
    scope-filtered on the Salesman column, and passed through.
    """
    sp = P.translate("number_4", params)
    mode = P.number_4_mode(params)

    def fetch(report_id: str) -> rpt_number_4.View:
        # Keep the API's column list (not just the rows): a run with zero rows
        # (or one fully scope-filtered) still needs its headers on screen.
        fetched = svc.client.run_report(report_id, sp)
        headers = fetched.columns or (list(fetched.rows[0].keys()) if fetched.rows else [])
        rows = rpt_number_4.filter_rows_by_salesman(
            rpt_number_4.clean_rows(fetched.rows), visible_keys)
        return headers, rows

    by_customer = fetch(P.NUMBER_4_BY_CUSTOMER_SP) if mode in ("both", "by_customer") else None
    by_item = fetch(P.NUMBER_4_BY_ITEM_SP) if mode in ("both", "by_item") else None
    tabs = rpt_number_4.build(by_customer=by_customer, by_item=by_item)
    row_count = sum(len(view[1]) for view in (by_customer, by_item) if view is not None)
    return svc._payload("number_4", tabs, row_count)


def _orch_customer_activity(svc: ReportService, params: dict, visible_keys) -> dict:
    # All-time order history (go-live..today), chunked by month so the largest
    # salesline_release pull doesn't blow the API timeout.
    orders = svc._facts_chunked(
        "salesline_release", P.translate("customer_activity", params),
        src_ordered.to_facts, visible_keys,
        from_key="CreatedDateTimeFrom", to_key="CreatedDateTimeTo",
        start=D365_GO_LIVE, end=today_eastern())
    customers = filter_facts_by_scope(svc._customer_universe(), visible_keys)
    tabs = rpt_customer_activity.build(
        customers, orders, salesmen=svc._salesmen(), scope=params,
    )
    return svc._payload("customer_activity", tabs, len(orders))


_ORCHESTRATORS: dict[str, Callable[[ReportService, dict, set | None], dict]] = {
    "ordered": _orch_ordered,
    "invoiced": _orch_invoiced,
    "salesman": _orch_salesman,
    "number_4": _orch_number_4,
    "customer_activity": _orch_customer_activity,
}
