"""Tests for the per-customer cadence metrics (lock-step with LIVE math)."""

from datetime import date, timedelta

from web.dashboard.metrics import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_NEW,
    STATUS_OVERDUE,
    compute_metrics,
)

TODAY = date(2026, 6, 1)


def _days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_no_orders_is_new():
    m = compute_metrics([], today=TODAY)
    assert m.status == STATUS_NEW
    assert m.avg_gap_days is None and m.days_since_last is None


def test_single_order_is_new():
    m = compute_metrics([_days_ago(10)], today=TODAY)
    assert m.status == STATUS_NEW
    assert m.days_since_last == 10
    assert m.avg_gap_days is None


def test_same_day_only_orders_is_new():
    d = _days_ago(5)
    m = compute_metrics([d, d, d], today=TODAY)
    assert m.status == STATUS_NEW  # all gaps zero -> no cadence
    assert m.avg_gap_days is None


def test_regular_cadence_active():
    # Orders ~30 days apart; last one recent -> active.
    dates = [_days_ago(95), _days_ago(65), _days_ago(35), _days_ago(5)]
    m = compute_metrics(dates, today=TODAY)
    assert m.status == STATUS_ACTIVE
    assert m.avg_gap_days == 30.0  # gaps 30,30,30
    assert m.gap_stdev == 0.0
    assert m.overdue_threshold == 30.0


def test_overdue_when_past_threshold_but_within_year():
    # Tight 10-day cadence, but 100 days since last (and <365) -> overdue.
    dates = [_days_ago(140), _days_ago(130), _days_ago(120), _days_ago(110), _days_ago(100)]
    m = compute_metrics(dates, today=TODAY)
    assert m.status == STATUS_OVERDUE
    assert 0 < m.overdue_threshold < m.days_since_last <= 365


def test_inactive_beats_overdue_past_365():
    dates = [_days_ago(800), _days_ago(770), _days_ago(740), _days_ago(400)]
    m = compute_metrics(dates, today=TODAY)
    assert m.status == STATUS_INACTIVE
    assert m.days_since_last > 365


def test_mean_and_stdev_exact():
    # gaps 10 and 20 -> mean 15, population stdev 5, threshold 20.
    dates = [_days_ago(31), _days_ago(21), _days_ago(1)]
    m = compute_metrics(dates, today=TODAY)
    assert m.avg_gap_days == 15.0
    assert m.gap_stdev == 5.0
    assert m.overdue_threshold == 20.0
