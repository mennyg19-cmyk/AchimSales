"""Copy People, views, and schedules from a live precious.db into this site.

Opt-in. Existing emails stay. Dummy views and schedules are wiped first.
Reads the same column tables the old GUI/clock assembled from
(views + view_* + layout_* + report_schedules + schedule_* children).
Does not read or store JSON blob tables (saved_reports, company_views,
report_defaults, master_schedules, params_json / layout_json). Those are
dropped on this site if they still exist.

  python3 import_precious.py /path/to/precious.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import cadence
import catalog
import config
from db import db, init_db
from store import hydrate_schedule_row

ROLES = {"admin", "developer", "manager", "salesman"}
KNOWN_REPORTS = {item["key"] for item in catalog.REPORTS}
SETTING_KEYS = {
    "schedule_test_mode",
    "test_emails",
    "show_company_schedule_setup",
}
SECRET_BITS = ("secret", "password", "token", "key")
REPORT_KEY_ALIASES = {
    "customer_last_orders": "customer_last_order",
    "last_order": "customer_last_order",
    "invoiced_report": "invoiced",
    "ordered_report": "ordered",
}


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _open_src(path: Path) -> sqlite3.Connection:
    src = sqlite3.connect(str(path.resolve()))
    src.row_factory = sqlite3.Row
    return src


def _user_maps(src: sqlite3.Connection) -> tuple[dict[int, str], dict[str, str], set[str]]:
    user_cols = _cols(src, "users")
    by_id: dict[int, str] = {}
    by_handle: dict[str, str] = {}
    emails: set[str] = set()
    for row in src.execute("SELECT * FROM users"):
        email = (row["email"] or "").strip().lower()
        if not email:
            continue
        by_id[int(row["id"])] = email
        emails.add(email)
        if "handle" in user_cols and row["handle"]:
            by_handle[str(row["handle"]).strip().lower()] = email
        by_handle[email] = email
        local = email.split("@", 1)[0]
        if local:
            by_handle.setdefault(local.lower(), email)
    return by_id, by_handle, emails


def _map_report_key(raw) -> str:
    key = str(raw or "").strip()
    return REPORT_KEY_ALIASES.get(key, key)


def _lookup_owner(by_handle: dict[str, str], *candidates, fallback: str) -> str:
    for raw in candidates:
        token = str(raw or "").strip()
        if not token:
            continue
        hit = by_handle.get(token.lower())
        if hit:
            return hit
        if "@" in token:
            return token.lower()
    return fallback


def _wipe_views_and_schedules(dest: sqlite3.Connection) -> None:
    dest.execute("DELETE FROM schedule_runs")
    dest.execute("DELETE FROM schedule_weekdays")
    dest.execute("DELETE FROM schedule_monthdays")
    dest.execute("DELETE FROM schedule_recipients")
    dest.execute("DELETE FROM schedule_email_salesmen")
    dest.execute("DELETE FROM schedules")
    dest.execute("DELETE FROM layout_column_filters")
    dest.execute("DELETE FROM layout_columns")
    dest.execute("DELETE FROM layout_tab_groups")
    dest.execute("DELETE FROM layout_tab_sorters")
    dest.execute("DELETE FROM layout_tabs")
    dest.execute("DELETE FROM view_salesmen")
    dest.execute("DELETE FROM view_statuses")
    dest.execute("DELETE FROM view_customers")
    dest.execute("DELETE FROM views")


def _copy_paired_rows(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    table: str,
    src_key: str,
    src_id,
    dest_id: int,
    columns: list[str],
    dest_key: str | None = None,
) -> None:
    dest_key = dest_key or src_key
    present = [name for name in columns if name in _cols(src, table)]
    if not present:
        return
    cols = ", ".join(present)
    placeholders = ", ".join("?" for _ in present)
    for row in src.execute(
        f"SELECT {cols} FROM {table} WHERE {src_key} = ?",
        (src_id,),
    ):
        dest.execute(
            f"INSERT OR IGNORE INTO {table} ({dest_key}, {cols}) VALUES (?, {placeholders})",
            (dest_id, *[row[name] for name in present]),
        )


def _insert_view(
    dest: sqlite3.Connection,
    *,
    owner_email: str | None,
    report_key: str,
    name: str,
    kind: str,
    include_period: int,
    period: str | None,
    start_date: str | None,
    end_date: str | None,
    year: str | None,
    mode: str | None,
    active_tab_key: str | None,
) -> int:
    dest.execute(
        """INSERT INTO views (
               owner_email, report_key, name, kind, include_period,
               period, start_date, end_date, year, mode, active_tab_key
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_email, report_key, name, kind, include_period,
            period, start_date, end_date, year, mode, active_tab_key,
        ),
    )
    return int(dest.execute("SELECT last_insert_rowid()").fetchone()[0])


def _copy_view_children(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    src_id,
    dest_id: int,
    tables: set[str],
) -> None:
    if "view_salesmen" in tables:
        _copy_paired_rows(
            src, dest, "view_salesmen", "view_id", src_id, dest_id, ["salesman"]
        )
    if "view_statuses" in tables:
        _copy_paired_rows(
            src, dest, "view_statuses", "view_id", src_id, dest_id, ["status"]
        )
    if "view_customers" in tables:
        _copy_paired_rows(
            src, dest, "view_customers", "view_id", src_id, dest_id, ["customer_account"]
        )
    if "layout_tabs" not in tables:
        return
    tab_cols = _cols(src, "layout_tabs")
    tab_map: dict[str, int] = {}
    for tab in src.execute(
        "SELECT * FROM layout_tabs WHERE view_id = ? ORDER BY position, id",
        (src_id,),
    ):
        dest.execute(
            """INSERT INTO layout_tabs (
                   view_id, tab_key, position, clone_of_tab_key, tab_name, has_view, groups_explicit
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                dest_id,
                tab["tab_key"],
                tab["position"] if "position" in tab_cols else None,
                tab["clone_of_tab_key"] if "clone_of_tab_key" in tab_cols else None,
                tab["tab_name"] if "tab_name" in tab_cols else None,
                int(tab["has_view"] or 0) if "has_view" in tab_cols else 0,
                int(tab["groups_explicit"] if tab["groups_explicit"] is not None else 1)
                if "groups_explicit" in tab_cols
                else 1,
            ),
        )
        tab_map[str(tab["id"])] = int(dest.execute("SELECT last_insert_rowid()").fetchone()[0])
    for src_tab_id, dest_tab_id in tab_map.items():
        if "layout_tab_groups" in tables:
            _copy_paired_rows(
                src, dest, "layout_tab_groups", "tab_id", src_tab_id, dest_tab_id,
                ["position", "column_name"],
            )
        if "layout_tab_sorters" in tables:
            for row in src.execute(
                """SELECT position, column_name, dir FROM layout_tab_sorters
                   WHERE tab_id = ? ORDER BY position""",
                (src_tab_id,),
            ):
                direction = row["dir"] if row["dir"] in {"asc", "desc"} else "asc"
                dest.execute(
                    """INSERT OR IGNORE INTO layout_tab_sorters
                       (tab_id, position, column_name, dir) VALUES (?, ?, ?, ?)""",
                    (dest_tab_id, row["position"], row["column_name"], direction),
                )
        if "layout_columns" in tables:
            _copy_paired_rows(
                src, dest, "layout_columns", "tab_id", src_tab_id, dest_tab_id,
                ["field", "position", "hidden", "frozen", "width"],
            )
        if "layout_column_filters" in tables:
            _copy_paired_rows(
                src, dest, "layout_column_filters", "tab_id", src_tab_id, dest_tab_id,
                ["field", "op", "v", "v2"],
            )


def _import_users(src: sqlite3.Connection, dest: sqlite3.Connection) -> dict:
    user_cols = _cols(src, "users")
    tables = _tables(src)
    extra_groups: dict[int, list[str]] = {}
    if "user_sales_groups" in tables:
        for row in src.execute("SELECT user_id, sales_group FROM user_sales_groups"):
            extra_groups.setdefault(int(row["user_id"]), []).append(row["sales_group"])
    elif "user_salesman_access" in tables:
        for row in src.execute("SELECT user_id, salesman_key FROM user_salesman_access"):
            extra_groups.setdefault(int(row["user_id"]), []).append(row["salesman_key"])
    report_access: list[tuple[str, str, int]] = []
    if "user_report_access" in tables:
        for row in src.execute(
            """SELECT u.email, a.report_key, a.allowed
               FROM user_report_access a JOIN users u ON u.id = a.user_id"""
        ):
            report_access.append((row["email"].lower(), row["report_key"], int(row["allowed"])))
    themes: dict[str, str] = {}
    if "user_preferences" in tables:
        for row in src.execute(
            """SELECT u.email, p.theme FROM user_preferences p
               JOIN users u ON u.id = p.user_id"""
        ):
            themes[row["email"].lower()] = row["theme"] or "light"
    dest_emails = {row["email"] for row in dest.execute("SELECT email FROM users")}
    inserted = 0
    skipped = 0
    for row in src.execute("SELECT * FROM users ORDER BY id"):
        email = (row["email"] or "").strip().lower()
        if not email:
            continue
        if email in dest_emails:
            skipped += 1
            continue
        role = row["role"] if row["role"] in ROLES else "salesman"
        sales_group = row["sales_group"] if "sales_group" in user_cols else ""
        extras = extra_groups.get(int(row["id"]), [])
        if not sales_group and extras:
            sales_group = extras[0]
            extras = extras[1:]
        theme = themes.get(email) or (row["theme"] if "theme" in user_cols else "light")
        dest.execute(
            """INSERT INTO users (
                   email, display_name, role, is_active, is_external,
                   sales_group, can_see_company_views, sharepoint_access,
                   dashboard_enabled, test_access, theme
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email,
                row["display_name"] or email,
                role,
                int(row["is_active"] if "is_active" in user_cols else 1),
                int(row["is_external"] if "is_external" in user_cols else 0),
                sales_group or "",
                int(row["can_see_company_views"] if "can_see_company_views" in user_cols else 0),
                int(row["sharepoint_access"] if "sharepoint_access" in user_cols else 0),
                int(row["dashboard_enabled"] if "dashboard_enabled" in user_cols else 0),
                int(row["test_access"] if "test_access" in user_cols else 0),
                theme if theme in {"light", "dark", "monochrome", "monochrome_dark"} else "light",
            ),
        )
        new_id = dest.execute("SELECT last_insert_rowid()").fetchone()[0]
        for group in extras:
            if group:
                dest.execute(
                    "INSERT OR IGNORE INTO user_sales_groups (user_id, sales_group) VALUES (?, ?)",
                    (new_id, group),
                )
        dest_emails.add(email)
        inserted += 1
    email_to_id = {row["email"]: row["id"] for row in dest.execute("SELECT id, email FROM users")}
    for email, report_key, allowed in report_access:
        uid = email_to_id.get(email)
        if not uid:
            continue
        dest.execute(
            """INSERT OR IGNORE INTO user_report_access (user_id, report_key, allowed)
               VALUES (?, ?, ?)""",
            (uid, report_key, allowed),
        )
    return {"inserted": inserted, "skipped": skipped}


def _import_normalized_views(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    by_handle: dict[str, str],
) -> tuple[dict, dict]:
    tables = _tables(src)
    view_cols = _cols(src, "views")
    id_map: dict[str, int] = {}
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    fallback = _fallback_owner(dest)
    for row in src.execute("SELECT * FROM views"):
        report_key = _map_report_key(row["report_key"])
        if not report_key:
            counts["skipped"] += 1
            continue
        kind = row["kind"] if row["kind"] in {"personal", "company", "default"} else "personal"
        owner = None
        if kind == "personal":
            handle = row["owner_handle"] if "owner_handle" in view_cols else None
            email_col = row["owner_email"] if "owner_email" in view_cols else None
            owner = _lookup_owner(by_handle, handle, email_col, fallback=fallback)
        period = row["period"] if "period" in view_cols else None
        start_date = row["start_date"] if "start_date" in view_cols else None
        end_date = row["end_date"] if "end_date" in view_cols else None
        year = row["year"] if "year" in view_cols else None
        mode = row["mode"] if "mode" in view_cols else None
        include = 1 if (period or start_date or end_date) else 0
        if "include_period" in view_cols and row["include_period"] is not None:
            include = int(row["include_period"])
        dest_id = _insert_view(
            dest,
            owner_email=owner,
            report_key=report_key,
            name=row["name"] or "Imported view",
            kind=kind,
            include_period=include,
            period=period,
            start_date=start_date,
            end_date=end_date,
            year=year,
            mode=mode,
            active_tab_key=row["active_tab_key"] if "active_tab_key" in view_cols else None,
        )
        _copy_view_children(src, dest, row["id"], dest_id, tables)
        id_map[str(row["id"])] = dest_id
        counts["inserted"] += 1
    return id_map, counts


def _insert_schedule(
    dest: sqlite3.Connection,
    *,
    view_id: int,
    owner_email: str,
    name: str,
    kind: str,
    freq: str,
    run_time: str,
    weekdays: str,
    monthday: int | None,
    recipients: str,
    cc: str,
    bcc: str,
    subject: str,
    filename: str,
    sharepoint_folder: str,
    onedrive_folder: str,
    is_active: int,
    last_run: str | None,
    catch_up_pending: int,
    catch_up_for_date: str | None,
) -> int:
    dest.execute(
        """INSERT INTO schedules (
               view_id, owner_email, name, kind, freq, run_time, weekdays, monthday,
               recipients, cc, bcc, subject, filename, sharepoint_folder, onedrive_folder,
               is_active, last_run, catch_up_pending, catch_up_for_date
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            view_id, owner_email, name or "", kind, freq, run_time, weekdays, monthday,
            recipients, cc, bcc, subject, filename, sharepoint_folder, onedrive_folder,
            is_active, last_run, catch_up_pending, catch_up_for_date,
        ),
    )
    return int(dest.execute("SELECT last_insert_rowid()").fetchone()[0])


def _copy_schedule_children(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    src_id,
    dest_id: int,
    tables: set[str],
) -> None:
    if "schedule_weekdays" in tables:
        for row in src.execute(
            "SELECT weekday FROM schedule_weekdays WHERE schedule_id = ? ORDER BY weekday",
            (src_id,),
        ):
            dest.execute(
                "INSERT OR IGNORE INTO schedule_weekdays (schedule_id, weekday) VALUES (?, ?)",
                (dest_id, int(row["weekday"])),
            )
    if "schedule_monthdays" in tables:
        for row in src.execute(
            "SELECT monthday FROM schedule_monthdays WHERE schedule_id = ? ORDER BY monthday",
            (src_id,),
        ):
            dest.execute(
                "INSERT OR IGNORE INTO schedule_monthdays (schedule_id, monthday) VALUES (?, ?)",
                (dest_id, int(row["monthday"])),
            )
    if "schedule_recipients" in tables:
        for row in src.execute(
            "SELECT email, role FROM schedule_recipients WHERE schedule_id = ?",
            (src_id,),
        ):
            email = (row["email"] or "").strip().lower()
            if "@" not in email:
                continue
            role = row["role"] if row["role"] in {"to", "cc", "bcc"} else "to"
            dest.execute(
                """INSERT OR IGNORE INTO schedule_recipients (schedule_id, email, role)
                   VALUES (?, ?, ?)""",
                (dest_id, email, role),
            )
    if "schedule_email_salesmen" in tables:
        for row in src.execute(
            "SELECT salesman FROM schedule_email_salesmen WHERE schedule_id = ?",
            (src_id,),
        ):
            salesman = (row["salesman"] or "").strip()
            if salesman:
                dest.execute(
                    """INSERT OR IGNORE INTO schedule_email_salesmen (schedule_id, salesman)
                       VALUES (?, ?)""",
                    (dest_id, salesman),
                )


def _sync_schedule_csv(dest: sqlite3.Connection, schedule_id: int) -> None:
    row = dest.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    hydrated = hydrate_schedule_row(row, dest)
    dest.execute(
        """UPDATE schedules SET weekdays = ?, monthday = ?, recipients = ?, cc = ?, bcc = ?
           WHERE id = ?""",
        (
            hydrated.get("weekdays") or "",
            hydrated.get("monthday"),
            hydrated.get("recipients") or "",
            hydrated.get("cc") or "",
            hydrated.get("bcc") or "",
            schedule_id,
        ),
    )


def _is_dummy_owner(email: str) -> bool:
    lower = (email or "").strip().lower()
    if not lower or lower.startswith("preview@"):
        return True
    return lower.endswith(("@local.test", "@test.local", "@example.com"))


def _fallback_owner(dest: sqlite3.Connection) -> str:
    rows = dest.execute(
        """SELECT email FROM users
           WHERE role IN ('admin', 'developer') AND is_active = 1
           ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, id"""
    ).fetchall()
    for row in rows:
        if not _is_dummy_owner(row["email"]):
            return row["email"]
    row = dest.execute(
        """SELECT email FROM users WHERE is_active = 1 ORDER BY id"""
    ).fetchone()
    if row and not _is_dummy_owner(row["email"]):
        return row["email"]
    row = dest.execute("SELECT email FROM users ORDER BY id LIMIT 1").fetchone()
    return row["email"] if row else "preview@achimonline.com"


def _import_report_schedules(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    view_map: dict[str, int],
    by_handle: dict[str, str],
) -> dict:
    tables = _tables(src)
    cols = _cols(src, "report_schedules")
    dest_cols = _cols(dest, "schedules")
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    fallback = _fallback_owner(dest)
    for row in src.execute("SELECT * FROM report_schedules"):
        view_id = view_map.get(str(row["view_id"]))
        if not view_id:
            counts["skipped"] += 1
            continue
        freq = (row["freq"] or "daily").lower()
        if freq not in cadence.VALID_FREQ:
            freq = "daily"
        run_time = row["time"] if "time" in cols else "08:00"
        owner = _lookup_owner(by_handle, row["owner_handle"] if "owner_handle" in cols else None, fallback=fallback)
        folder = row["sharepoint_path"] if "sharepoint_path" in cols else ""
        folder_kind = row["folder_kind"] if "folder_kind" in cols else "sharepoint"
        sharepoint = folder if folder_kind != "onedrive" else ""
        onedrive = folder if folder_kind == "onedrive" else ""
        sched_kind = row["kind"] if "kind" in cols and row["kind"] in {"personal", "company"} else "personal"
        dest_id = _insert_schedule(
            dest,
            view_id=view_id,
            owner_email=owner,
            name=row["name"] if "name" in cols else "",
            kind=sched_kind,
            freq=freq,
            run_time=run_time or "08:00",
            weekdays="",
            monthday=None,
            recipients="",
            cc="",
            bcc="",
            subject=row["email_subject"] if "email_subject" in cols else "",
            filename=row["filename_template"] if "filename_template" in cols else "",
            sharepoint_folder=sharepoint or "",
            onedrive_folder=onedrive or "",
            is_active=int(row["is_active"] if "is_active" in cols else 1),
            last_run=row["last_claimed_at"] if "last_claimed_at" in cols else None,
            catch_up_pending=int(row["catch_up_pending"] if "catch_up_pending" in cols else 0),
            catch_up_for_date=row["catch_up_for_date"] if "catch_up_for_date" in cols else None,
        )
        _copy_schedule_children(src, dest, row["id"], dest_id, tables)
        _sync_schedule_csv(dest, dest_id)
        extras = {
            "split_by_salesman": int(row["split_by_salesman"] or 0)
            if "split_by_salesman" in cols else None,
            "email_to_salesmen": int(row["email_to_salesmen"] or 0)
            if "email_to_salesmen" in cols else None,
            "window_period": (str(row["window_period"]).strip() or None)
            if "window_period" in cols and row["window_period"] else None,
            "window_start": (str(row["window_start"]).strip() or None)
            if "window_start" in cols and row["window_start"] else None,
            "window_end": (str(row["window_end"]).strip() or None)
            if "window_end" in cols and row["window_end"] else None,
        }
        for name, value in extras.items():
            if name in dest_cols and value is not None:
                dest.execute(f"UPDATE schedules SET {name} = ? WHERE id = ?", (value, dest_id))
        counts["inserted"] += 1
    return counts


JSON_GARBAGE_TABLES = (
    "saved_reports",
    "company_views",
    "report_defaults",
    "master_schedules",
    "view_workbook_parity",
)
# Live GUI/clock reads views via assemble_params + assemble_layout, and
# schedules via report_schedules plus these four children. JSON tables are leftover.
# Fingerprint of live home sqlite (BETA_PRECIOUS_DB_PATH /tmp/betadata).
# /tmp/v3data is the /test seed, not the home site.
LIVE_ASSEMBLE_MIN = {
    "views": 50,
    "report_schedules": 30,
    "layout_tabs": 100,
}
ASSEMBLE_TABLES = (
    "views",
    "view_salesmen",
    "view_statuses",
    "view_customers",
    "layout_tabs",
    "layout_tab_groups",
    "layout_tab_sorters",
    "layout_columns",
    "layout_column_filters",
    "report_schedules",
    "schedule_weekdays",
    "schedule_monthdays",
    "schedule_recipients",
    "schedule_email_salesmen",
)


def _assemble_counts(conn: sqlite3.Connection, *, dest: bool = False) -> dict[str, int]:
    tables = _tables(conn)
    out: dict[str, int] = {}
    for name in ASSEMBLE_TABLES:
        lookup = name
        if dest and name == "report_schedules":
            lookup = "report_schedules" if "report_schedules" in tables else "schedules"
        out[name] = (
            int(conn.execute(f"SELECT COUNT(*) FROM {lookup}").fetchone()[0])
            if lookup in tables
            else 0
        )
    return out


def _drop_json_tables(dest: sqlite3.Connection) -> list[str]:
    dropped = []
    present = _tables(dest)
    for name in JSON_GARBAGE_TABLES:
        if name in present:
            dest.execute(f"DROP TABLE IF EXISTS {name}")
            dropped.append(name)
    return dropped


def _import_visibility(src: sqlite3.Connection, dest: sqlite3.Connection) -> int:
    tables = _tables(src)
    table = "report_config" if "report_config" in tables else (
        "report_visibility" if "report_visibility" in tables else None
    )
    if not table:
        return 0
    n = 0
    for row in src.execute(f"SELECT report_key, enabled FROM {table}"):
        if row["report_key"] not in KNOWN_REPORTS:
            continue
        dest.execute(
            """INSERT INTO report_visibility (report_key, enabled) VALUES (?, ?)
               ON CONFLICT(report_key) DO UPDATE SET enabled = excluded.enabled""",
            (row["report_key"], int(row["enabled"])),
        )
        n += 1
    return n


def _import_settings(src: sqlite3.Connection, dest: sqlite3.Connection) -> int:
    if "app_settings" not in _tables(src):
        return 0
    n = 0
    for row in src.execute("SELECT key, value FROM app_settings"):
        key = row["key"] or ""
        lower = key.lower()
        if any(bit in lower for bit in SECRET_BITS) and key not in SETTING_KEYS:
            continue
        if key not in SETTING_KEYS:
            continue
        dest.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, row["value"] or ""),
        )
        n += 1
    return n


def import_precious(source_path: Path, dest_path: Path | None = None) -> dict:
    if dest_path is not None:
        os.environ["APP_DB_PATH"] = str(dest_path)
    init_db()
    src = _open_src(source_path)
    try:
        if "users" not in _tables(src):
            raise ValueError(f"{source_path} has no users table.")
        with db() as dest:
            _drop_json_tables(dest)
            users = _import_users(src, dest)
            _, by_handle, _ = _user_maps(src)
            _wipe_views_and_schedules(dest)
            view_map: dict[str, int] = {}
            views = {"inserted": 0, "updated": 0, "skipped": 0}
            schedules = {"inserted": 0, "updated": 0, "skipped": 0}
            source_tables = _assemble_counts(src)
            source_views = source_tables["views"]
            source_schedules = source_tables["report_schedules"]
            if source_views:
                view_map, views = _import_normalized_views(src, dest, by_handle)
            if source_schedules:
                schedules = _import_report_schedules(src, dest, view_map, by_handle)
            visibility = _import_visibility(src, dest)
            settings = _import_settings(src, dest)
            dropped = _drop_json_tables(dest)
            dest_tables = _assemble_counts(dest, dest=True)
    finally:
        src.close()
    return {
        "users_inserted": users["inserted"],
        "users_skipped": users["skipped"],
        "views_inserted": views["inserted"],
        "views_updated": views["updated"],
        "views_skipped": views["skipped"],
        "schedules_inserted": schedules["inserted"],
        "schedules_updated": schedules["updated"],
        "schedules_skipped": schedules["skipped"],
        "source_views": source_views,
        "source_schedules": source_schedules,
        "source_tables": source_tables,
        "dest_tables": dest_tables,
        "dropped_json_tables": dropped,
        "visibility": visibility,
        "settings": settings,
    }


def import_users(source_path: Path, dest_path: Path | None = None) -> dict:
    result = import_precious(source_path, dest_path)
    return {"inserted": result["users_inserted"], "skipped": result["users_skipped"]}


def summarize(result: dict) -> str:
    tables = result.get("source_tables") or {}
    dest = result.get("dest_tables") or {}
    bits = ", ".join(f"{name} {tables.get(name, 0)}→{dest.get(name, 0)}" for name in ASSEMBLE_TABLES)
    text = (
        f"People {result['users_inserted']} added, {result['users_skipped']} already here. "
        f"Dummy views/schedules cleared. "
        f"Copied assemble tables (live→here): {bits}."
    )
    dropped = result.get("dropped_json_tables") or []
    if dropped:
        text += f" Dropped JSON tables: {', '.join(dropped)}."
    skipped = result["views_skipped"] + result["schedules_skipped"]
    if skipped:
        text += (
            f" Skipped {result['views_skipped']} views, "
            f"{result['schedules_skipped']} schedules (no matching view/report)."
        )
    if (
        tables.get("views", 0) < LIVE_ASSEMBLE_MIN["views"]
        or tables.get("report_schedules", 0) < LIVE_ASSEMBLE_MIN["report_schedules"]
        or tables.get("layout_tabs", 0) < LIVE_ASSEMBLE_MIN["layout_tabs"]
    ):
        text += (
            " This file looks like /test /tmp/v3data (about 9 views), not the "
            "home site BETA_PRECIOUS_DB_PATH /tmp/betadata/precious.db (about "
            "97 views, 58 report_schedules, 592 layout_tabs). SSH-backup that "
            "file and import again."
        )
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import People, views, and schedules from a v3 precious.db"
    )
    parser.add_argument("precious", type=Path, help="Path to live precious.db (read-only)")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination sqlite (default APP_DB_PATH / app/data/home.sqlite)",
    )
    args = parser.parse_args(argv)
    if not args.precious.is_file():
        print(f"No file at {args.precious}", file=sys.stderr)
        return 2
    dest = args.dest or config.db_path()
    result = import_precious(args.precious, dest)
    print(f"{summarize(result)} into {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
