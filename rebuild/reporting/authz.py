"""The one place that decides who may run a report and what they may see."""

# === What's in this file ===
# Every report route (run, status, result) asks this module the same question:
# "can this person use this report, and what slice of the data is theirs?" Doing
# it in one place means there's no second, looser check to forget. The answer
# carries a scope token that becomes part of the cache key, so results are never
# shared across people who shouldn't share them.
#
# How scope is decided:
#   - A privileged person (admin/developer) sees everything: scope token "all".
#   - A regular person sees only the salesman number(s) an admin mapped to their
#     login: scope token "sm:<numbers>". The same numbers get forced into the
#     report query and the rows are filtered to them, so they can't see anyone
#     else's data even if they tamper with the request.
#   - A regular person with no mapping can't run anything (they'd see nothing).
#
# ReportAccess -- allowed? + the scope token + the salesman numbers (None = all)
# resolve_access() -- the single access decision for a (person, report)
# allowed_salesmen() -- turn a scope token back into its salesman numbers

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..auth.principal import Principal
from ..data.repositories.user_scope import UserScopeRepository

SCOPE_ALL = "all"
_SCOPE_PREFIX = "sm:"


@dataclass(frozen=True)
class ReportAccess:
    allowed: bool
    scope_token: str
    salesmen: Optional[tuple[str, ...]] = None  # None = every salesman
    reason: str = ""


def salesman_scope_token(salesmen: list[str]) -> str:
    """The one place a "sm:<numbers>" scope token is spelled, so the producer and
    the reader below can never drift apart."""
    return _SCOPE_PREFIX + ",".join(sorted(salesmen))


def allowed_salesmen(scope_token: Optional[str]) -> Optional[list[str]]:
    """The salesman numbers a scope token permits, or None for "all".

    Only two shapes are accepted, both of which the access decision actually
    produces: the exact token "all" (privileged), and "sm:<numbers>" with at
    least one number. Anything else -- blank, missing, whitespace-padded, or
    "sm:" with no numbers -- is a corrupt or tampered token, so we REFUSE
    (raise) rather than fall back to "all". We match "all" exactly (no strip):
    "see everything" must be stated precisely, never inferred from a token that
    merely looks close. Failing closed is the safe default for a worker reading
    a stored job.
    """
    if scope_token == SCOPE_ALL:
        return None
    if scope_token and scope_token.startswith(_SCOPE_PREFIX):
        numbers = [n for n in scope_token[len(_SCOPE_PREFIX):].split(",") if n]
        if not numbers:
            raise ValueError("Scope token 'sm:' has no salesman numbers")
        return numbers
    raise ValueError(f"Unrecognized scope token: {scope_token!r}")


def resolve_access(
    principal: Optional[Principal],
    report_key: str,
    user_scope: UserScopeRepository,
) -> ReportAccess:
    if principal is None:
        return ReportAccess(False, "", reason="not signed in")
    if principal.is_privileged:
        return ReportAccess(True, SCOPE_ALL)
    salesmen = sorted(user_scope.salesmen_for(principal.email))
    if salesmen:
        return ReportAccess(True, salesman_scope_token(salesmen), salesmen=tuple(salesmen))
    return ReportAccess(
        False,
        "",
        reason="no salesman scope assigned -- ask an admin to map your login to your salesman number(s)",
    )
