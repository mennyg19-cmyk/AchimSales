"""Customer-filtered Ordered --email uses AMAZON_EMAIL_RECIPIENTS only."""

from __future__ import annotations

import pytest

from reports.ordered import runner as ordered_runner


ENV_RECIPIENTS = ["bgrossman@achimonline.com", "ops@achimonline.com"]


def test_filtered_recipients_come_from_environment(monkeypatch):
    monkeypatch.setenv("AMAZON_EMAIL_RECIPIENTS", ";".join(ENV_RECIPIENTS))
    assert ordered_runner._get_filtered_report_recipients() == ENV_RECIPIENTS


def test_empty_environment_means_no_recipients(monkeypatch):
    monkeypatch.setenv("AMAZON_EMAIL_RECIPIENTS", "")
    assert ordered_runner._get_filtered_report_recipients() == []
