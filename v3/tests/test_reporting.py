"""Reporting infra: API client, scope-safe cache, runner, export."""

import io

import pytest

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.jobs import JobRepository
from web.jobs.worker import JobWorker
from web.reporting.cache import (
    SCOPE_ALL,
    SCOPE_NONE,
    ReportCache,
    build_cache_key,
    canonical_scope_token,
)
from web.reporting.export import payload_to_xlsx
from web.reporting.http_client import (
    ReportingApiClient,
    ReportingApiError,
    ReportingApiNotConfigured,
)
from web.reporting.jobs import enqueue_report_run, make_report_run_handler
from web.reporting.runner import ReportRunner


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


# --- HTTP client ------------------------------------------------------------

class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _FakeSession:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, 0

    def post(self, url, *, json, headers, timeout):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.resp


def test_client_not_configured_raises():
    with pytest.raises(ReportingApiNotConfigured):
        ReportingApiClient("", "").run_report("ordered", {})


def test_client_parses_rows():
    sess = _FakeSession(_FakeResp(200, {"rows": [{"A": 1}], "row_count": 1, "columns": ["A"]}))
    client = ReportingApiClient("http://api", "k", session=sess)
    res = client.run_report("salesline_release", {"From": "2026-01-01"})
    assert res.row_count == 1 and res.rows == [{"A": 1}] and res.columns == ["A"]


def test_client_4xx_raises_without_retry():
    sess = _FakeSession(_FakeResp(400, {}))
    client = ReportingApiClient("http://api", "k", retries=3, session=sess)
    with pytest.raises(ReportingApiError):
        client.run_report("x", {})
    assert sess.calls == 1  # client error is not retried


def test_client_5xx_is_retried():
    sess = _FakeSession(_FakeResp(503, {}))
    client = ReportingApiClient("http://api", "k", retries=2, session=sess)
    with pytest.raises(ReportingApiError):
        client.run_report("x", {})
    assert sess.calls == 3  # transient server error retried (initial + 2)


def test_client_retries_network_then_fails():
    sess = _FakeSession(exc=ConnectionError("down"))
    client = ReportingApiClient("http://api", "k", retries=2, session=sess)
    with pytest.raises(ReportingApiError):
        client.run_report("x", {})
    assert sess.calls == 3  # initial + 2 retries


def test_client_tolerates_non_list_rows():
    sess = _FakeSession(_FakeResp(200, {"rows": None}))
    client = ReportingApiClient("http://api", "k", session=sess)
    assert client.run_report("x", {}).rows == []


# --- canonical scope token --------------------------------------------------

def test_canonical_scope_token_is_order_stable():
    assert canonical_scope_token({"b", "a"}) == canonical_scope_token({"a", "b"}) == "a,b"


def test_canonical_scope_token_reserved_values():
    assert canonical_scope_token(None) == SCOPE_ALL       # privileged
    assert canonical_scope_token(set()) == SCOPE_NONE      # known user, no keys
    assert canonical_scope_token(["", "  "]) == SCOPE_NONE  # blanks ignored


def test_build_cache_key_rejects_empty_scope():
    with pytest.raises(ValueError):
        build_cache_key(report_key="ordered", identity="u", scope_token="",
                        builder_version=1, params={})


# --- cache key scope safety -------------------------------------------------

def test_cache_key_isolates_scope():
    base = dict(report_key="ordered", builder_version=1, params={"from": "2026-01-01"})
    admin = build_cache_key(identity="shared", scope_token="ALL", **base)
    sm_a = build_cache_key(identity="shared", scope_token="mkolko", **base)
    sm_b = build_cache_key(identity="shared", scope_token="hkaufman", **base)
    assert admin != sm_a != sm_b and admin != sm_b  # every scope -> distinct key


def test_cache_key_changes_with_every_component():
    k = lambda **o: build_cache_key(report_key="ordered", identity="u", scope_token="ALL",
                                    builder_version=1, params={"a": 1}, **o)
    baseline = k()
    assert baseline != build_cache_key(report_key="invoiced", identity="u", scope_token="ALL",
                                       builder_version=1, params={"a": 1})
    assert baseline != build_cache_key(report_key="ordered", identity="u", scope_token="ALL",
                                       builder_version=2, params={"a": 1})
    assert baseline != build_cache_key(report_key="ordered", identity="u", scope_token="ALL",
                                       builder_version=1, params={"a": 2})


def test_cache_round_trip_and_isolation(db):
    cache = ReportCache(db)
    key_a = build_cache_key(report_key="ordered", identity="x", scope_token="mkolko",
                            builder_version=1, params={})
    key_b = build_cache_key(report_key="ordered", identity="x", scope_token="hkaufman",
                            builder_version=1, params={})
    cache.put(key_a, "ordered", {"tabs": [{"name": "T", "rows": [{"v": "A-only"}]}]})
    assert cache.get(key_b) is None  # other scope cannot read A's payload
    assert cache.get(key_a).payload["tabs"][0]["rows"][0]["v"] == "A-only"


# --- runner -----------------------------------------------------------------

def test_runner_caches_then_serves_from_cache(db):
    runner = ReportRunner(ReportCache(db))
    calls = {"n": 0}

    def builder(params, visible_keys):
        calls["n"] += 1
        return {"tabs": [{"name": "T", "rows": [{"x": params["x"]}]}]}

    args = dict(report_key="ordered", identity="u", visible_salesman_keys=None,
                builder_version=1, params={"x": 1}, builder=builder)
    first = runner.run(**args)
    second = runner.run(**args)
    assert first.from_cache is False and second.from_cache is True
    assert calls["n"] == 1  # builder ran once


def test_runner_scope_isolates_cache(db):
    """Two scoped users with the same params never share a cached payload."""
    runner = ReportRunner(ReportCache(db))

    def builder_a(params, visible_keys):
        return {"tabs": [{"name": "T", "rows": [{"who": "a"}]}]}

    def builder_b(params, visible_keys):
        return {"tabs": [{"name": "T", "rows": [{"who": "b"}]}]}

    out_a = runner.run(report_key="ordered", identity="shared", visible_salesman_keys={"mkolko"},
                       builder_version=1, params={"x": 1}, builder=builder_a)
    out_b = runner.run(report_key="ordered", identity="shared", visible_salesman_keys={"hkaufman"},
                       builder_version=1, params={"x": 1}, builder=builder_b)
    assert out_a.cache_key != out_b.cache_key
    assert out_b.from_cache is False  # did not read user A's cache


def test_runner_force_refresh_rebuilds(db):
    runner = ReportRunner(ReportCache(db))
    calls = {"n": 0}

    def builder(params, visible_keys):
        calls["n"] += 1
        return {"tabs": []}

    args = dict(report_key="ordered", identity="u", visible_salesman_keys=None,
                builder_version=1, params={}, builder=builder)
    runner.run(**args)
    runner.run(**args, force_refresh=True)
    assert calls["n"] == 2


def test_runner_rejects_non_dict_payload(db):
    runner = ReportRunner(ReportCache(db))
    with pytest.raises(TypeError):
        runner.run(report_key="ordered", identity="u", visible_salesman_keys=None,
                   builder_version=1, params={}, builder=lambda p, v: ["not", "a", "dict"])


def test_cache_prune_removes_old_rows(db):
    cache = ReportCache(db)
    key = build_cache_key(report_key="ordered", identity="u", scope_token="ALL",
                          builder_version=1, params={})
    cache.put(key, "ordered", {"tabs": []})
    assert cache.prune(older_than_seconds=-1) == 1  # cutoff in the future -> prunes all
    assert cache.get(key) is None


def test_cache_self_heals_when_cache_db_wiped_mid_flight(db, tmp_path):
    """Regression (2026-06-11): cache.db was deleted while the app was running;
    the fresh file had no schema and a finished report run died at the save step
    with 'no such table: report_payload_cache'. put/get/exists must re-create
    the schema and carry on instead of failing the run."""
    cache = ReportCache(db)
    key = build_cache_key(report_key="ordered", identity="u", scope_token="ALL",
                          builder_version=1, params={})

    # Simulate the wipe: replace cache.db with a brand-new, schema-less file.
    db.cache_path.unlink()
    db.cache_path.touch()

    cache.put(key, "ordered", {"tabs": [{"name": "T", "rows": [{"v": 1}]}]})
    assert cache.get(key).payload["tabs"][0]["rows"] == [{"v": 1}]

    db.cache_path.unlink()
    assert cache.get(key) is None       # heals on read too, returns a clean miss
    assert cache.exists(key) is False


def test_cache_quarantines_corrupt_json(db):
    cache = ReportCache(db)
    key = "deadbeef"
    with db.cache() as conn:
        conn.execute(
            "INSERT INTO report_payload_cache(cache_key, report_key, payload_json, built_at)"
            " VALUES (?, 'ordered', '{not json', datetime('now'))",
            (key,),
        )
    assert cache.get(key) is None  # corrupt -> miss
    with db.cache() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM report_payload_cache WHERE cache_key=?", (key,)
        ).fetchone()[0] == 0  # and the bad row is deleted


# --- durable report.run wiring (rule 7) -------------------------------------

def test_report_run_enqueues_and_worker_populates_cache(db):
    runner = ReportRunner(ReportCache(db))
    job_repo = JobRepository(db)
    worker = JobWorker(db)
    worker.register("report.run", make_report_run_handler(
        runner, builder_resolver=lambda key: (lambda params, vk: {"tabs": [{"name": key, "rows": []}]})
    ))

    jid = enqueue_report_run(
        job_repo, report_key="ordered", identity="u", visible_salesman_keys={"mkolko"},
        builder_version=1, params={"from": "2026-01-01"},
    )
    # Same request collapses to one job (dedup).
    jid2 = enqueue_report_run(
        job_repo, report_key="ordered", identity="u", visible_salesman_keys={"mkolko"},
        builder_version=1, params={"from": "2026-01-01"},
    )
    assert jid == jid2

    worker.process_next()
    done = job_repo.get(jid)
    assert done.status == "success"
    # result_ref is the cache key; the payload is now cached and readable.
    assert ReportCache(db).get(done.result_ref).payload["tabs"][0]["name"] == "ordered"


# --- export -----------------------------------------------------------------

def test_export_produces_valid_xlsx():
    openpyxl = pytest.importorskip("openpyxl")
    payload = {"tabs": [
        {"name": "Summary", "columns": ["Customer", "Total"], "rows": [{"Customer": "ACME", "Total": 10}]},
        {"name": "Detail/Bad:Name*", "columns": ["X"], "rows": [{"X": 1}, {"X": 2}]},
    ]}
    data = payload_to_xlsx(payload)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert "Summary" in wb.sheetnames
    # Invalid sheet chars are sanitized.
    assert all(not set(name) & set(":\\/?*[]") for name in wb.sheetnames)
    ws = wb["Summary"]
    assert [c.value for c in ws[1]] == ["Customer", "Total"]
    assert ws[2][0].value == "ACME"


def test_export_neutralizes_formula_injection():
    openpyxl = pytest.importorskip("openpyxl")
    payload = {"tabs": [{"name": "T", "columns": ["X"], "rows": [
        {"X": "=cmd|'/c calc'!A1"}, {"X": "+1+1"}, {"X": "-2"}, {"X": "@SUM(1)"}, {"X": "safe"},
    ]}]}
    wb = openpyxl.load_workbook(io.BytesIO(payload_to_xlsx(payload)))
    ws = wb["T"]
    assert ws[2][0].value.startswith("'=")   # leading apostrophe forces literal text
    assert ws[3][0].value.startswith("'+")
    assert ws[4][0].value.startswith("'-")
    assert ws[5][0].value.startswith("'@")
    assert ws[6][0].value == "safe"          # ordinary text untouched


def test_export_styles_header_and_money_format():
    openpyxl = pytest.importorskip("openpyxl")
    payload = {"tabs": [{"name": "S", "columns": [
        {"field": "Cust", "header": "Cust", "type": "text"},
        {"field": "Amt", "header": "Amt", "type": "money"},
    ], "rows": [{"Cust": "ACME", "Amt": 12.5}]}]}
    wb = openpyxl.load_workbook(io.BytesIO(payload_to_xlsx(payload)))
    ws = wb["S"]
    header = ws["A1"]
    assert header.font.bold is True
    assert str(header.fill.fgColor.rgb).endswith("E0E0E0")   # live grey header
    assert ws["B2"].value == 12.5                            # money stored as number
    assert "$" in ws["B2"].number_format


def test_export_grouped_adds_subtotals_and_grand_total():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "Cust", "header": "Cust", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [{"Cust": "A", "Amt": 10}, {"Cust": "A", "Amt": 5}, {"Cust": "B", "Amt": 7}],
    }]}
    layout = {"views": {"t": {"group": ["Cust"]}}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    ws = wb["T"]
    col_a = [c.value for c in ws["A"]]
    assert any(str(v).startswith("Cust: A") for v in col_a)        # group banner
    assert any(str(v).startswith("Total \u2014 A") for v in col_a)  # per-group subtotal
    assert "Grand total" in col_a
    grand = next(row for row in ws.iter_rows() if row[0].value == "Grand total")
    assert grand[1].value == 22                                     # 10 + 5 + 7


def test_export_nested_groups_subtotals_each_level():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "CustomerName", "header": "CustomerName", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [
            {"Salesman": "A", "CustomerName": "Zed", "Amt": 1},
            {"Salesman": "A", "CustomerName": "Zed", "Amt": 2},
            {"Salesman": "A", "CustomerName": "Ann", "Amt": 3},
            {"Salesman": "B", "CustomerName": "Zed", "Amt": 4},
        ],
    }]}
    layout = {"views": {"t": {"group": ["Salesman", "CustomerName"]}}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    col_a = [c.value for c in wb["T"]["A"]]
    assert col_a.index("Salesman: A") < col_a.index("CustomerName: Ann")
    assert col_a.index("CustomerName: Ann") < col_a.index("Total \u2014 Ann")
    assert col_a.index("Total \u2014 Ann") < col_a.index("CustomerName: Zed")
    assert col_a.index("Total \u2014 Zed") < col_a.index("Total \u2014 A")
    assert col_a.index("Total \u2014 A") < col_a.index("Salesman: B")
    assert "Grand total" in col_a
    ann = next(row for row in wb["T"].iter_rows() if row[0].value == "Total \u2014 Ann")
    assert ann[2].value == 3
    salesman_a = next(row for row in wb["T"].iter_rows() if row[0].value == "Total \u2014 A")
    assert salesman_a[2].value == 6
    grand = next(row for row in wb["T"].iter_rows() if row[0].value == "Grand total")
    assert grand[2].value == 10


def test_export_sorts_then_groups_without_customer_totals():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "CustomerName", "header": "CustomerName", "type": "text"},
            {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [
            {"CustomerName": "Beta", "SalesOrderNumber": "SO2", "Amt": 1},
            {"CustomerName": "Acme", "SalesOrderNumber": "SO9", "Amt": 2},
            {"CustomerName": "Acme", "SalesOrderNumber": "SO1", "Amt": 3},
            {"CustomerName": "Acme", "SalesOrderNumber": "SO1", "Amt": 4},
        ],
    }]}
    layout = {"views": {"t": {
        "group": ["SalesOrderNumber"],
        "sorters": [
            {"column": "CustomerName", "dir": "asc"},
            {"column": "SalesOrderNumber", "dir": "asc"},
        ],
    }}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    col_a = [str(c.value) for c in wb["T"]["A"]]
    assert not any(v.startswith("CustomerName:") for v in col_a)
    so1 = col_a.index("SalesOrderNumber: SO1")
    so9 = col_a.index("SalesOrderNumber: SO9")
    so2 = col_a.index("SalesOrderNumber: SO2")
    assert so1 < so9 < so2
    order_total = next(row for row in wb["T"].iter_rows()
                       if row[0].value == "Total \u2014 SO1")
    assert order_total[2].value == 7


def test_export_percent_columns_not_summed_in_totals():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "Cust", "header": "Cust", "type": "text"},
            {"field": "Rate", "header": "Rate", "type": "percent"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [{"Cust": "A", "Rate": 0.5, "Amt": 10}, {"Cust": "A", "Rate": 0.5, "Amt": 5}],
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, {"views": {"t": {"group": ["Cust"]}}})))
    ws = wb["T"]
    sub = next(row for row in ws.iter_rows() if str(row[0].value).startswith("Total \u2014"))
    assert sub[1].value in (None, "")   # percent col not summed (would be 1.0/100%)
    assert sub[2].value == 15           # money still summed


def test_export_group_by_hidden_column_still_groups():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    from web.delivery.layout import apply_layout
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "Cust", "header": "Cust", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [{"Cust": "A", "Amt": 10}, {"Cust": "B", "Amt": 7}],
    }]}
    layout = {"views": {"t": {"hidden": ["Cust"], "group": ["Cust"]}}}
    shaped = apply_layout(payload, layout)           # drops the Cust column
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(shaped, layout)))
    col_a = [c.value for c in wb["T"]["A"]]
    assert any(str(v).startswith("Cust: A") for v in col_a)   # still grouped by hidden col


def test_export_empty_saved_group_does_not_use_default_group():
    """Number 4 Default ungroup used to fall back to Item # in the emailed file."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "by_customer", "name": "T",
        "default_group": ["Item #"],
        "columns": [
            {"field": "Item #", "header": "Item #", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [
            {"Item #": "A", "Amt": 10}, {"Item #": "A", "Amt": 5},
            {"Item #": "B", "Amt": 7},
        ],
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(
        build_workbook(payload, {"views": {"by_customer": {"group": []}}})))
    col_a = [c.value for c in wb["T"]["A"]]
    assert not any(str(v).startswith("Item #:") for v in col_a)
    assert "Grand total" not in col_a


def test_export_missing_group_still_uses_default_group():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "default_group": ["Item #"],
        "columns": [
            {"field": "Item #", "header": "Item #", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [{"Item #": "A", "Amt": 10}, {"Item #": "B", "Amt": 7}],
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(
        build_workbook(payload, {"views": {"t": {"hidden": []}}})))
    col_a = [c.value for c in wb["T"]["A"]]
    assert any(str(v).startswith("Item #: A") for v in col_a)


def test_export_fulfillment_percent_is_heatmap_filled():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "full_data", "name": "Full Data",
        "columns": [
            {"field": "Item#", "header": "Item#", "type": "text"},
            {"field": "Fulfillment %", "header": "Fulfillment %", "type": "percent"},
        ],
        "rows": [{"Item#": "A", "Fulfillment %": 1.0}, {"Item#": "B", "Fulfillment %": 0.0}],
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, None)))
    ws = wb["Full Data"]
    green = ws["B2"].fill.fgColor.rgb
    red = ws["B3"].fill.fgColor.rgb
    assert "C6EFCE" in green.upper() or "C6EFCE" in str(green).upper()
    assert "FFC7CE" in red.upper() or "FFC7CE" in str(red).upper()
