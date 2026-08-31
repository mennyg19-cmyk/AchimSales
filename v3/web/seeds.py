"""Canonical seed data and boot-time seed functions.

Kept out of the Flask factory so create_app stays about wiring, not fixtures.
"""
from __future__ import annotations

from flask import Flask

from web.data.repositories.feature_flags import FeatureFlagRepository
from web.data.repositories.report_config import ReportConfigRepository

def _seed_feature_flags(app: Flask, db) -> None:
    """Insert default feature flags on a fresh DB (idempotent)."""
    try:
        FeatureFlagRepository(db).seed_defaults()
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("feature-flag seed failed")


def _seed_report_config(app: Flask, db) -> None:
    try:
        ReportConfigRepository(db).seed_built()
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("report-config seed failed")


def _seed_admins(app: Flask, db) -> None:
    """Grant admin to the emails in V3_ADMIN_EMAILS (fallback V2_ADMIN_EMAILS).

    Authorization is DB-authoritative + fail-closed, so without this the first
    person to sign in would land as a no-access 'salesman'. Idempotent.
    """
    import os

    raw = os.environ.get("V3_ADMIN_EMAILS") or os.environ.get("V2_ADMIN_EMAILS") or ""
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    if not emails:
        return
    try:
        with db.precious() as conn:
            for email in emails:
                conn.execute(
                    "INSERT INTO users(email, display_name, role, is_active)"
                    " VALUES (?, '', 'admin', 1)"
                    " ON CONFLICT(email) DO UPDATE SET role='admin', is_active=1",
                    (email,),
                )
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("admin seed failed")


def _seed_developers(app: Flask, db) -> None:
    """Grant 'developer' to the emails in V3_DEVELOPER_EMAILS. Runs AFTER admins so
    a developer listed here also in V2_ADMIN_EMAILS ends up developer, not admin
    (developer outranks admin: it adds the dev tools). Creates the row if missing
    so an account that isn't in the live directory yet still works. Idempotent.
    """
    import os

    raw = os.environ.get("V3_DEVELOPER_EMAILS") or ""
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    if not emails:
        return
    try:
        with db.precious() as conn:
            for email in emails:
                conn.execute(
                    "INSERT INTO users(email, display_name, role, is_active)"
                    " VALUES (?, '', 'developer', 1)"
                    " ON CONFLICT(email) DO UPDATE SET role='developer', is_active=1",
                    (email,),
                )
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("developer seed failed")


_SALESMEN_ALL = {"period": "yesterday", "split_by_salesman": True}
# Invoiced always includes a Commissions sheet. Salesmen Shipped files should not.
_INVOICED_WITHOUT_COMMISSIONS = {
    "order": [
        "summary_by_customer", "full_data", "credits", "invoices",
        "audit_reversals", "totals_by_salesman",
    ],
}
# Per-rep Ordered files: drop By Salesman (the file is already one salesman).
_ORDERED_SALESMAN_FILE = {
    "order": ["summary", "by_customer", "by_item", "by_order", "full_data"],
}


_AZURE_SCHEDULES: list[dict] = [
    {
        "name": "Daily Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Invoiced Report/Daily",
    },
    {
        "name": "Daily Ordered Report",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "00:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Daily Number 4 Report",
        "report_key": "number_4",
        "params": {},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Number 4 Report/Daily",
    },
    {
        "name": "Daily Ordered (9am)",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Daily Salesmen Ordered (9am)",
        "report_key": "ordered",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _ORDERED_SALESMAN_FILE,
    },
    {
        "name": "Daily Salesmen Shipped (9am)",
        "report_key": "invoiced",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _INVOICED_WITHOUT_COMMISSIONS,
    },
    {
        "name": "Monthly Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "last_month"},
        "cadence": {"freq": "monthly", "time": "05:00", "monthday": 1},
        "sharepoint_path": "Invoiced Report/Monthly",
    },
    {
        "name": "Monthly Customer Activity",
        "report_key": "customer_activity",
        "params": {},
        "cadence": {"freq": "monthly", "time": "00:00", "monthday": 1},
        "sharepoint_path": "Salesman Report/Customer Activity/{Month} {YYYY}",
    },
    {
        "name": "Monthly Salesman Report",
        "report_key": "salesman",
        "params": {},
        "cadence": {"freq": "monthly", "time": "22:00", "monthday": 1},
        "sharepoint_path": "Salesman Report/Monthly",
    },
    {
        "name": "Monthly Salesmen Report",
        "report_key": "salesman",
        "params": {"split_by_salesman": True},
        "cadence": {"freq": "monthly", "time": "22:00", "monthday": 1},
    },
    {
        "name": "Amazon Monthly Ordered",
        "report_key": "ordered",
        "params": {"period": "last_month"},
        "cadence": {"freq": "monthly", "time": "19:59", "monthday": 28},
        "sharepoint_path": "Amazon Weekly",
    },
    {
        "name": "Weekly Amazon Ordered (Friday)",
        "report_key": "ordered",
        "params": {"period": "last_7_days"},
        "cadence": {"freq": "weekly", "time": "00:00", "weekdays": [4]},
        "sharepoint_path": "Amazon Weekly",
    },
]


# Live Azure Automation jobs as of 2026-08-13. Names match Azure. Email-only
# Live jobs have no stored recipients here — SharePoint is the delivery so the
# row can be saved; add addresses after you check each one. Skipped:
# amazon_weekly (no Beta report), leftover OrderReportDirect, and Daily 9am
# (customer 48999/917/2267 — deleted on Beta; boot must not put it back).
_LIVE_RUNBOOK_SCHEDULES: list[dict] = [
    {
        "name": "DailyInvoicedReport",
        "report_key": "invoiced",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Invoiced Report/Daily",
    },
    {
        "name": "DailyOrderReport",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "00:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Daily 5am Number_4",
        "report_key": "number_4",
        "params": {},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Number 4 Report/Daily",
    },
    {
        "name": "Daily 9am Salesmen Ordered",
        "report_key": "ordered",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _ORDERED_SALESMAN_FILE,
    },
    {
        "name": "Daily 9am Salesmen Shipped",
        "report_key": "invoiced",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _INVOICED_WITHOUT_COMMISSIONS,
    },
    {
        "name": "Daily Open Orders Report",
        "report_key": "ordered",
        "params": {"period": "yesterday", "salesman": ["Hkaufman"], "status": ["Open order"]},
        "cadence": {"freq": "daily", "time": "11:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Monthly Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "last_month"},
        "cadence": {"freq": "monthly", "time": "05:00", "monthdays": [1]},
        "sharepoint_path": "Invoiced Report/Monthly",
    },
    {
        "name": "Monthly 1st 12am Customer Activity",
        "report_key": "customer_activity",
        "params": {},
        "cadence": {"freq": "monthly", "time": "00:00", "monthdays": [1]},
        "sharepoint_path": "Salesman Report/Customer Activity/{Month} {YYYY}",
    },
    {
        "name": "Monthly 1st 12am Monthly Salesman",
        "report_key": "salesman",
        "params": {},
        "cadence": {"freq": "monthly", "time": "22:00", "monthdays": [1]},
        "sharepoint_path": "Salesman Report/Monthly",
    },
    {
        "name": "Monthly 1st 12am Monthly Salesmen",
        "report_key": "salesman",
        "params": {"split_by_salesman": True},
        "cadence": {"freq": "monthly", "time": "22:00", "monthdays": [1]},
    },
    {
        "name": "Amazon Monthly Ordered",
        "report_key": "ordered",
        "params": {"period": "mtd", "customers": ["9300", "9301"]},
        "cadence": {"freq": "monthly", "time": "19:59", "monthdays": [-1]},
        "sharepoint_path": "Amazon Weekly",
    },
    {
        "name": "Weekly 5pm Friday Amazon Ordered",
        "report_key": "ordered",
        "params": {"period": "last_7_days", "customers": ["9300", "9301"]},
        "cadence": {"freq": "weekly", "time": "00:00", "weekdays": [3]},
        "sharepoint_path": "Amazon Weekly",
    },
]


def _seed_master_schedules(app: Flask, db, rows: list[dict] | None = None,
                           *, inactive: bool = False) -> None:
    """Insert missing master_schedules. Existing and operator-deleted names stay put."""
    import sqlite3

    from web.data.repositories.schedules import MasterScheduleRepository
    from web.delivery.sharepoint import strip_reports_home
    from web.scheduling import cadence as C

    try:
        from web.data.repositories.app_settings import AppSettingsRepository

        repo = MasterScheduleRepository(db)
        skipped = AppSettingsRepository(db).skipped_seed_names()
        existing = {s.name for s in repo.list_all()}
        added = 0
        for s in (rows if rows is not None else _AZURE_SCHEDULES):
            if s["name"] in existing or s["name"] in skipped:
                continue
            try:
                repo.create(
                    s["report_key"], s["name"],
                    params=s.get("params", {}), layout=s.get("layout") or {},
                    cadence=C.normalize(s.get("cadence") or {"freq": "daily", "time": "08:00"}),
                    sharepoint_path=strip_reports_home(s.get("sharepoint_path", "")),
                    is_shared=True,
                    is_active=not inactive,
                )
            except sqlite3.IntegrityError:
                continue
            existing.add(s["name"])
            added += 1
        for s in (rows if rows is not None else _AZURE_SCHEDULES):
            layout = s.get("layout") or {}
            if layout.get("order"):
                repo.fill_layout_if_blank(s["name"], layout)
            if (s.get("params") or {}).get("split_by_salesman"):
                repo.enable_split_all_if_plain(s["name"])
        if added:
            state = "disabled" if inactive else "active"
            app.logger.info("seeded %d master schedules (%s) from Azure config", added, state)
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("master schedule seed failed")


def _seed_company_views(app: Flask, db) -> None:
    try:
        from web.scheduling.company_layouts import seed_canonical_company_views

        seed_canonical_company_views(db)
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("company view seed failed")
