"""Shared report access + naming policy for the test app.

This mirrors key live-app behavior:
  - salesmen only see salesman-filter reports unless explicitly overridden
  - managers/admins can see all enabled reports (subject to overrides)
  - role-specific display names (e.g. Invoiced -> Shipped for salesmen)
  - run-time salesman scoping (salesman fixed to self; managers constrained
    to assigned salesman keys)
"""

from __future__ import annotations

from dataclasses import replace

from test.config.reports import REPORTS, Report
from test.webapp.db import (
    get_app_user,
    get_user_report_overrides,
    get_user_salesman_access,
)


PRIVILEGED_ROLES = {"admin", "developer", "manager"}


def get_user_profile(email: str) -> dict:
    """Best-effort role profile from app_users.

    Falls back to a salesman role when no row exists yet so behavior stays
    restrictive by default.
    """
    row = get_app_user(email or "") or {}
    role = (row.get("role") or "salesman").strip().lower() or "salesman"
    return {
        "email": (email or "").strip().lower(),
        "role": role,
        "salesman_key": (row.get("salesman_key") or "").strip() or None,
        "is_admin": role in {"admin", "developer"},
    }


def _apply_role_labels(report: Report, role: str) -> Report:
    if role in PRIVILEGED_ROLES:
        return report
    if report.name_salesman or report.description_salesman:
        return replace(
            report,
            name=report.name_salesman or report.name,
            description=report.description_salesman or report.description,
        )
    return report


def list_accessible_reports(email: str, *, include_disabled: bool = False) -> list[Report]:
    """Return reports visible to this user, in registry order."""
    profile = get_user_profile(email)
    role = profile["role"]
    overrides = get_user_report_overrides(email)

    out: list[Report] = []
    for report in REPORTS.values():
        if not include_disabled and not report.enabled:
            continue

        # Salesmen default to salesman-filter reports only (live parity).
        if role not in PRIVILEGED_ROLES and not report.salesman_filter:
            if not overrides.get(report.key, False):
                continue

        if report.key in overrides and not overrides[report.key]:
            continue

        out.append(_apply_role_labels(report, role))
    return out


def can_access_report(email: str, report_key: str) -> bool:
    return any(r.key == report_key for r in list_accessible_reports(email, include_disabled=False))


def get_report_for_user(email: str, report_key: str) -> Report:
    """Return the role-adjusted report metadata, or raise KeyError."""
    for report in list_accessible_reports(email, include_disabled=True):
        if report.key == report_key:
            return report
    raise KeyError(report_key)


def scope_params_for_user(email: str, report: Report, params: dict) -> dict:
    """Apply live-style role scoping for salesman-filter reports."""
    profile = get_user_profile(email)
    role = profile["role"]
    out = dict(params or {})
    if not report.salesman_filter:
        return out

    if role == "salesman":
        sk = profile["salesman_key"]
        if sk:
            out["salesman"] = sk
            out.pop("salesman_list", None)
        return out

    if role == "manager":
        allowed = set(get_user_salesman_access(email))
        if not allowed:
            raise PermissionError("No salesmen assigned to your account.")
        requested = (out.get("salesman") or "").strip()
        if requested and requested in allowed:
            out["salesman"] = requested
        elif len(allowed) == 1:
            out["salesman"] = next(iter(allowed))
        else:
            out.pop("salesman", None)
            out["salesman_list"] = sorted(allowed)
        return out

    return out
