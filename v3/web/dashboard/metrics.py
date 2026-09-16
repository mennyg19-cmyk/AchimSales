"""Per-customer cadence metrics (pure; no I/O).

Ported verbatim from the LIVE app's `_compute_customer_metrics`
(webapp/dashboard_data.py). Given a customer's order dates, compute:

  * days_since_last  - calendar days since the most recent order
  * avg_gap_days     - population MEAN of positive day-gaps between orders
  * gap_stdev        - population STDEV of those gaps (the overdue buffer)
  * overdue_threshold = avg_gap_days + gap_stdev
  * status           - new | active | overdue | inactive

Status precedence (matches LIVE exactly):
  - "new"      : <2 distinct order days, or every gap is 0 (same-day-only)
  - "inactive" : has a cadence AND days_since_last > 365   (checked first)
  - "overdue"  : has a cadence AND days_since_last > overdue_threshold (<=365)
  - "active"   : has a cadence AND days_since_last <= overdue_threshold

Zero-day gaps (multiple orders the same day) are dropped before the stats,
identical to LIVE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

STATUS_NEW = "new"
STATUS_ACTIVE = "active"
STATUS_OVERDUE = "overdue"
STATUS_INACTIVE = "inactive"

INACTIVE_DAYS = 365


@dataclass(frozen=True)
class CustomerMetrics:
    last_order_date: date | None
    days_since_last: int | None
    avg_gap_days: float | None
    gap_stdev: float | None
    overdue_threshold: float | None
    status: str


def compute_metrics(order_dates: list[date], *, today: date | None = None) -> CustomerMetrics:
    """Compute cadence metrics from a customer's order dates (any order/dups ok)."""
    today = today or date.today()

    if not order_dates:
        return CustomerMetrics(None, None, None, None, None, STATUS_NEW)

    parsed = sorted(order_dates)
    last = parsed[-1]
    days_since = (today - last).days

    # Positive gaps only (drop same-day duplicates).
    gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
    gaps = [g for g in gaps if g > 0]

    if not gaps:
        # One distinct day (or only same-day orders): not enough to learn cadence.
        return CustomerMetrics(last, days_since, None, None, None, STATUS_NEW)

    mean_gap = sum(gaps) / len(gaps)
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    stdev = math.sqrt(variance)
    threshold = mean_gap + stdev

    if days_since > INACTIVE_DAYS:
        status = STATUS_INACTIVE
    elif days_since > threshold:
        status = STATUS_OVERDUE
    else:
        status = STATUS_ACTIVE

    return CustomerMetrics(
        last_order_date=last, days_since_last=days_since,
        avg_gap_days=round(mean_gap, 1), gap_stdev=round(stdev, 1),
        overdue_threshold=round(threshold, 1), status=status,
    )
