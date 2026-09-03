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
        self.content = b""
        self.text = ""

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


def test_client_logs_call_params_and_response_sample():
    from web.jobs import trace as job_trace

    body = {
        "rows": [
            {"InvoiceDate": "2026-01-15", "CustomerAccount": "100", "Amount": "10"},
            {"InvoiceDate": "2026-02-01", "CustomerAccount": "HIDDENROW", "Amount": "99"},
        ],
        "row_count": 2,
        "columns": ["InvoiceDate", "CustomerAccount", "Amount"],
    }
    resp = _FakeResp(200, body)
    resp.content = b"x" * 50
    client = ReportingApiClient("http://api", "k", session=_FakeSession(resp))
    job_trace.bind("job1", None)
    try:
        client.run_report("invoiced_report", {"InvoiceDateFrom": "2026-01-01"})
        details = [e["detail"] for e in job_trace.snapshot() if e.get("step") == "api"]
        blob = " ".join(details)
        assert any("calling invoiced_report" in d for d in details)
        assert "InvoiceDateFrom" in blob
        assert "HTTP 200" in blob
        assert "rows=2" in blob and "len=2" in blob
        assert "bytes=50" in blob
        assert "first_row=" in blob and "CustomerAccount=100" in blob
        assert "HIDDENROW" not in blob
        assert "dates=2026-01-15..2026-02-01" in blob
    finally:
        job_trace.unbind()


def test_client_4xx_log_includes_body():
    from web.jobs import trace as job_trace

    sess = _FakeSession(_FakeResp(400, {"error": "bad filter"}))
    client = ReportingApiClient("http://api", "k", retries=3, session=sess)
    job_trace.bind("j", None)
    try:
        with pytest.raises(ReportingApiError):
            client.run_report("x", {})
        blob = " ".join(e["detail"] for e in job_trace.snapshot())
        assert "HTTP 400" in blob and "not retrying" in blob
        assert "bad filter" in blob
    finally:
        job_trace.unbind()


def test_client_stops_when_job_cancelled():
    from web.jobs import trace as job_trace
    from web.jobs.trace import JobCancelled

    class _Repo:
        def get(self, _id):
            return type("J", (), {"status": "cancelled"})()
        def append_log(self, *a, **k):
            pass

    sess = _FakeSession(_FakeResp(200, {"rows": []}))
    client = ReportingApiClient("http://api", "k", session=sess)
    job_trace.bind("j", _Repo())
    try:
        with pytest.raises(JobCancelled):
            client.run_report("x", {})
        assert sess.calls == 0
    finally:
        job_trace.unbind()


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

def test_export_logs_each_sheet():
    from web.jobs import trace as job_trace
    pytest.importorskip("openpyxl")
    payload = {"tabs": [
        {"name": "Summary", "columns": ["A"], "rows": [{"A": 1}]},
        {"name": "Detail", "columns": ["X"], "rows": [{"X": 1}, {"X": 2}]},
    ]}
    job_trace.bind("j", None)
    try:
        payload_to_xlsx(payload)
        details = [e["detail"] for e in job_trace.snapshot() if e.get("step") == "xlsx"]
        assert any("Summary" in d and "1 rows" in d for d in details)
        assert any("Detail" in d and "2 rows" in d for d in details)
    finally:
        job_trace.unbind()


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


def _cell_fill_hex(cell) -> str:
    rgb = getattr(cell.fill.fgColor, "rgb", None)
    return str(rgb)[-6:].upper() if rgb else ""


def _cell_font_hex(cell) -> str:
    color = cell.font.color
    rgb = getattr(color, "rgb", None) if color is not None else None
    return str(rgb)[-6:].upper() if rgb else ""


def test_export_does_not_sum_net_price_on_group_footers():
    """Net Price is a unit price. Totals stay blank; dollars still add up."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "Customer Name", "header": "Customer Name", "type": "text"},
            {"field": "Net Price", "header": "Net Price", "type": "money"},
            {"field": "Extended Price - Ordered", "header": "Extended Price - Ordered", "type": "money"},
        ],
        "rows": [
            {"Salesman": "A", "Customer Name": "Zed", "Net Price": 2.0, "Extended Price - Ordered": 10},
            {"Salesman": "A", "Customer Name": "Zed", "Net Price": 3.0, "Extended Price - Ordered": 6},
            {"Salesman": "A", "Customer Name": "Ann", "Net Price": 4.0, "Extended Price - Ordered": 4},
            {"Salesman": "B", "Customer Name": "Zed", "Net Price": 5.0, "Extended Price - Ordered": 5},
        ],
    }]}
    layout = {"views": {"t": {"group": ["Salesman", "Customer Name"]}}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    zed = next(row for row in wb["T"].iter_rows() if row[0].value == "Total \u2014 Zed")
    assert zed[2].value is None
    assert zed[3].value == 16
    salesman = next(row for row in wb["T"].iter_rows() if row[0].value == "Total \u2014 A")
    assert salesman[2].value is None
    assert salesman[3].value == 20
    grand = next(row for row in wb["T"].iter_rows() if row[0].value == "Grand total")
    assert grand[2].value is None
    assert grand[3].value == 25


def test_export_nested_group_shades_outer_darker():
    """Daily Ordered-style nesting: salesman darker than customer; grand darkest grey."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import (
        build_workbook, nest_header_rgb, nest_footer_rgb, _hex6, _contrast_text_hex,
    )
    payload = {"tabs": [{
        "key": "t", "name": "T",
        "columns": [
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "CustomerName", "header": "CustomerName", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [
            {"Salesman": "A", "CustomerName": "Zed", "Amt": 1},
            {"Salesman": "A", "CustomerName": "Ann", "Amt": 3},
            {"Salesman": "B", "CustomerName": "Zed", "Amt": 4},
        ],
    }]}
    layout = {"views": {"t": {"group": ["Salesman", "CustomerName"]}}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    salesman_hdr = next(row for row in wb["T"].iter_rows() if row[0].value == "Salesman: A")
    customer_hdr = next(row for row in wb["T"].iter_rows() if row[0].value == "CustomerName: Ann")
    customer_tot = next(row for row in wb["T"].iter_rows() if row[0].value == "Total \u2014 Ann")
    salesman_tot = next(row for row in wb["T"].iter_rows() if row[0].value == "Total \u2014 A")
    grand = next(row for row in wb["T"].iter_rows() if row[0].value == "Grand total")
    assert _cell_fill_hex(salesman_hdr[0]) == _hex6(nest_header_rgb(0, 2))
    assert _cell_fill_hex(customer_hdr[0]) == _hex6(nest_header_rgb(1, 2))
    assert _cell_fill_hex(salesman_tot[0]) == _hex6(nest_footer_rgb(0, 2, grand=False))
    assert _cell_fill_hex(customer_tot[0]) == _hex6(nest_footer_rgb(1, 2, grand=False))
    assert _cell_fill_hex(grand[0]) == _hex6(nest_footer_rgb(0, 2, grand=True))
    assert _cell_fill_hex(salesman_hdr[0]) != _cell_fill_hex(customer_hdr[0])
    assert _cell_fill_hex(grand[0]) != _cell_fill_hex(salesman_tot[0])
    assert _cell_fill_hex(salesman_tot[0]) != _cell_fill_hex(customer_tot[0])
    assert _cell_font_hex(salesman_hdr[0]) == _contrast_text_hex(nest_header_rgb(0, 2))
    assert _cell_font_hex(customer_hdr[0]) == _contrast_text_hex(nest_header_rgb(1, 2))
    assert _cell_font_hex(grand[0]) == _contrast_text_hex(nest_footer_rgb(0, 2, grand=True))
    assert _cell_font_hex(salesman_hdr[0]) == "FFFFFF"
    assert _cell_font_hex(grand[0]) == "FFFFFF"


def test_nest_colors_keep_readable_contrast():
    from web.reporting.export import nest_header_rgb, nest_footer_rgb, _contrast, _contrast_text_hex
    white, dark = (255, 255, 255), (30, 41, 59)
    for depth in (1, 2, 3, 4):
        for level in range(depth):
            for rgb in (
                nest_header_rgb(level, depth),
                nest_footer_rgb(level, depth, grand=False),
            ):
                text = (255, 255, 255) if _contrast_text_hex(rgb) == "FFFFFF" else dark
                assert _contrast(rgb, text) >= 4.5
        grand = nest_footer_rgb(0, depth, grand=True)
        text = (255, 255, 255) if _contrast_text_hex(grand) == "FFFFFF" else dark
        assert _contrast(grand, text) >= 4.5
        assert _contrast(grand, white) >= 4.5


def test_innermost_footer_is_clearly_grey():
    """2-level customer totals must not stretch to a near-white grey."""
    from web.reporting.export import nest_footer_rgb
    inner = nest_footer_rgb(1, 2, grand=False)
    outer = nest_footer_rgb(0, 2, grand=False)
    assert inner == (156, 163, 175)
    assert outer == (107, 114, 128)
    assert max(inner) < 200
    assert inner != outer


def test_export_grouped_sheets_have_no_outline():
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
            {"Salesman": "A", "CustomerName": "Ann", "Amt": 3},
        ],
    }]}
    layout = {"views": {"t": {"group": ["Salesman", "CustomerName"]}}}
    ws = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))["T"]
    assert int(ws.sheet_format.outlineLevelRow or 0) == 0
    for row in ws.iter_rows():
        dim = ws.row_dimensions[row[0].row]
        assert int(dim.outline_level or 0) == 0


def test_export_drops_salesman_group_when_file_is_one_rep():
    """Daily Ordered By Customer groups by salesman only. A per-rep file is
    already one salesman — no salesman banner, and no customer group either."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "by_customer", "name": "By Customer",
        "columns": [
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "CustomerName", "header": "CustomerName", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [
            {"Salesman": "Joe", "CustomerName": "Zed", "Amt": 9},
            {"Salesman": "Joe", "CustomerName": "Ann", "Amt": 1},
        ],
    }]}
    layout = {"views": {"by_customer": {
        "group": ["Salesman"],
        "sorters": [
            {"column": "Salesman", "dir": "asc"},
            {"column": "CustomerName", "dir": "asc"},
        ],
    }}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    col_a = [c.value for c in wb["By Customer"]["A"]]
    assert "Salesman: Joe" not in col_a
    assert not any(str(v).startswith("CustomerName:") for v in col_a)


def test_export_salesman_summary_uses_builder_customer_sort():
    """Per-rep Ordered Summary has no default_group; honour default_layout."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "summary", "name": "Summary",
        "columns": [
            {"field": "Customer Name", "header": "Customer Name", "type": "text"},
            {"field": "Item Number", "header": "Item Number", "type": "text"},
            {"field": "Amt", "header": "Amt", "type": "money"},
        ],
        "rows": [
            {"Customer Name": "Zed", "Item Number": "B", "Amt": 9, "Salesman": "Joe"},
            {"Customer Name": "Ann", "Item Number": "A", "Amt": 1, "Salesman": "Joe"},
        ],
        "default_group": [],
        "default_layout": {
            "group_levels": ["Customer Name"],
            "sort_levels": [
                {"field": "Customer Name", "dir": "asc"},
                {"field": "Item Number", "dir": "asc"},
            ],
        },
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, None)))
    col_a = [c.value for c in wb["Summary"]["A"]]
    assert col_a.index("Customer Name: Ann") < col_a.index("Customer Name: Zed")


def test_export_customer_sort_does_not_split_salesman_groups():
    """Daily Ordered Summary: sort customers A-Z inside each salesman, not across."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "summary", "name": "Summary",
        "columns": [
            {"field": "Customer Name", "header": "Customer Name", "type": "text"},
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "Item Number", "header": "Item Number", "type": "text"},
        ],
        "rows": [
            {"Customer Name": "ZEBRA", "Salesman": "REdwards", "Item Number": "Z-1"},
            {"Customer Name": "AMAZON", "Salesman": "REdwards", "Item Number": "A-2"},
            {"Customer Name": "MACY'S", "Salesman": "AGrossman", "Item Number": "M-1"},
            {"Customer Name": "BOSCOV'S", "Salesman": "AGrossman", "Item Number": "B-1"},
            {"Customer Name": "AMAZON", "Salesman": "REdwards", "Item Number": "A-1"},
            {"Customer Name": "MACY'S", "Salesman": "AGrossman", "Item Number": "A-1"},
        ],
        "default_group": ["Salesman"],
        "default_layout": {
            "group_levels": ["Customer Name"],
            "sort_levels": [
                {"field": "Customer Name", "dir": "asc"},
                {"field": "Item Number", "dir": "asc"},
            ],
        },
    }]}
    layout = {"views": {"summary": {
        "group": ["Salesman"],
        "sorters": [
            {"column": "Customer Name", "dir": "asc"},
            {"column": "Item Number", "dir": "asc"},
        ],
    }}}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, layout)))
    col_a = [c.value for c in wb["Summary"]["A"]]
    col_c = [c.value for c in wb["Summary"]["C"]]
    assert col_a.count("Salesman: AGrossman") == 1
    assert col_a.count("Salesman: REdwards") == 1
    assert col_a.index("Salesman: AGrossman") < col_a.index("Salesman: REdwards")
    ag = col_a.index("Salesman: AGrossman")
    re = col_a.index("Salesman: REdwards")
    assert col_a[ag + 1] == "BOSCOV'S"
    assert col_a[ag + 2] == "MACY'S"
    assert col_c[ag + 2] == "A-1"
    assert col_a[re + 1] == "AMAZON"
    assert col_c[re + 1] == "A-1"
    assert col_a[re + 2] == "AMAZON"
    assert col_c[re + 2] == "A-2"
    assert col_a[re + 3] == "ZEBRA"


def test_export_summary_salesman_group_takes_builder_customer_sort():
    """No Daily Ordered summary view: still sort customers inside default_group."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    payload = {"tabs": [{
        "key": "summary", "name": "Summary",
        "columns": [
            {"field": "Customer Name", "header": "Customer Name", "type": "text"},
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "Item Number", "header": "Item Number", "type": "text"},
        ],
        "rows": [
            {"Customer Name": "ZEBRA", "Salesman": "REdwards", "Item Number": "Z-1"},
            {"Customer Name": "MACY'S", "Salesman": "AGrossman", "Item Number": "M-1"},
            {"Customer Name": "BOSCOV'S", "Salesman": "AGrossman", "Item Number": "B-1"},
        ],
        "default_group": ["Salesman"],
        "default_layout": {
            "group_levels": ["Customer Name"],
            "sort_levels": [
                {"field": "Customer Name", "dir": "asc"},
                {"field": "Item Number", "dir": "asc"},
            ],
        },
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, None)))
    col_a = [c.value for c in wb["Summary"]["A"]]
    assert col_a.count("Salesman: AGrossman") == 1
    ag = col_a.index("Salesman: AGrossman")
    assert col_a[ag + 1] == "BOSCOV'S"
    assert col_a[ag + 2] == "MACY'S"


def test_daily_ordered_layout_sorts_summary_customers_within_salesman():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    from web.scheduling.company_layouts import DAILY_ORDERED_LAYOUT
    payload = {"tabs": [{
        "key": "summary", "name": "Summary",
        "columns": [
            {"field": "Customer Name", "header": "Customer Name", "type": "text"},
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "Item Number", "header": "Item Number", "type": "text"},
        ],
        "rows": [
            {"Customer Name": "ZEBRA", "Salesman": "REdwards", "Item Number": "Z-1"},
            {"Customer Name": "BOSCOV'S", "Salesman": "AGrossman", "Item Number": "B-9"},
            {"Customer Name": "AMAZON", "Salesman": "REdwards", "Item Number": "A-1"},
            {"Customer Name": "BOSCOV'S", "Salesman": "AGrossman", "Item Number": "B-1"},
        ],
        "default_group": ["Salesman"],
    }]}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, DAILY_ORDERED_LAYOUT)))
    col_a = [c.value for c in wb["Summary"]["A"]]
    col_c = [c.value for c in wb["Summary"]["C"]]
    assert col_a.count("Salesman: AGrossman") == 1
    assert col_a.count("Customer Name: BOSCOV'S") == 1
    assert col_a.index("Salesman: AGrossman") < col_a.index("Customer Name: BOSCOV'S")
    assert col_a.index("Customer Name: BOSCOV'S") < col_a.index("Salesman: REdwards")
    bos = col_a.index("Customer Name: BOSCOV'S")
    assert col_c[bos + 1] == "B-1"
    assert col_c[bos + 2] == "B-9"
    assert col_a.index("Customer Name: AMAZON") < col_a.index("Customer Name: ZEBRA")


def test_daily_ordered_by_customer_salesman_only_by_order_ungrouped():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook
    from web.scheduling.company_layouts import DAILY_ORDERED_LAYOUT
    payload = {"tabs": [
        {
            "key": "by_customer", "name": "By Customer",
            "columns": [
                {"field": "Salesman", "header": "Salesman", "type": "text"},
                {"field": "CustomerName", "header": "CustomerName", "type": "text"},
            ],
            "rows": [
                {"Salesman": "REdwards", "CustomerName": "ZEBRA"},
                {"Salesman": "AGrossman", "CustomerName": "BOSCOV'S"},
                {"Salesman": "REdwards", "CustomerName": "AMAZON"},
                {"Salesman": "AGrossman", "CustomerName": "MACY'S"},
            ],
            "default_group": ["Salesman"],
        },
        {
            "key": "by_order", "name": "By Order",
            "columns": [
                {"field": "Salesman", "header": "Salesman", "type": "text"},
                {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
            ],
            "rows": [
                {"Salesman": "REdwards", "SalesOrderNumber": "SO2"},
                {"Salesman": "AGrossman", "SalesOrderNumber": "SO1"},
            ],
            "default_group": ["Salesman"],
        },
    ]}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, DAILY_ORDERED_LAYOUT)))
    cust = [c.value for c in wb["By Customer"]["A"]]
    names = [c.value for c in wb["By Customer"]["B"]]
    assert cust.count("Salesman: AGrossman") == 1
    assert cust.count("Salesman: REdwards") == 1
    assert not any(str(v).startswith("CustomerName:") for v in cust)
    ag = cust.index("Salesman: AGrossman")
    assert names[ag + 1] == "BOSCOV'S"
    assert names[ag + 2] == "MACY'S"
    re = cust.index("Salesman: REdwards")
    assert names[re + 1] == "AMAZON"
    assert names[re + 2] == "ZEBRA"
    orders = [c.value for c in wb["By Order"]["A"]]
    assert not any(str(v).startswith("Salesman:") for v in orders)
    assert "Grand total" not in orders


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


def _font_rgb(cell) -> str:
    color = getattr(cell.font, "color", None)
    rgb = getattr(color, "rgb", None) if color is not None else None
    return str(rgb or "").upper()


def _march_salesman_tab(*, strip_band: bool = False) -> dict:
    from report_engine.reports import salesman as B

    raw = {
        "SalesmanId": "10",
        "SalesmanName": "Robert Edwards",
        "CustomerAccount": "100",
        "CustomerName": "Acme",
        "Jan This Year": 0, "Jan Last Year": 0,
        "Feb This Year": 200, "Feb Last Year": 0,
        "Mar This Year": 100, "Mar Last Year": 500,  # month $ delta is negative
        "Apr This Year": 0, "Apr Last Year": 0,
        "May This Year": 0, "May Last Year": 0,
        "Jun This Year": 0, "Jun Last Year": 0,
        "Jul This Year": 0, "Jul Last Year": 0,
        "Aug This Year": 0, "Aug Last Year": 0,
        "Sep This Year": 0, "Sep Last Year": 0,
        "Oct This Year": 0, "Oct Last Year": 0,
        "Nov This Year": 0, "Nov Last Year": 0,
        "Dec This Year": 0, "Dec Last Year": 0,
        "Full Year This Year": 1200,
        "Full Year Last Year": 500,
    }
    tab = next(t for t in B.build(B.clean_rows([raw]), year=2026) if t["name"] == "Mar")
    if strip_band:
        for col in tab["columns"]:
            col.pop("band", None)
    return tab


def test_export_salesman_bands_follow_fields_when_leading_columns_hidden():
    """Hiding Sort Number + Salesman used to paint Excel E instead of C."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.delivery.layout import apply_layout
    from web.reporting.export import build_workbook

    tab = _march_salesman_tab()
    payload = {"report_key": "salesman", "tabs": [tab]}
    layout = {"views": {tab["key"]: {
        "hidden": ["Sort Number", "Salesman"],
        "group": ["Salesman"],
    }}}
    shaped = apply_layout(payload, layout)
    ws = openpyxl.load_workbook(io.BytesIO(build_workbook(shaped, layout)))[tab["name"]]
    headers = [c.value for c in ws[1]]
    assert headers[0] == "Cust. #"
    assert headers[2] == "Sales March 2026"  # used to be Excel E; now C
    assert headers[6] == "Sales 2026 Jan Thru March"
    assert headers[10] == "Sales Year to Date 2026"
    data = next(
        row for row in ws.iter_rows(min_row=2)
        if isinstance(row[2].value, (int, float))
    )
    assert _font_rgb(data[2]).endswith("0000CC")   # month TY: blue on C
    assert _font_rgb(data[6]).endswith("008000")   # YTD: green, not shifted blue
    assert _font_rgb(data[10]).endswith("800080")  # full year: purple
    dollar = next(i for i, h in enumerate(headers) if h == "$ This Year to Last Year")
    assert data[dollar].value == -400.0
    assert _font_rgb(data[dollar]).endswith("FF0000")


def test_export_salesman_bands_follow_reordered_fields():
    openpyxl = pytest.importorskip("openpyxl")
    from web.delivery.layout import apply_layout
    from web.reporting.export import build_workbook

    tab = _march_salesman_tab()
    payload = {"report_key": "salesman", "tabs": [tab]}
    layout = {"views": {tab["key"]: {"order": [
        "Sales Year to Date 2026",
        "Cust. #",
        "Sales March 2026",
    ]}}}
    shaped = apply_layout(payload, layout)
    ws = openpyxl.load_workbook(io.BytesIO(build_workbook(shaped, layout)))[tab["name"]]
    assert [c.value for c in ws[1][:3]] == [
        "Sales Year to Date 2026", "Cust. #", "Sales March 2026",
    ]
    assert _font_rgb(ws["A2"]).endswith("800080")  # full-year field stayed purple in A
    ident = ws["B2"].font.color
    ident_rgb = str(getattr(ident, "rgb", "") or "").upper()
    assert not ident_rgb.endswith("0000CC")
    assert not ident_rgb.endswith("008000")
    assert not ident_rgb.endswith("800080")
    assert _font_rgb(ws["C2"]).endswith("0000CC")


def test_export_salesman_bands_infer_field_names_without_band_tag():
    """Cached payloads from before columns carried ``band`` still color by field."""
    openpyxl = pytest.importorskip("openpyxl")
    from web.delivery.layout import apply_layout
    from web.reporting.export import build_workbook

    tab = _march_salesman_tab(strip_band=True)
    payload = {"report_key": "salesman", "tabs": [tab]}
    layout = {"views": {tab["key"]: {"hidden": ["Sort Number", "Salesman"]}}}
    shaped = apply_layout(payload, layout)
    ws = openpyxl.load_workbook(io.BytesIO(build_workbook(shaped, layout)))[tab["name"]]
    assert ws["A1"].value == "Cust. #"
    assert ws["C1"].value == "Sales March 2026"
    assert _font_rgb(ws["C2"]).endswith("0000CC")
    assert _font_rgb(ws["G2"]).endswith("008000")


def test_export_salesman_default_columns_still_start_blue_at_e():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook

    tab = _march_salesman_tab()
    ws = openpyxl.load_workbook(io.BytesIO(build_workbook(
        {"report_key": "salesman", "tabs": [tab]}, None)))[tab["name"]]
    assert ws["A1"].value == "Sort Number"
    assert ws["E1"].value == "Sales March 2026"
    ident = str(getattr(ws["C2"].font.color, "rgb", "") or "").upper()
    assert not ident.endswith("0000CC")
    assert _font_rgb(ws["E2"]).endswith("0000CC")
    assert _font_rgb(ws["I2"]).endswith("008000")
    assert _font_rgb(ws["M2"]).endswith("800080")
