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


# Matches the live app's report keys. Status reflects v3 build reality, updated
# as builders land. customer_aging / amazon_weekly are BACKLOG until built - they
# must never appear as working reports (this is the "no fake stub" guarantee).
REGISTRY: tuple[ReportSpec, ...] = (
    ReportSpec("ordered", "Ordered", ReportStatus.BACKLOG),
    ReportSpec("invoiced", "Invoiced", ReportStatus.BACKLOG),
    ReportSpec("salesman", "Salesman", ReportStatus.BACKLOG),
    ReportSpec("number_4", "Number 4", ReportStatus.BACKLOG),
    ReportSpec("customer_activity", "Customer Activity", ReportStatus.BACKLOG),
    ReportSpec("customer_last_order", "Customer Last Order", ReportStatus.BACKLOG),
    ReportSpec("amazon_weekly", "Amazon Weekly", ReportStatus.BACKLOG),
    ReportSpec("customer_aging", "Customer Aging", ReportStatus.BACKLOG),
)

_BY_KEY = {spec.key: spec for spec in REGISTRY}


def get(key: str) -> ReportSpec | None:
    return _BY_KEY.get(key)


def built_reports() -> tuple[ReportSpec, ...]:
    return tuple(s for s in REGISTRY if s.status is ReportStatus.BUILT)


def backlog_reports() -> tuple[ReportSpec, ...]:
    return tuple(s for s in REGISTRY if s.status is ReportStatus.BACKLOG)
