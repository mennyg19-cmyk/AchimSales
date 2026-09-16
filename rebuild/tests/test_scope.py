"""Regression tests for per-salesman scoping (who sees which rows).

These guard the security promise: a privileged person sees everything, a mapped
person sees only their salesman number(s), an unmapped person can't run reports,
and a scoped person can't widen their view by tampering with the salesman filter.
Pure functions -- no database, no network.
"""

from __future__ import annotations

import pytest

from rebuild.auth.principal import ROLE_DEVELOPER, ROLE_USER, Principal
from rebuild.reporting.authz import SCOPE_ALL, allowed_salesmen, resolve_access
from rebuild.reports.params import force_salesman_scope


class _FakeScope:
    """Stands in for UserScopeRepository: email -> assigned salesman numbers."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    def salesmen_for(self, email: str) -> list[str]:
        return list(self._mapping.get((email or "").strip().lower(), []))


def test_privileged_user_sees_all_salesmen():
    access = resolve_access(Principal("boss@x.com", "Boss", ROLE_DEVELOPER), "invoiced", _FakeScope({}))
    assert access.allowed
    assert access.scope_token == SCOPE_ALL
    assert access.salesmen is None


def test_mapped_user_is_scoped_to_their_sorted_salesmen():
    scope = _FakeScope({"rep@x.com": ["20", "10"]})
    access = resolve_access(Principal("rep@x.com", "Rep", ROLE_USER), "invoiced", scope)
    assert access.allowed
    assert access.salesmen == ("10", "20")
    assert access.scope_token == "sm:10,20"


def test_unmapped_regular_user_is_denied():
    access = resolve_access(Principal("nobody@x.com", "N", ROLE_USER), "invoiced", _FakeScope({}))
    assert not access.allowed
    assert access.salesmen is None
    assert "admin" in access.reason


def test_not_signed_in_is_denied():
    assert not resolve_access(None, "invoiced", _FakeScope({})).allowed


def test_allowed_salesmen_round_trips_the_scope_token():
    assert allowed_salesmen("all") is None
    assert allowed_salesmen("sm:10,20") == ["10", "20"]


def test_allowed_salesmen_fails_closed_on_a_blank_or_tampered_token():
    # "see everything" must be stated as the exact token "all" -- blank/missing,
    # empty-sm:, whitespace-padded "all", whitespace-containing parts, double
    # commas, trailing commas — anything other than a clean "sm:N,N" format —
    # must refuse, so a corrupt or tampered stored token can never silently widen.
    for bad in ("", None, "everything", "sm", "sm:", " all ", "all ", "ALL",
                "sm: ", "sm:10,", "sm:,10", "sm:10,,20", "sm: 10"):
        with pytest.raises(ValueError):
            allowed_salesmen(bad)


def test_scope_forces_salesman_param_over_user_filter():
    # The user tried to ask for salesman 99; scope must overwrite it.
    forced = force_salesman_scope(
        "invoiced", {"Salesman": "99", "InvoiceDateFrom": "2026-01-01"}, ["10", "20"]
    )
    assert forced["Salesman"] == "10,20"
    assert forced["InvoiceDateFrom"] == "2026-01-01"


def test_scope_all_leaves_params_untouched():
    params = {"Salesman": "99"}
    assert force_salesman_scope("invoiced", params, None) is params


def test_a_report_with_no_salesman_param_cannot_be_scoped():
    with pytest.raises(KeyError):
        force_salesman_scope("some_other_report", {}, ["10"])
