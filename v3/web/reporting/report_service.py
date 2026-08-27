"""Report service: the connective layer between routes and the pure builders.

`builder_for(report_key)` returns a `runner.Builder` closure
`(filter_params) -> {report_key, tabs, row_count}` that:
    1. translates filter params -> SP params (web.reporting.params),
    2. fetches rows from the on-prem Reporting API (http_client),
    3. adapts rows -> typed facts (report_engine.sources),
    4. runs the pure builder (report_engine.reports),
    5. wraps the tabs into the viewer payload.

Multi-source reports own their extra fetches here (not in the builder):
    * invoiced     -> YTD rows feed the monthly commissions pivot (one pull when
      the selected period already sits inside that YTD window). Skipped when
      the output will not include Commissions (salesman-scoped / shipped, or a
      saved layout that dropped that tab),
    * salesman     -> monthly_salesman_yoy (wide YoY pivot; no invoice facts),
    * number_4     -> one or two rolling-12 SPs, picked by the mode filter
      (each view becomes a 12-month tab plus a YTD tab derived from it),
    * customer_activity -> dedicated customer_activity SP (All + salesman tabs).
The builders stay pure and source-agnostic; this is where I/O lives.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from typing import Any, Callable

from report_engine.dates import D365_GO_LIVE, month_chunks, sp_datetime, today_eastern
from report_engine.facts import InvoiceChargeFact, SalesmanFact
from report_engine.lib import filter_facts_by_scope, salesman_key
from report_engine.reports import customer_activity as rpt_customer_activity
from report_engine.reports import invoiced as rpt_invoiced
from report_engine.reports import item_averages as rpt_item_averages
from report_engine.reports import number_4 as rpt_number_4
from report_engine.reports import ordered as rpt_ordered
from report_engine.reports import salesman as rpt_salesman
from report_engine.reports import sales_by_state as rpt_sales_by_state
from report_engine.sources import customer_master as src_customers
from report_engine.sources import invoiced as src_invoiced
from report_engine.sources import ordered as src_ordered
from web.reporting import params as P
from web.reporting.http_client import ReportingApiError
from web.reporting.runner import Builder

log = logging.getLogger(__name__)

# Optional fallback that returns customer_master-shaped rows from a local
# mirror when the live SP is unreachable (owner decision #15).
CustomerMirror = Callable[[], list[dict]]


def _is_numeric_sales_group(value: str) -> bool:
    digits = value.replace(" ", "")
    return bool(digits) and digits.isdigit()


def _known_salesman_labels(salesmen: dict[str, SalesmanFact],
                           customers_by_acct: dict[str, str] | None = None) -> set[str]:
    """Labels the salesman/customer dropdowns would accept (not Excel numbers)."""
    known: set[str] = set()
    for sm in salesmen.values():
        for label in (sm.key, sm.display_name):
            if label:
                known.add(label)
                known.add(salesman_key(label))
    if customers_by_acct:
        for sg in customers_by_acct.values():
            if sg:
                known.add(sg)
                known.add(salesman_key(sg))
    return known


def _sales_group_needs_lookup(fact: InvoiceChargeFact, known: set[str]) -> bool:
    sg = (fact.sales_group or "").strip()
    if not sg or _is_numeric_sales_group(sg):
        return True
    return sg not in known and salesman_key(sg) not in known


def fill_invoiced_sales_group(
    facts: list[InvoiceChargeFact],
    customers_by_acct: dict[str, str],
    salesmen: dict[str, SalesmanFact],
) -> list[InvoiceChargeFact]:
    """Keep a real SalesGroup from the invoiced SP; otherwise use the customer dropdown."""
    known = _known_salesman_labels(salesmen, customers_by_acct)
    out: list[InvoiceChargeFact] = []
    for fact in facts:
        if not _sales_group_needs_lookup(fact, known):
            out.append(fact)
            continue
        cust_sg = (customers_by_acct.get(fact.customer_account) or "").strip()
        if not cust_sg:
            out.append(fact)
            continue
        sm = salesmen.get(salesman_key(cust_sg))
        name = fact.salesman_name or (sm.full_name if sm else "")
        out.append(replace(fact, sales_group=cust_sg, salesman_name=name))
    return out


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

        def _build(params: dict, visible_keys):
            # Beta hybrid source: OData via live runners when the shared map says so.
            # /test ignores the map and always uses SQL (this path is a no-op there
            # unless BETA forces the check — gated on app config at call sites).
            from flask import current_app, has_app_context

            use_odata = False
            if has_app_context():
                cfg = current_app.config.get("APP_CONFIG")
                if cfg is not None and getattr(cfg, "is_beta", False):
                    from web.beta_sources import get_source

                    # Reports not on the hybrid map (Sales by State) stay SQL.
                    use_odata = get_source(report_key) == "odata"
            if use_odata:
                from web.reporting.odata_bridge import build_odata_payload

                return build_odata_payload(report_key, params or {}, visible_keys)
            return orchestrate(self, params or {}, visible_keys)

        return _build

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

    def _customer_sales_groups(self) -> dict[str, str]:
        """{account -> SalesGroup} from the same source as the report dropdowns."""
        from flask import current_app, has_app_context

        if has_app_context():
            lookups = current_app.config.get("LOOKUP_SERVICE")
            if lookups is not None:
                mapped = lookups.customer_sales_groups()
                if mapped:
                    return mapped
        return {
            (getattr(f, "customer_account", "") or "").strip():
                (getattr(f, "sales_group", "") or "").strip()
            for f in self._customer_universe()
            if (getattr(f, "customer_account", "") or "").strip()
            and (getattr(f, "sales_group", "") or "").strip()
        }

    def _with_dropdown_salesman(
        self,
        facts: list,
        extra: list | None = None,
    ) -> tuple[dict, list, list | None]:
        salesmen = self._salesmen()
        known = _known_salesman_labels(salesmen)
        pool = list(facts)
        if extra is not None and extra is not facts:
            pool.extend(extra)
        customers_by_acct = (
            self._customer_sales_groups()
            if any(_sales_group_needs_lookup(f, known) for f in pool)
            else {}
        )
        same = extra is facts
        facts = fill_invoiced_sales_group(facts, customers_by_acct, salesmen)
        if extra is None:
            filled_extra = None
        elif same:
            filled_extra = facts
        else:
            filled_extra = fill_invoiced_sales_group(extra, customers_by_acct, salesmen)
        return salesmen, facts, filled_extra

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
            "salesline_release", {},
            src_ordered.to_facts, None,
            from_key="CreatedDateTimeFrom", to_key="CreatedDateTimeTo",
            start=D365_GO_LIVE, end=today_eastern())

    def customer_orders(self, account: str) -> list:
        """All-time OrderLineFacts for one customer (dashboard customer detail)."""
        sp = P.translate("ordered", {"period": "all_time", "customers": [account]})
        return src_ordered.to_facts(self._rows("salesline_release", sp))

    def last_order_rows(self, account: str, *, order_count: int = 10) -> list[dict]:
        """Recent logical-order lines for Customer's Last Order (ADDON rolled).

        Calls ``customer_last_orders`` for one account. The SP returns at most
        ``order_count`` logical orders (default 10) so we don't pull the whole
        history the way the old salesline_release path did.
        """
        return self._rows("customer_last_orders", P.translate(
            "customer_last_order",
            {"customer_account": account, "order_count": order_count},
        ))


# --------------------------------------------------------------------------- #
# Per-report orchestration (module-level so the closure stays thin)
# --------------------------------------------------------------------------- #

def _orch_ordered(svc: ReportService, params: dict, visible_keys) -> dict:
    report_id = P.report_id_for("ordered")  # rpt.usp_ordered_report
    base_sp = P.translate("ordered", params)
    start, end = P.resolve_window(params)
    # translate() omits dates for all_time/blank so the SP would use its own
    # (huge) default. One undated pull blows the API timeout and occupies a
    # job-worker slot until then, so later Ordered schedules fail too.
    # Dashboard all_orders() already chunks go-live..today; this report must
    # do the same. Bounded periods (daily/MTD/YTD/custom) already have dates.
    if not start or not end:
        start, end = D365_GO_LIVE, today_eastern()
    facts = svc._facts_chunked(
        report_id, base_sp, src_ordered.to_facts_ordered_report, visible_keys,
        from_key="CreatedDateTimeFrom", to_key="CreatedDateTimeTo",
        start=start, end=end)
    # The new SP's CustomerAccount is a single exact match, so a multi-customer
    # selection isn't pushed down -- post-filter it here (same as invoiced).
    accounts = _selected_accounts(params)
    if len(accounts) > 1:
        facts = [f for f in facts if f.customer_account in accounts]
    # build() consumes the facts list to keep peak memory down on big runs, so
    # capture the count first.
    row_count = len(facts)
    tabs = rpt_ordered.build(facts, skip_by_salesman=bool(_salesman_filter(params)))
    return svc._payload("ordered", tabs, row_count)


def _selected_accounts(params: dict) -> set[str]:
    """Customer accounts selected in the filter, as a set of trimmed strings."""
    c = (params or {}).get("customers")
    if isinstance(c, (list, tuple, set)):
        return {str(x).strip() for x in c if str(x).strip()}
    if c:
        return {s.strip() for s in str(c).split(",") if s.strip()}
    return set()


def _invoice_day(fact) -> date | None:
    raw = (getattr(fact, "invoice_date", None) or "")[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _salesman_filter(params: dict | None) -> list[str]:
    raw = (params or {}).get("salesman")
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def invoiced_skip_commissions(params: dict | None, layout: dict | None = None) -> bool:
    """True when output omits Commissions — fetch the selected period only.

    Matches live Shipped Reports (`--salesman` / `--salesman all`): no
    commissions tab, so no January-through-period pull. A saved layout.order
    that does not include `commissions` is the same (9am Salesmen Shipped, or
    Remove tab then Schedule).
    """
    p = params or {}
    if p.get("_skip_commissions"):
        return True
    if _salesman_filter(p):
        return True
    order = (layout or {}).get("order") if isinstance(layout, dict) else None
    if isinstance(order, list) and order:
        return "commissions" not in order
    return False


def drop_commissions_tab(payload: dict) -> dict:
    """Copy a payload without the Commissions tab (salesman viewers never see it)."""
    tabs = payload.get("tabs") or []
    kept = [t for t in tabs if t.get("key") != "commissions"]
    if len(kept) == len(tabs):
        return payload
    out = dict(payload)
    out["tabs"] = kept
    return out


def _orch_invoiced(svc: ReportService, params: dict, visible_keys) -> dict:
    """Invoiced tabs use the selected period; Commissions needs Jan 1..period end.

    When Commissions will not be in the output, skip the YTD pull and the tab.
    When the selected period already sits inside that YTD window, one SP pull
    covers both (period tabs = date filter on the YTD rows). Otherwise we keep
    the two-pull path (e.g. all_time / custom that starts before Jan 1).
    """
    report_id = P.report_id_for("invoiced")
    period_start, period_end = P.resolve_window(params)
    end = period_end or today_eastern()
    year = end.year
    ytd_start = date(year, 1, 1)
    ytd_end = end

    accounts = _selected_accounts(params)

    def _scope(facts):
        if len(accounts) > 1:
            return [f for f in facts if f.customer_account in accounts]
        return facts

    def _fetch(sp_params):
        return _scope(svc._facts(report_id, sp_params, src_invoiced.to_facts, visible_keys))

    base_sp = P.translate("invoiced", params)
    if invoiced_skip_commissions(params):
        facts = _fetch(base_sp)
        salesmen, facts, _ = svc._with_dropdown_salesman(facts)
        tabs = rpt_invoiced.build(
            facts, salesmen=salesmen, skip_commissions=True,
        )
        return svc._payload("invoiced", tabs, len(facts))

    period_inside_ytd = (
        period_start is not None
        and period_end is not None
        and period_start >= ytd_start
        and period_end <= ytd_end
    )

    if period_inside_ytd:
        ytd_sp = dict(base_sp)
        ytd_sp["InvoiceDateFrom"] = sp_datetime(ytd_start, end_of_day=False)
        ytd_sp["InvoiceDateTo"] = sp_datetime(ytd_end, end_of_day=True)
        ytd_facts = _fetch(ytd_sp)
        if period_start == ytd_start and period_end == ytd_end:
            facts = ytd_facts
        else:
            facts = [
                f for f in ytd_facts
                if (d := _invoice_day(f)) is not None and period_start <= d <= period_end
            ]
    else:
        facts = _fetch(base_sp)
        ytd_sp = dict(base_sp)
        ytd_sp["InvoiceDateFrom"] = sp_datetime(ytd_start, end_of_day=False)
        ytd_sp["InvoiceDateTo"] = sp_datetime(ytd_end, end_of_day=True)
        ytd_facts = _fetch(ytd_sp)

    salesmen, facts, ytd_facts = svc._with_dropdown_salesman(facts, ytd_facts)
    tabs = rpt_invoiced.build(
        facts, salesmen=salesmen,
        ytd_facts=ytd_facts, year=year, end_month=end.month,
    )
    return svc._payload("invoiced", tabs, len(facts))


def _orch_salesman(svc: ReportService, params: dict, visible_keys) -> dict:
    """Monthly Salesman YoY from rpt.usp_monthly_salesman_yoy (Total Invoice)."""
    sp = P.translate("salesman", params)
    fetched = svc.client.run_report(P.report_id_for("salesman"), sp)
    rows = rpt_salesman.filter_rows_by_salesman(
        rpt_salesman.clean_rows(fetched.rows), visible_keys)
    tabs = rpt_salesman.build(rows, year=_resolved_year(params))
    return svc._payload("salesman", tabs, len(rows))


def _orch_number_4(svc: ReportService, params: dict, visible_keys) -> dict:
    """Number 4 = rolling-12 pivots from the SPs, plus a YTD slice of each.

    The mode filter decides which view(s) to fetch: By Customer, By Item, or
    Both (two SP calls). Each view becomes two tabs (12 months and YTD). The
    SPs do the rolling-12 math; YTD is the current-year months of that pivot.
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


def _orch_item_averages(svc: ReportService, params: dict, visible_keys) -> dict:
    """Company-wide item qty averages from the Number 4 By Item SP.

    Privileged-only at the auth layer; this path ignores salesman scope and
    always rolls up the full company result.
    """
    fetched = svc.client.run_report(
        rpt_item_averages.SP_NAME, P.translate("item_averages", params))
    tabs = rpt_item_averages.build(fetched.rows)
    return svc._payload("item_averages", tabs, len(tabs[0]["rows"]) if tabs else 0)


def _orch_customer_activity(svc: ReportService, params: dict, visible_keys) -> dict:
    # Dedicated SP returns one row per customer (Salesman + last-order fields).
    # Builder fans out into All + per-salesman + Unassigned tabs.
    fetched = svc.client.run_report(
        P.report_id_for("customer_activity"), P.translate("customer_activity", params))
    rows = rpt_customer_activity.filter_rows_by_salesman(
        rpt_customer_activity.clean_rows(fetched.rows), visible_keys)
    return svc._payload("customer_activity", rpt_customer_activity.build(rows), len(rows))


def _orch_sales_by_state(svc: ReportService, params: dict, visible_keys) -> dict:
    """Three SQL catalog calls (summary / NYC / detail) with the same dates."""
    _ = visible_keys  # company-wide; the SPs have no salesman filter
    sp = P.translate("sales_by_state", params)
    tabs = rpt_sales_by_state.build(
        summary=svc._rows(P.SALES_BY_STATE_SUMMARY_SP, sp),
        nyc=svc._rows(P.SALES_BY_STATE_NYC_SP, sp),
        detail=svc._rows(P.SALES_BY_STATE_DETAIL_SP, sp),
    )
    return svc._payload("sales_by_state", tabs, sum(len(t["rows"]) for t in tabs))


_ORCHESTRATORS: dict[str, Callable[[ReportService, dict, set | None], dict]] = {
    "ordered": _orch_ordered,
    "invoiced": _orch_invoiced,
    "salesman": _orch_salesman,
    "number_4": _orch_number_4,
    "item_averages": _orch_item_averages,
    "customer_activity": _orch_customer_activity,
    "sales_by_state": _orch_sales_by_state,
}
