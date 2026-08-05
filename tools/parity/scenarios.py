"""Default shared params for each parity report (admin / company-wide)."""

from __future__ import annotations

# Keys must exist on both live and /test.
REPORTS = (
    "ordered",
    "invoiced",
    "salesman",
    "customer_activity",
    "number_4",
)

# Same JSON body shape the UIs send (snake_case filters).
DEFAULT_PARAMS: dict[str, dict] = {
    "ordered": {"period": "last_month"},
    "invoiced": {"period": "ytd"},
    "salesman": {},  # live: full year; /test: year defaults server-side
    "customer_activity": {},  # all salesmen (admin)
    "number_4": {"mode": "both"},
}
