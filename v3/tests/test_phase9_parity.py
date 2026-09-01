"""Phase 9: retained reports, Q6 retirement, Ordered Q4 grouping column."""

from pathlib import Path

from report_engine.registry import backlog_reports, built_reports
from report_engine.reports.ordered import SUMMARY_COLS

V3_ROOT = Path(__file__).resolve().parents[1]


def test_built_reports_are_the_retained_set():
    assert {s.key for s in built_reports()} == {
        "ordered",
        "invoiced",
        "salesman",
        "number_4",
        "customer_activity",
        "customer_last_order",
        "item_averages",
        "sales_by_state",
    }


def test_customer_aging_stays_backlog():
    assert {s.key for s in backlog_reports()} == {"customer_aging"}


def test_ordered_summary_leads_with_customer_account():
    assert SUMMARY_COLS[0]["field"] == "CustomerAccount"


def test_no_in_app_email_distribution_module():
    hits = [
        str(path.relative_to(V3_ROOT))
        for path in V3_ROOT.rglob("*")
        if path.is_file()
        and "email_distribution" in path.name.lower()
        and ".venv" not in path.parts
        and "node_modules" not in path.parts
    ]
    assert hits == []


def test_hashed_lock_has_hashes():
    text = (V3_ROOT.parent / "requirements.txt").read_text()
    assert "--hash=sha256:" in text
    assert "Flask>=" not in text
    # pytest 8 on Python 3.10 pulls these; an unhashed extra fails CI install.
    assert "\nexceptiongroup==" in text
    assert "\ntomli==" in text
