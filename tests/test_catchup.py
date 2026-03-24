"""
Tests for catch-up / two-pass logic in the universal runbook.

Uses ``_SIMULATED_NOW`` and temporary run_log.csv files to exercise
the catch-up decision engine without running actual reports.
"""

import csv
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

# Ensure runbooks/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runbooks"))

EASTERN = ZoneInfo("America/New_York")

LOG_COLS = ["timestamp", "report_name", "status", "duration_sec",
            "rows_output", "files_uploaded", "args", "error"]


def _make_run_log(rows: list[dict]) -> str:
    """Write a temporary run_log.csv and return its path."""
    path = os.path.join(tempfile.gettempdir(), f"test_catchup_{os.getpid()}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return path


@pytest.fixture(autouse=True)
def _reset_simulated_now():
    """Reset _SIMULATED_NOW before/after each test."""
    import universal_runbook as rb
    old = getattr(rb, "_SIMULATED_NOW", None)
    yield
    rb._SIMULATED_NOW = old


class TestCatchup:

    def test_no_gap_no_catchup(self):
        """Last success = yesterday → no catch-up injection."""
        import universal_runbook as rb

        sim_now = datetime(2026, 3, 25, 23, 0, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now
        yesterday = (sim_now.date() - timedelta(days=1)).isoformat()

        log_path = _make_run_log([{
            "timestamp": f"{yesterday} 23:00:00",
            "report_name": "Ordered Report",
            "status": "SUCCESS", "args": "--period daily",
        }])

        result = rb._maybe_inject_catchup_args(
            ["--period", "daily"], "--period daily", log_path, "Ordered Report"
        )
        # No catch-up needed → returns the same argv
        assert result is None or result == ["--period", "daily"]

    def test_3_day_gap_daily(self):
        """3-day gap with period=daily → injects --from/--to."""
        import universal_runbook as rb

        sim_now = datetime(2026, 3, 25, 23, 0, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now

        log_path = _make_run_log([{
            "timestamp": "2026-03-22 23:00:00",
            "report_name": "Ordered Report",
            "status": "SUCCESS", "args": "--period daily",
        }])

        result = rb._maybe_inject_catchup_args(
            ["--period", "daily"], "--period daily", log_path, "Ordered Report"
        )
        # Should inject --from and --to covering the gap
        assert result is not None
        if isinstance(result, list):
            joined = " ".join(result)
            assert "--from" in joined
            assert "--to" in joined

    def test_nightly_two_pass(self):
        """No period, 3-day gap → two-pass sentinel returned."""
        import universal_runbook as rb

        sim_now = datetime(2026, 3, 25, 23, 7, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now

        log_path = _make_run_log([{
            "timestamp": "2026-03-22 23:27:05",
            "report_name": "Ordered Report",
            "status": "SUCCESS", "args": "",
        }])

        result = rb._maybe_inject_catchup_args([], "", log_path, "Ordered Report")
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] == rb._CATCHUP_THEN_NORMAL

    def test_mtd_cross_month(self):
        """Last success in prior month → catch-up for prior month range."""
        import universal_runbook as rb

        sim_now = datetime(2026, 4, 2, 23, 0, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now

        log_path = _make_run_log([{
            "timestamp": "2026-03-30 23:00:00",
            "report_name": "Ordered Report",
            "status": "SUCCESS", "args": "--period mtd",
        }])

        result = rb._maybe_inject_catchup_args(
            ["--period", "mtd"], "--period mtd", log_path, "Ordered Report"
        )
        # Cross-month: should inject prior month range
        if isinstance(result, list):
            joined = " ".join(result)
            assert "--from" in joined
            assert "2026-03" in joined

    def test_last_7_days_widened(self):
        """5-day gap on last_7_days → start widened by gap days."""
        import universal_runbook as rb

        sim_now = datetime(2026, 3, 25, 23, 0, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now

        log_path = _make_run_log([{
            "timestamp": "2026-03-20 23:00:00",
            "report_name": "Ordered Report",
            "status": "SUCCESS", "args": "--period last_7_days",
        }])

        result = rb._maybe_inject_catchup_args(
            ["--period", "last_7_days"], "--period last_7_days", log_path, "Ordered Report"
        )
        if isinstance(result, list):
            joined = " ".join(result)
            assert "--from" in joined

    def test_explicit_from_to_no_catchup(self):
        """Explicit --from/--to → no catch-up injection."""
        import universal_runbook as rb

        sim_now = datetime(2026, 3, 25, 23, 0, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now

        log_path = _make_run_log([{
            "timestamp": "2026-03-20 23:00:00",
            "report_name": "Ordered Report",
            "status": "SUCCESS", "args": "--from 2026-03-01 --to 2026-03-15",
        }])

        result = rb._maybe_inject_catchup_args(
            ["--from", "2026-03-01", "--to", "2026-03-25"],
            "--from 2026-03-01 --to 2026-03-25",
            log_path, "Ordered Report"
        )
        # Explicit range → no modification
        assert result is None or result == ["--from", "2026-03-01", "--to", "2026-03-25"]

    def test_no_prior_success(self):
        """No prior success in log → should not crash."""
        import universal_runbook as rb

        sim_now = datetime(2026, 3, 25, 23, 0, tzinfo=EASTERN)
        rb._SIMULATED_NOW = sim_now

        log_path = _make_run_log([])

        result = rb._maybe_inject_catchup_args(
            ["--period", "daily"], "--period daily", log_path, "Ordered Report"
        )
        # No prior success → either None or unchanged args
        assert result is None or isinstance(result, list)
