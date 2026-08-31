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

def test_adapter_uses_sql_totals_when_present():
    fact = S.to_fact({
        "InvoiceNumber": "INV1", "CustomerAccount": "100", "CustomerName": "Acme",
        "InvoiceDate": "2026-04-30T00:00:00", "salesorder": "SO1",
        "amount": "100", "Tariff Charges": "7",
        "Freight Charges": "3", "CC Charges": "2",
        "Misc Charges": "1",
        "Total Invoice": "113",
        "salesman": "REdwards",
    })
    assert fact.tariff == 7.0
    assert fact.freight == 3.0 and fact.cc == 2.0 and fact.misc == 1.0
    assert fact.total == 113.0          # trusts SQL, does not re-sum
    assert fact.invoice_date == "2026-04-30"
    assert fact.is_credit is False


def test_adapter_sums_total_only_when_sql_omits_it():
    fact = S.to_fact({
        "InvoiceNumber": "INV1", "amount": "100",
        "Tariff Charges": "7", "Freight Charges": "3", "CC Charges": "2", "Misc Charges": "1",
    })
    assert fact.total == 113.0


def test_adapter_parses_rfc1123_date_without_truncation():
    fact = S.to_fact({"InvoiceNumber": "INV2", "InvoiceDate": "Thu, 30 Apr 2026 00:00:00 GMT",
                      "amount": "10"})
    assert fact.invoice_date == "2026-04-30"


def test_adapter_detects_credits_from_is_credit_flag():
    assert S.to_fact({"InvoiceNumber": "INV9", "IsCredit": True}).is_credit is True
    assert S.to_fact({"InvoiceNumber": "INV9", "IsCredit": "false"}).is_credit is False


def test_adapter_detects_credits_as_substring_case_insensitive():
    # LIVE uses InvoiceNumber.upper().contains("CRD|CM|FC") - substring, not prefix.
    for n in ("CRD100", "CM5", "FC9", "cm-1", "X-CRD-9", "INVCM7"):
        assert S.to_fact({"InvoiceNumber": n, "amount": "-5"}).is_credit is True
    assert S.to_fact({"InvoiceNumber": "INV9", "amount": "5"}).is_credit is False


def test_adapter_keeps_numeric_salesman_from_the_endpoint():
    fact = S.to_fact({
        "InvoiceNumber": "INV1",
        "salesman": "029",
        "SalesmanName": "Reggie Edwards",
        "amount": "10",
    })
    assert fact.sales_group == "029"
    assert fact.salesman_name == "Reggie Edwards"


def test_adapter_prefers_salesgroup_over_numeric_salesman():
    fact = S.to_fact({
        "InvoiceNumber": "INV1",
        "salesman": "029",
        "SalesGroup": "REdwards",
        "SalesmanName": "Herschel Kaufman",
        "amount": "10",
    })
    assert fact.sales_group == "REdwards"
    fact = S.to_fact({
        "InvoiceNumber": "INV1", "salesman": "REdwards",
        "SalesmanName": "Robert Edwards", "amount": "10",
    })
    assert fact.salesman_name == "Robert Edwards"


def test_adapter_accepts_new_invoiced_report_field_names():
    fact = S.to_fact({
        "InvoiceNumber": "INV9",
        "CustomerAccount": "C100",
        "CustomerName": "Acme",
        "InvoiceDate": "2026-04-30",
        "salesorder": "SO-9",
        "salesman": "REdwards",
        "amount": "90",
        "Tariff Charges": "5",
        "Freight Charges": "3",
        "CC Charges": "2",
        "Misc Charges": "1",
        "Total Invoice": "101",
    })
    assert fact.invoice_number == "INV9"
    assert fact.customer_account == "C100"
    assert fact.sales_order_number == "SO-9"
    assert fact.sales_group == "REdwards"
    assert fact.subtotal == 90.0
    assert fact.total == 101.0


# --- builder ---------------------------------------------------------------

def _basic_facts():
    return S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-04-10", "amount": "100", "Tariff Charges": "10",
         "Freight Charges": "5", "CC Charges": "2", "salesman": "REdwards",
         "Total Invoice": "117", "commission": "0.05"},
        {"InvoiceNumber": "INV2", "CustomerAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-04-12", "amount": "50", "salesman": "REdwards",
         "Total Invoice": "50", "commission": "0.05"},
        {"InvoiceNumber": "CRD1", "CustomerAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-04-15", "amount": "-20", "salesman": "REdwards",
         "Total Invoice": "-20", "commission": "0.05"},
    ])


def test_build_tab_order_and_presence():
    tabs = B.build(_basic_facts(), salesmen=_salesmen())
    keys = [t["key"] for t in tabs]
    assert keys[:5] == ["summary_by_customer", "commissions", "full_data", "credits", "invoices"]


def test_build_skip_commissions_omits_that_tab():
    keys = [t["key"] for t in B.build(_basic_facts(), salesmen=_salesmen(), skip_commissions=True)]
    assert "commissions" not in keys
    assert keys[:4] == ["summary_by_customer", "full_data", "credits", "invoices"]


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
    assert row["Salesman"] == "REdwards"
    assert row["SalesmanName"] == "Robert Edwards"


def test_full_details_skips_netting_when_one_row_per_invoice():
    facts = S.to_facts([
        {"InvoiceNumber": "INV5", "CustomerAccount": "1", "amount": "100",
         "InvoiceDate": "2026-04-01", "Total Invoice": "100"},
    ])
    full = _tabs_by_key(B.build(facts, salesmen={}))["full_data"]["rows"]
    assert len(full) == 1
    assert full[0]["Total Invoice"] == 100.0


def test_full_details_nets_reversal_pairs():
    facts = S.to_facts([
        {"InvoiceNumber": "INV5", "CustomerAccount": "1", "amount": "100",
         "InvoiceDate": "2026-04-01", "Total Invoice": "100"},
        {"InvoiceNumber": "INV5", "CustomerAccount": "1", "amount": "-100",
         "InvoiceDate": "2026-04-02", "Total Invoice": "-100"},
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
        {"InvoiceNumber": "A1", "CustomerAccount": "1", "amount": "100", "salesman": "REdwards",
         "InvoiceDate": "2026-04-01", "Total Invoice": "100"},
        {"InvoiceNumber": "B1", "CustomerAccount": "2", "amount": "200", "salesman": "JDoe",
         "InvoiceDate": "2026-04-01", "Total Invoice": "200"},
    ])
    salesmen = _salesmen()
    salesmen[salesman_key("JDoe")] = _sm("jdoe", "11", "Jane Doe", 0.04)
    tabs = _tabs_by_key(B.build(facts, salesmen=salesmen))
    assert "totals_by_salesman" in tabs
    assert len(tabs["totals_by_salesman"]["rows"]) == 2


def test_totals_by_salesman_nets_credits():
    # Totals by Salesman are NET: credits subtract from the salesman's total.
    facts = S.to_facts([
        {"InvoiceNumber": "A1", "CustomerAccount": "1", "amount": "100", "salesman": "REdwards",
         "InvoiceDate": "2026-04-01", "Total Invoice": "100"},
        {"InvoiceNumber": "B1", "CustomerAccount": "2", "amount": "200", "salesman": "JDoe",
         "InvoiceDate": "2026-04-01", "Total Invoice": "200"},
        {"InvoiceNumber": "CRD9", "CustomerAccount": "1", "amount": "-50", "salesman": "REdwards",
         "InvoiceDate": "2026-04-02", "Total Invoice": "-50"},
    ])
    salesmen = _salesmen()
    salesmen[salesman_key("JDoe")] = _sm("jdoe", "11", "Jane Doe", 0.04)
    totals = _tabs_by_key(B.build(facts, salesmen=salesmen))["totals_by_salesman"]["rows"]
    redwards = next(r for r in totals if r["Salesman"] == "REdwards")
    assert redwards["Total Invoice"] == 50.0    # 100 invoice - 50 credit
    assert redwards["InvoiceCount"] == 2


def test_commissions_pivot_ignores_prior_year_rows():
    facts = S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "1000", "salesman": "REdwards", "Total Invoice": "1000"},
        {"InvoiceNumber": "INV0", "CustomerAccount": "1", "InvoiceDate": "2025-04-10",
         "amount": "9999", "salesman": "REdwards", "Total Invoice": "9999"},
    ])
    comm = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["ytd"]["subtotal_invoices"] == 1000.0


def test_builder_uses_sql_salesman_name():
    facts = S.to_facts([{
        "InvoiceNumber": "X", "CustomerAccount": "1", "amount": "5",
        "salesman": "REdwards", "SalesmanName": "Robert Edwards",
    }])
    row = _tabs_by_key(B.build(facts, salesmen={}))["invoices"]["rows"][0]
    assert row["Salesman"] == "REdwards"
    assert row["SalesmanName"] == "Robert Edwards"


def test_unresolved_nonempty_salesgroup_keeps_code():
    facts = S.to_facts([{"InvoiceNumber": "X", "CustomerAccount": "1", "amount": "5",
                         "salesman": "ZZTOP"}])
    row = _tabs_by_key(B.build(facts, salesmen={}))["invoices"]["rows"][0]
    assert row["Salesman"] == "ZZTOP"        # raw code, not "Unassigned"
    assert row["SalesmanName"] == ""


def test_commissions_monthly_pivot_math():
    facts = S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "1000", "Tariff Charges": "100", "Freight Charges": "50",
         "CC Charges": "25", "salesman": "REdwards", "Total Invoice": "1175",
         "commission": "0.05"},
        {"InvoiceNumber": "CRD1", "CustomerAccount": "1", "InvoiceDate": "2026-04-20",
         "amount": "-200", "salesman": "REdwards", "Total Invoice": "-200",
         "commission": "0.05"},
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
    assert sm["salesman_number"]
    assert len(sm["monthly"]) == 4  # end_month=4 → no future months
    assert sm["monthly"][-1]["month"] == 4


def test_adapter_reads_commission_rate_as_fraction():
    # A fraction passes through untouched...
    assert S.to_fact({"InvoiceNumber": "X", "amount": "1", "commission": "0.06"}).commission_pct == 0.06
    # ...a whole percent above 1 is normalized; exactly 1 is 100%.
    assert S.to_fact({"InvoiceNumber": "X", "amount": "1", "commission": "6"}).commission_pct == 0.06
    assert S.to_fact({"InvoiceNumber": "X", "amount": "1", "commission": "1"}).commission_pct == 1.0
    # Blank/zero is 0% (builder does not fall back to the salesman table for money).
    assert S.to_fact({"InvoiceNumber": "X", "amount": "1"}).commission_pct == 0.0


def test_commissions_apply_each_months_own_rate():
    # Two rates in one year must not apply the later/higher rate to earlier months.
    facts = S.to_facts([
        {"InvoiceNumber": "JAN1", "CustomerAccount": "1", "InvoiceDate": "2026-01-10",
         "amount": "1000", "salesman": "REdwards", "Total Invoice": "1000",
         "commission": "0.05"},
        {"InvoiceNumber": "APR1", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "1000", "salesman": "REdwards", "Total Invoice": "1000",
         "commission": "0.10"},
    ])
    comm = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["monthly"][0]["commission"] == 50.0   # Jan 1000 * 5%
    assert sm["monthly"][3]["commission"] == 100.0  # Apr 1000 * 10%
    assert sm["ytd"]["commission"] == 150.0
    assert sm["commission_pct"] == 0.05  # table leftover, not the last invoice


def test_zero_sp_commission_pays_zero_and_keeps_table_percent():
    facts = S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "1000", "salesman": "REdwards", "Total Invoice": "1000",
         "commission": "0"},
    ])
    comm = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["ytd"]["commission"] == 0.0
    assert sm["commission_pct"] == 0.05


def test_commission_one_means_one_hundred_percent():
    facts = S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "1000", "salesman": "REdwards", "Total Invoice": "1000",
         "commission": "1"},
    ])
    comm = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["ytd"]["commission"] == 1000.0
    assert sm["commission_pct"] == 0.05


def test_commission_card_number_uses_current_bucket():
    facts = S.to_facts([
        {"InvoiceNumber": "A", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "100", "salesman": "REdwards", "Total Invoice": "100",
         "commission": "0.05"},
        {"InvoiceNumber": "B", "CustomerAccount": "2", "InvoiceDate": "2026-04-11",
         "amount": "200", "salesman": "MKolko", "Total Invoice": "200",
         "commission": "0.03"},
    ])
    salesmen = {
        salesman_key("REdwards"): _sm("redwards", "10", "Robert Edwards", 0.05),
        salesman_key("MKolko"): _sm("mkolko", "20", "M Kolko", 0.03),
    }
    comm = _tabs_by_key(B.build(facts, salesmen=salesmen,
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    by_name = {s["salesman_name"]: s for s in comm["salesmen"]}
    assert by_name["Robert Edwards"]["salesman_number"] == "10"
    assert by_name["M Kolko"]["salesman_number"] == "20"


def test_commissions_use_sp_rate_over_master():
    # SP sends commission=0.10 in the rows; master says 0.05. The SP wins.
    facts = S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "1", "InvoiceDate": "2026-04-10",
         "amount": "1000", "salesman": "REdwards", "Total Invoice": "1000",
         "commission": "0.10"},
    ])
    comm = _tabs_by_key(B.build(facts, salesmen=_salesmen(),
                                ytd_facts=facts, year=2026, end_month=4))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["commission_pct"] == 0.05  # leftover salesman-table %
    assert sm["ytd"]["commission"] == 100.0   # 1000 net * SP 0.10


def test_commissions_use_sp_rate_without_master_entry():
    # No master at all: the SP's per-row commission still drives the math.
    facts = S.to_facts([
        {"InvoiceNumber": "INV1", "CustomerAccount": "1", "InvoiceDate": "2026-03-10",
         "amount": "2000", "salesman": "NEWREP", "Total Invoice": "2000",
         "commission": "0.04"},
    ])
    comm = _tabs_by_key(B.build(facts, salesmen={},
                                ytd_facts=facts, year=2026, end_month=3))["commissions"]
    sm = comm["salesmen"][0]
    assert sm["commission_pct"] == 0.0  # no salesman-table row
    assert sm["ytd"]["commission"] == 80.0    # 2000 net * 0.04


def test_commissions_simple_fallback_without_ytd():
    tabs = _tabs_by_key(B.build(_basic_facts(), salesmen=_salesmen()))
    comm = tabs["commissions"]
    assert comm.get("layout") != "commission_cards"
    assert comm["columns"] == B.COMMISSION_COLS


def test_unresolved_salesman_is_unassigned():
    facts = S.to_facts([{"InvoiceNumber": "X", "CustomerAccount": "1", "amount": "5"}])
    rows = _tabs_by_key(B.build(facts, salesmen={}))["invoices"]["rows"]
    assert rows[0]["Salesman"] == "Unassigned"
    assert rows[0]["SalesmanName"] == "Unassigned"
