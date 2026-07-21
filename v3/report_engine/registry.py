"""Report registry - single source of truth for which reports exist.

Rule 8: no fake stubs. Every key is either BUILT (wired to a real builder) or
BACKLOG (explicitly not yet implemented). The web layer must NOT render a BACKLOG
report as a clickable, real-looking option - it shows it as disabled/"coming soon"
or hides it. Nothing here pretends to work when it does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReportStatus(str, Enum):
    BUILT = "built"
    BACKLOG = "backlog"


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    status: ReportStatus
    builder_version: int = 1
    # In-app reports (e.g. Customer's Last Order) are customer-picker driven and
    # have their own dedicated pages, NOT the standard filter -> table viewer.
    in_app: bool = False
    # Legacy parity (test/config/reports.py `salesman_filter`): a salesman-filter
    # report is the set a salesman sees by DEFAULT when their per-report access is
    # left on "inherit". Non-salesman_filter reports are inherit-hidden for
    # salesmen until an explicit allow. Managers/admins/developers see everything
    # by default regardless of this flag.
    salesman_default: bool = False
    # Admin/developer only. Salesmen and managers never see or run it, even with
    # an explicit allow row (company-wide data that isn't for the sales floor).
    privileged_only: bool = False


# Matches the live app's report keys. Status reflects v3 build reality, updated
# as builders land. customer_aging / amazon_weekly are BACKLOG until built - they
# must never appear as working reports (this is the "no fake stub" guarantee).
REGISTRY: tuple[ReportSpec, ...] = (
    ReportSpec("ordered", "Ordered", ReportStatus.BUILT, builder_version=2, salesman_default=True),
    ReportSpec("invoiced", "Invoiced", ReportStatus.BUILT, salesman_default=True),
    ReportSpec("salesman", "Salesman", ReportStatus.BUILT),
    # v2: switched from the invoice_lines fetch + in-app pivot to the finished
    # rolling-12 SPs (customer_item / item_customer), so cached v1 payloads
    # must not be reused.
    ReportSpec("number_4", "Number 4", ReportStatus.BUILT, builder_version=2),
    ReportSpec("customer_activity", "Customer Activity", ReportStatus.BUILT, salesman_default=True),
    ReportSpec("customer_last_order", "Customer's Last Order", ReportStatus.BUILT, in_app=True),
    ReportSpec(
        "item_averages", "Item Averages", ReportStatus.BUILT,
        privileged_only=True,
    ),
    ReportSpec("amazon_weekly", "Amazon Weekly", ReportStatus.BACKLOG),
    ReportSpec("customer_aging", "Customer Aging", ReportStatus.BACKLOG, salesman_default=True),
)

_BY_KEY = {spec.key: spec for spec in REGISTRY}


def get(key: str) -> ReportSpec | None:
    return _BY_KEY.get(key)


def built_reports() -> tuple[ReportSpec, ...]:
    return tuple(s for s in REGISTRY if s.status is ReportStatus.BUILT)


def backlog_reports() -> tuple[ReportSpec, ...]:
    return tuple(s for s in REGISTRY if s.status is ReportStatus.BACKLOG)
