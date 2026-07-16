"""Recipient safety tests for the OData Amazon Weekly email."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from openpyxl import Workbook

from config import salesman_excel
from core.dates import FetchPlan, PeriodSpec
from reports.ordered.runner import OrderedReportRunner


ENV_RECIPIENTS = [
    "amazon-one@example.com",
    "amazon-two@example.com",
    "outside-salesman-map@example.com",
]
SALESMEN = [
    ("Alice", "alice@example.com"),
    ("Bob", "bob@example.com"),
]


def _write_map(path, amazon_values: dict[str, bool] | None = None) -> None:
    wb = Workbook()
    ws = wb.active
    headers = ["Key", "Number", "FullName", "DisplayName", "Email"]
    if amazon_values is not None:
        headers.append("Recv_AmazonWeekly")
    ws.append(headers)

    for number, (name, email) in enumerate(SALESMEN, start=1):
        row = [name, str(number), name, name, email]
        if amazon_values is not None:
            row.append(amazon_values.get(name, False))
        ws.append(row)

    wb.save(path)
    wb.close()


@pytest.fixture(autouse=True)
def _clear_salesman_cache():
    salesman_excel.load_salesman_map.cache_clear()
    yield
    salesman_excel.load_salesman_map.cache_clear()


@pytest.fixture
def env_recipients(monkeypatch):
    monkeypatch.setenv("AMAZON_EMAIL_RECIPIENTS", ";".join(ENV_RECIPIENTS))
    return list(ENV_RECIPIENTS)


def test_missing_amazon_column_uses_only_environment(tmp_path, env_recipients):
    map_path = tmp_path / "salesman_map.xlsx"
    _write_map(map_path)

    recipients = salesman_excel.get_amazon_weekly_recipients(str(map_path))

    assert recipients == env_recipients
    assert set(recipients).isdisjoint({email for _, email in SALESMEN})


def test_existing_amazon_column_is_authoritative(tmp_path, env_recipients):
    map_path = tmp_path / "salesman_map.xlsx"
    _write_map(map_path, {"Alice": True, "Bob": False})

    recipients = salesman_excel.get_amazon_weekly_recipients(str(map_path))

    assert recipients == ["alice@example.com"]
    assert env_recipients[-1] not in recipients


def test_existing_all_false_amazon_column_sends_to_nobody(tmp_path, env_recipients):
    map_path = tmp_path / "salesman_map.xlsx"
    _write_map(map_path, {})

    recipients = salesman_excel.get_amazon_weekly_recipients(str(map_path))

    assert recipients == []


def test_unrelated_missing_columns_keep_existing_behavior(tmp_path):
    map_path = tmp_path / "salesman_map.xlsx"
    _write_map(map_path)

    subscribers = salesman_excel.get_report_subscribers(
        "ordered", path=str(map_path)
    )

    assert [email for _, email, _, _ in subscribers] == [
        "alice@example.com",
        "bob@example.com",
    ]


def test_ordered_email_uses_environment_when_amazon_column_missing(
    tmp_path, env_recipients,
):
    map_path = tmp_path / "salesman_map.xlsx"
    _write_map(map_path)
    runner = OrderedReportRunner()
    runner._cli_args = SimpleNamespace(
        dry_run=False, no_email=False, test=False, email=True
    )

    with (
        patch.object(salesman_excel, "_XLSX_PATH", str(map_path)),
        patch("reports.ordered.runner.send_report_email") as send_email,
    ):
        runner._email_filtered_report(None, "Amazon Weekly", "body")

    send_email.assert_called_once()
    assert send_email.call_args.kwargs["recipients"] == env_recipients


def test_ordered_dry_run_never_emails_on_no_data():
    runner = OrderedReportRunner()
    runner._cli_args = SimpleNamespace(
        dry_run=True, no_email=False, test=False, email=True
    )
    period = PeriodSpec(
        label="Last 7 Days",
        start_date=date(2026, 7, 9),
        end_date=date(2026, 7, 15),
        subfolder="This Week",
        filename_tag="2026-07-15",
    )
    plan = FetchPlan(
        fetch_start=period.start_date,
        fetch_end=period.end_date,
        periods=[period],
    )
    empty_frames = (pd.DataFrame(),) * 4

    with (
        patch.object(runner, "connect", return_value=("url", object(), "usmf")),
        patch("reports.ordered.runner.fetch_all_data", return_value=empty_frames),
        patch.object(runner, "_email_filtered_report") as email_filtered,
        patch("reports.ordered.runner.send_report_email") as send_email,
    ):
        runner._run_for_salesman_list([], ["9300", "9301"], plan, None)

    email_filtered.assert_not_called()
    send_email.assert_not_called()


def test_ordered_no_email_flag_overrides_email_request():
    runner = OrderedReportRunner()
    runner._cli_args = SimpleNamespace(
        dry_run=False, no_email=True, test=False, email=True
    )

    assert runner._send_emails is False
