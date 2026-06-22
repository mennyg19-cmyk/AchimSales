"""The one place that decides who may run a report and what they may see."""

# === What's in this file ===
# Every report route (run, status, result) asks this module the same question:
# "can this person use this report, and what slice of the data is theirs?" Doing
# it in one place means there's no second, looser check to forget. The answer
# carries a scope token that becomes part of the cache key, so results are never
# shared across people who shouldn't share them.
#
# NOTE (PROVISIONAL): per-salesman row scoping isn't built yet -- every signed-in
# person currently gets the full table. When real scoping lands, ONLY this
# function and a row filter change; the routes don't move. Each person still has
# their own cache entry because the cache key also folds in their email.
#
# ReportAccess -- allowed? + the scope token to fold into the cache key
# resolve_access() -- the single access decision for a (person, report)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..auth.principal import Principal

SCOPE_ALL = "all"


@dataclass(frozen=True)
class ReportAccess:
    allowed: bool
    scope_token: str
    reason: str = ""


def resolve_access(principal: Optional[Principal], report_key: str) -> ReportAccess:
    if principal is None:
        return ReportAccess(False, "", "not signed in")
    # Provisional: everyone signed in may run any active report and sees the full
    # table. The scope token is decided here so a future per-salesman rule is a
    # one-place change.
    return ReportAccess(True, SCOPE_ALL)
