"""Invoiced report: source adapter + pure builder (math/format parity)."""

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from report_engine.reports import invoiced as B
from report_engine.sources import invoiced as S


def _sm(key, number, full_name, pct, display=""):
    return SalesmanFact(source="reporting_api", key=key, number=number,
                        full_name=full_name, display_name=display, commission_pct=pct)


def _salesmen():
    return {salesman_key("REdwards"): _sm("redwards", "10", "Robert Edwards", 0.05)}


def _tabs_by_key(tabs):
    return {t["key"]: t for t in tabs}


# --- source adapter --------------------------------------------------------

def test_adapter_prefers_line_level_tariff_and_computes_total():
    fact = S.to_fact({
        "Invoice": "INV1", "InvoiceAccount": "100", "CustomerName": "Acme",
        "InvoiceDate": "2026-04-30T00:00:00", "SalesOrder": "SO1",
        "Amount": "100", "SL_TariffCharges": "7", "SH_TariffCharges": None,
        "SH_FreightCharges": "3", "SH_ProcessingFeesCharges": "2",
        "SalesGroup": "REdwards",
    })
    assert fact.tariff == 7.0          # SL wins over null SH
    assert fact.freight == 3.0 and fact.cc == 2.0
    assert fact.total == 112.0
    assert fact.invoice_date == "2026-04-30"
    assert fact.is_credit is False


def test_adapter_parses_rfc1123_date_without_truncation():
    fact = S.to_fact({"Invoice": "INV2", "InvoiceDate": "Thu, 30 Apr 2026 00:00:00 GMT",
                      "Amount": "10"})
    assert fact.invoice_date == "2026-04-30"


def test_adapter_detects_credits_as_substring_case_insensitive():
    # LIVE uses InvoiceNumber.upper().contains("CRD|CM|FC") - substring, not prefix.
    for n in ("CRD100", "CM5", "FC9", "cm-1", "X-CRD-9", "INVCM7"):
        assert S.to_fact({"Invoice": n, "Amount": "-5"}).is_credit is True
    assert S.to_fact({"Invoice": "INV9", "Amount": "5"}).is_credit is False


def test_adapter_falls_back_to_sh_tariff_when_sl_missing():
    fact = S.to_fact({"Invoice": "INV1", "Amount": "100", "SH_TariffCharges": "9"})
    assert fact.tariff == 9.0


# --- builder ---------------------------------------------------------------

def _basic_facts():
    return S.to_facts([
        {"Invoice": "INV1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-04-10", "Amount": "100", "SL_TariffCharges": "10",
         "SH_FreightCharges": "5", "SH_ProcessingFeesCharges": "2", "SalesGroup": "REdwards"},
        {"Invoice": "INV2", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-04-12", "Amount": "50", "SalesGroup": "REdwards"},
        {"Invoice": "CRD1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-04-15", "Amount": "-20", "SalesGroup": "REdwards"},
    ])


def test_build_tab_order_and_presence():
    tabs = B.build(_basic_facts(), salesmen=_salesmen())
    keys = [t["key"] for t in tabs]
    assert keys[:5] == ["summary_by_customer", "commissions", "full_data", "credits", "invoices"]


def test_credits_and_invoices_split():
    tabs = _tabs_by_key(B.build(_basic_facts(), salesmen=_salesmen()))
    assert {r["InvoiceNumber"] for r in tabs["credits"]["rows"]} == {"CRD1"}
    assert {r["InvoiceNumber"] for r in tabs["invoices"]["rows"]} == {"INV1", "INV2"}


def test_summary_aggregates_per_customer_salesman():
    tabs = _tabs_by_key(B.build(_basic_facts(), salesmen=_salesmen()))
    rows = tabs["summary_by_customer"]["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["InvoiceCount"] == 3
    assert row["SubTotal Invoices"] == 130.0          # 100 + 50 + (-20)
    assert row["Total Tariff Charges"] == 10.0
    assert row["Total Invoices"] == 100 + 10 + 5 + 2 + 50 + (-20)  # 147
    assert row["SalesmanNumber"] == "10"


def test_full_details_nets_reversal_pairs():
    facts = S.to_facts([
        {"Invoice": "INV5", "InvoiceAccount": "1", "Amount": "100", "InvoiceDate": "2026-04-01"},
        {"Invoice": "INV5", "InvoiceAccount": "1", "Amount": "-100", "InvoiceDate": "2026-04-02"},
    ])
    tabs = _tabs_by_key(B.build(facts, salesmen={}))
    full = tabs["full_data"]["rows"]
    assert len(full) == 1
    assert full[0]["Total Invoice"] == 0.0
    # Both positive & negative -> reversal audit tab present.
    assert "audit_reversals" in tabs


def test_totals_by_salesman_only_when_multiple():
    one = B.build(_basic_facts(), salesmen=_salesmen())
    assert "totals_by_salesman" not in _tabs_by_key(one)

    facts = S.to_facts([
        {"Invoice": "A1", "InvoiceAccount": "1", "Amount": "100", "SalesGroup": "REdwards",
         "InvoiceDate": "2026-04-01"},
        {"Invoice": "B1", "InvoiceAccount": "2", "Amount": "200", "SalesGroup": "JDoe",
         "InvoiceDate": "2026-04-01"},
    ])
    salesmen = _salesmen()
    salesmen[salesman_key("JDoe")] = _sm("jdoe", "11", "Jane Doe", 0.04)
    tabs = _tabs_by_key(B.build(facts, salesmen=salesmen))
    assert "totals_by_salesman" in tabs
    assert len(tabs["totals_by_salesman"]["rows"]) == 2


def test_totals_by_salesman_excludes_credits():
    # LIVE builds Totals by Salesman from the non-credit invoices view.
    facts = S.to_facts([
        {"Invoice": "A1", "InvoiceAccount": "1", "Amount": "100", "SalesGroup": "REdwards",
         "InvoiceDate": "2026-04-01"},
        {"Invoice": "B1", "InvoiceAccount": "2", "Amount": "200", "SalesGroup": "JDoe",
         "InvoiceDate": "2026-04-01"},
        {"Invoice": "CRD9", "InvoiceAccount": "1", "Amount": "-50", "SalesGroup": "REdwards",
         "InvoiceDate": "2026-04-02"},
    ])
    salesmen = _salesmen()
    salesmen[salesman_key("JDoe")] = _sm("jdoe", "11", "Jane Doe", 0.04)
    totals = _tabs_by_key(B.build(facts, salesmen=salesmen))["totals_by_salesman"]["rows"]
    redwards = next(r for r in totals if r["SalesmanNumber"] == "10")
    assert redwards["Total Invoice"] == 100.0   # credit -50 excluded
    assert redwards["InvoiceCount"] == 1


def test_commissions_pivot_ignores_prior_year_rows():
    facts = S.to_facts([
        {"Invoice": "INV1", "InvoiceAccount": "1", "InvoiceDate": "2026-04-10",
         "Amount": "1000", "SalesGroup": "REdwards"},
        {"Invoice": "INV0", "InvoiceAccount": "1", "InvoiceDate": "2025-04-10",
         "Amount": "9999", "SalesGroup": "REdwards"},  # prior year - must be ignored
    ])
    comm = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["ytd"]["subtotal_invoices"] == 1000.0


def test_unresolved_nonempty_salesgroup_keeps_code():
    facts = S.to_facts([{"Invoice": "X", "InvoiceAccount": "1", "Amount": "5",
                         "SalesGroup": "ZZTOP"}])
    row = _tabs_by_key(B.build(facts, salesmen={}))["invoices"]["rows"][0]
    assert row["Salesman"] == "ZZTOP"        # raw code, not "Unassigned"
    assert row["SalesmanNumber"] == ""
    assert row["SalesmanName"] == ""


def test_commissions_monthly_pivot_math():
    facts = S.to_facts([
        {"Invoice": "INV1", "InvoiceAccount": "1", "InvoiceDate": "2026-04-10",
         "Amount": "1000", "SL_TariffCharges": "100", "SH_FreightCharges": "50",
         "SH_ProcessingFeesCharges": "25", "SalesGroup": "REdwards"},
        {"Invoice": "CRD1", "InvoiceAccount": "1", "InvoiceDate": "2026-04-20",
         "Amount": "-200", "SalesGroup": "REdwards"},
    ])
    tabs = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))
    comm = tabs["commissions"]
    assert comm["layout"] == "commission_cards"
    sm = comm["salesmen"][0]
    apr = sm["monthly"][3]
    assert apr["total_invoices"] == 1175.0          # 1000+100+50+25
    # net = total_invoices + credits - freight - cc = 1175 + (-200) - 50 - 25
    assert apr["net_commission"] == 900.0
    assert apr["commission"] == 45.0                # 900 * 0.05
    assert sm["ytd"]["total_payable"] == 45.0


def test_commissions_simple_fallback_without_ytd():
    tabs = _tabs_by_key(B.build(_basic_facts(), salesmen=_salesmen()))
    comm = tabs["commissions"]
    assert comm.get("layout") != "commission_cards"
    assert comm["columns"] == B.COMMISSION_COLS


def test_unresolved_salesman_is_unassigned():
    facts = S.to_facts([{"Invoice": "X", "InvoiceAccount": "1", "Amount": "5"}])
    rows = _tabs_by_key(B.build(facts, salesmen={}))["invoices"]["rows"]
    assert rows[0]["Salesman"] == "Unassigned"
    assert rows[0]["SalesmanNumber"] == "?unassigned"
