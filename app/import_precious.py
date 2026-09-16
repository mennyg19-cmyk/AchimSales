"""Copy People, views, and schedules from a live precious.db into this site.

Opt-in. Existing emails stay. Dummy views and schedules are wiped first.
Writes only column tables on this site (views, layout_*, view_*,
schedules, schedule_weekdays/monthdays/recipients/email_salesmen).
Reads live column tables first, then fills gaps from JSON backup tables
(saved_reports, company_views, report_defaults, schedules, master_schedules)
without storing those blobs.

  python3 import_precious.py /path/to/precious.db
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import cadence
import catalog
import config
from db import db, init_db
from store import hydrate_schedule_row, write_schedule_children, _weekday_csv
from views import save_filters_and_layout

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
) -> tuple[dict, dict[tuple[str, int], int]]:
    tables = _tables(src)
    cols = _cols(src, "report_schedules")
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    legacy_map: dict[tuple[str, int], int] = {}
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
        window = row["window_period"] if "window_period" in cols else None
        if window:
            dest.execute(
                """UPDATE views SET period = COALESCE(NULLIF(period, ''), ?), include_period = 1
                   WHERE id = ?""",
                (window, view_id),
            )
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
        if "legacy_kind" in cols and "legacy_id" in cols and row["legacy_kind"] and row["legacy_id"] is not None:
            legacy_map[(str(row["legacy_kind"]), int(row["legacy_id"]))] = dest_id
        counts["inserted"] += 1
    return counts, legacy_map


def _json_obj(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _as_str_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
    return []


SOURCE_COUNT_TABLES = (
    "views",
    "report_schedules",
    "saved_reports",
    "company_views",
    "report_defaults",
    "schedules",
    "master_schedules",
)


def _source_table_counts(src: sqlite3.Connection) -> dict[str, int]:
    tables = _tables(src)
    out: dict[str, int] = {}
    for name in SOURCE_COUNT_TABLES:
        out[name] = (
            int(src.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            if name in tables
            else 0
        )
    return out


def _json_backup_counts(src: sqlite3.Connection) -> tuple[int, int]:
    counts = _source_table_counts(src)
    views = counts["saved_reports"] + counts["company_views"] + counts["report_defaults"]
    schedules = counts["schedules"] + counts["master_schedules"]
    return views, schedules


def _projected_view_keys(src: sqlite3.Connection) -> set[tuple[str, int]]:
    tables = _tables(src)
    if "views" not in tables:
        return set()
    cols = _cols(src, "views")
    if "legacy_source" not in cols or "legacy_id" not in cols:
        return set()
    out = set()
    for row in src.execute("SELECT legacy_source, legacy_id FROM views"):
        if row["legacy_source"] and row["legacy_id"] is not None:
            out.add((str(row["legacy_source"]), int(row["legacy_id"])))
    return out


def _existing_view_id(
    dest: sqlite3.Connection,
    kind: str,
    report_key: str,
    name: str,
    owner_email: str | None,
) -> int | None:
    if kind == "personal":
        row = dest.execute(
            """SELECT id FROM views
               WHERE kind = 'personal' AND report_key = ? AND name = ? AND owner_email = ?""",
            (report_key, name, owner_email),
        ).fetchone()
    else:
        row = dest.execute(
            """SELECT id FROM views
               WHERE kind = ? AND report_key = ? AND name = ? AND owner_email IS NULL""",
            (kind, report_key, name),
        ).fetchone()
    return int(row["id"]) if row else None


def _ensure_view_from_json(
    dest: sqlite3.Connection,
    *,
    kind: str,
    report_key: str,
    name: str,
    owner_email: str | None,
    params_raw,
    layout_raw,
) -> tuple[int, str]:
    existing = _existing_view_id(dest, kind, report_key, name, owner_email)
    if existing:
        return existing, "skipped"
    filters = _json_obj(params_raw)
    if not filters.get("from_date") and filters.get("start_date"):
        filters["from_date"] = filters["start_date"]
    if not filters.get("to_date") and filters.get("end_date"):
        filters["to_date"] = filters["end_date"]
    layout = _json_obj(layout_raw)
    include = 1 if (
        filters.get("period") or filters.get("from_date") or filters.get("to_date")
        or filters.get("start_date") or filters.get("end_date")
    ) else 0
    dest_id = _insert_view(
        dest,
        owner_email=owner_email,
        report_key=report_key,
        name=name or "Imported view",
        kind=kind,
        include_period=include,
        period=filters.get("period"),
        start_date=filters.get("from_date") or filters.get("start_date"),
        end_date=filters.get("to_date") or filters.get("end_date"),
        year=filters.get("year"),
        mode=filters.get("n4_mode") or filters.get("mode"),
        active_tab_key=layout.get("active") if isinstance(layout.get("active"), str) else None,
    )
    save_filters_and_layout(dest, dest_id, filters, layout, include)
    return dest_id, "inserted"


def _import_json_views(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    by_id: dict[int, str],
) -> tuple[dict[str, int], dict]:
    tables = _tables(src)
    projected = _projected_view_keys(src)
    id_map: dict[str, int] = {}
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    fallback = _fallback_owner(dest)

    def add(kind: str, report_key: str, name: str, owner: str | None, params_raw, layout_raw, source: str, legacy_id: int):
        report_key = _map_report_key(report_key)
        if not report_key:
            counts["skipped"] += 1
            return
        if (source, int(legacy_id)) in projected:
            existing = _existing_view_id(dest, kind, report_key, name or "Imported view", owner)
            if existing:
                id_map[f"{source}:{legacy_id}"] = existing
            counts["skipped"] += 1
            return
        view_id, action = _ensure_view_from_json(
            dest,
            kind=kind,
            report_key=report_key,
            name=name or "Imported view",
            owner_email=owner,
            params_raw=params_raw,
            layout_raw=layout_raw,
        )
        id_map[f"{source}:{legacy_id}"] = view_id
        counts[action] += 1

    if "saved_reports" in tables:
        sr_cols = _cols(src, "saved_reports")
        for row in src.execute("SELECT * FROM saved_reports"):
            owner = by_id.get(int(row["user_id"])) or fallback
            add(
                "personal",
                row["report_key"],
                row["name"],
                owner,
                row["params_json"] if "params_json" in sr_cols else None,
                row["layout_json"] if "layout_json" in sr_cols else None,
                "saved_reports",
                int(row["id"]),
            )
    if "company_views" in tables:
        cv_cols = _cols(src, "company_views")
        for row in src.execute("SELECT * FROM company_views"):
            add(
                "company",
                row["report_key"],
                row["name"],
                None,
                row["params_json"] if "params_json" in cv_cols else None,
                row["layout_json"] if "layout_json" in cv_cols else None,
                "company_views",
                int(row["id"]),
            )
    if "report_defaults" in tables:
        rd_cols = _cols(src, "report_defaults")
        for row in src.execute("SELECT * FROM report_defaults"):
            add(
                "default",
                row["report_key"],
                "Default",
                None,
                row["params_json"] if "params_json" in rd_cols else None,
                row["layout_json"] if "layout_json" in rd_cols else None,
                "report_defaults",
                int(row["id"]),
            )
    return id_map, counts


def _cadence_fields(raw) -> tuple[str, str, str, int | None]:
    data = _json_obj(raw)
    freq = str(data.get("freq") or "daily").lower()
    if freq not in cadence.VALID_FREQ:
        freq = "daily"
    run_time = str(data.get("time") or "08:00")
    weekdays = _weekday_csv([int(d) for d in (data.get("weekdays") or [])])
    monthday = None
    if data.get("monthday") not in (None, ""):
        monthday = int(data["monthday"])
    elif data.get("monthdays"):
        monthday = int(data["monthdays"][0])
    return freq, run_time, weekdays, monthday


def _find_view_for_json_schedule(
    dest: sqlite3.Connection,
    report_key: str,
    view_name: str,
    owner: str | None,
) -> int | None:
    name = view_name or "Default"
    if owner:
        row = dest.execute(
            """SELECT id FROM views
               WHERE report_key = ? AND name = ? AND owner_email = ?
               ORDER BY id LIMIT 1""",
            (report_key, name, owner),
        ).fetchone()
        if row:
            return int(row["id"])
    row = dest.execute(
        """SELECT id FROM views
           WHERE report_key = ? AND name = ? AND owner_email IS NULL
           ORDER BY CASE kind WHEN 'company' THEN 0 WHEN 'default' THEN 1 ELSE 2 END, id
           LIMIT 1""",
        (report_key, name),
    ).fetchone()
    if row:
        return int(row["id"])
    row = dest.execute(
        """SELECT id FROM views WHERE report_key = ? AND name = ? ORDER BY id LIMIT 1""",
        (report_key, name),
    ).fetchone()
    return int(row["id"]) if row else None


def _schedule_children_empty(dest: sqlite3.Connection, schedule_id: int) -> bool:
    for table in (
        "schedule_recipients",
        "schedule_weekdays",
        "schedule_monthdays",
        "schedule_email_salesmen",
    ):
        if dest.execute(
            f"SELECT 1 FROM {table} WHERE schedule_id = ? LIMIT 1",
            (schedule_id,),
        ).fetchone():
            return False
    return True


def _overlay_json_schedule(
    dest: sqlite3.Connection,
    dest_id: int,
    row,
    cols: set[str],
    by_id: dict[int, str],
    fallback: str,
) -> None:
    current = dest.execute("SELECT * FROM schedules WHERE id = ?", (dest_id,)).fetchone()
    if current is None:
        return
    params = _json_obj(row["params_json"] if "params_json" in cols else None)
    freq, run_time, weekdays, monthday = _cadence_fields(
        row["cadence"] if "cadence" in cols else None
    )
    recipients = row["recipients"] if "recipients" in cols else ""
    cc = ", ".join(_as_str_list(params.get("email_cc")))
    bcc = ", ".join(_as_str_list(params.get("email_bcc")))
    salesmen = _as_str_list(params.get("email_salesman_keys"))
    owner = current["owner_email"]
    if _is_dummy_owner(owner) and "owner_user_id" in cols and row["owner_user_id"] is not None:
        owner = by_id.get(int(row["owner_user_id"])) or fallback
    elif _is_dummy_owner(owner) and not _is_dummy_owner(fallback):
        owner = fallback
    folder = row["sharepoint_path"] if "sharepoint_path" in cols else ""
    folder_kind = str(params.get("folder_kind") or "").strip()
    sharepoint = folder if folder_kind != "onedrive" else ""
    onedrive = folder if folder_kind == "onedrive" else ""
    dest.execute(
        """UPDATE schedules SET
               owner_email = ?,
               freq = COALESCE(NULLIF(freq, ''), ?),
               run_time = COALESCE(NULLIF(run_time, ''), ?),
               subject = COALESCE(NULLIF(subject, ''), ?),
               filename = COALESCE(NULLIF(filename, ''), ?),
               sharepoint_folder = COALESCE(NULLIF(sharepoint_folder, ''), ?),
               onedrive_folder = COALESCE(NULLIF(onedrive_folder, ''), ?)
           WHERE id = ?""",
        (
            owner,
            freq,
            run_time,
            str(params.get("email_subject") or ""),
            row["filename_template"] if "filename_template" in cols else "",
            sharepoint or "",
            onedrive or "",
            dest_id,
        ),
    )
    if _schedule_children_empty(dest, dest_id):
        write_schedule_children(
            dest,
            dest_id,
            weekdays=weekdays,
            monthday=monthday,
            recipients=recipients,
            cc=cc,
            bcc=bcc,
            salesmen=salesmen,
        )
        _sync_schedule_csv(dest, dest_id)


def _import_json_schedules(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    by_id: dict[int, str],
    dest_legacy_map: dict[tuple[str, int], int] | None = None,
) -> dict:
    tables = _tables(src)
    dest_legacy_map = dest_legacy_map or {}
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    fallback = _fallback_owner(dest)

    def ingest(table: str, legacy_kind: str, dest_kind: str) -> None:
        if table not in tables:
            return
        cols = _cols(src, table)
        for row in src.execute(f"SELECT * FROM {table}"):
            dest_id = dest_legacy_map.get((legacy_kind, int(row["id"])))
            if dest_id:
                _overlay_json_schedule(dest, dest_id, row, cols, by_id, fallback)
                counts["updated"] += 1
                continue
            report_key = _map_report_key(row["report_key"])
            if not report_key:
                counts["skipped"] += 1
                continue
            view_name = row["view_name"] if "view_name" in cols else (row["name"] if "name" in cols else "Default")
            owner = fallback
            if dest_kind == "personal" and "owner_user_id" in cols and row["owner_user_id"] is not None:
                owner = by_id.get(int(row["owner_user_id"])) or fallback
            elif dest_kind == "company" and "owner_user_id" in cols and row["owner_user_id"] is not None:
                owner = by_id.get(int(row["owner_user_id"])) or fallback
            params = _json_obj(row["params_json"] if "params_json" in cols else None)
            layout = _json_obj(row["layout_json"] if "layout_json" in cols else None)
            view_id = _find_view_for_json_schedule(dest, report_key, view_name or "Default", owner)
            if view_id is None:
                view_kind = "company" if dest_kind == "company" else "personal"
                view_id, _ = _ensure_view_from_json(
                    dest,
                    kind=view_kind,
                    report_key=report_key,
                    name=view_name or "Imported schedule view",
                    owner_email=None if view_kind == "company" else owner,
                    params_raw=params,
                    layout_raw=layout,
                )
            freq, run_time, weekdays, monthday = _cadence_fields(row["cadence"] if "cadence" in cols else None)
            cc = ", ".join(_as_str_list(params.get("email_cc")))
            bcc = ", ".join(_as_str_list(params.get("email_bcc")))
            salesmen = _as_str_list(params.get("email_salesman_keys"))
            folder = row["sharepoint_path"] if "sharepoint_path" in cols else ""
            folder_kind = str(params.get("folder_kind") or "").strip()
            sharepoint = folder if folder_kind != "onedrive" else ""
            onedrive = folder if folder_kind == "onedrive" else ""
            dest_id = _insert_schedule(
                dest,
                view_id=view_id,
                owner_email=owner,
                name=(row["name"] if "name" in cols and dest_kind == "company" else (view_name or "")),
                kind=dest_kind,
                freq=freq,
                run_time=run_time,
                weekdays=weekdays,
                monthday=monthday,
                recipients=row["recipients"] if "recipients" in cols else "",
                cc=cc,
                bcc=bcc,
                subject=str(params.get("email_subject") or ""),
                filename=row["filename_template"] if "filename_template" in cols else "",
                sharepoint_folder=sharepoint or "",
                onedrive_folder=onedrive or "",
                is_active=int(row["is_active"] if "is_active" in cols else 1),
                last_run=row["last_claimed_at"] if "last_claimed_at" in cols else None,
                catch_up_pending=int(row["catch_up_pending"] if "catch_up_pending" in cols else 0),
                catch_up_for_date=row["catch_up_for_date"] if "catch_up_for_date" in cols else None,
            )
            write_schedule_children(
                dest,
                dest_id,
                weekdays=weekdays,
                monthday=monthday,
                recipients=row["recipients"] if "recipients" in cols else "",
                cc=cc,
                bcc=bcc,
                salesmen=salesmen,
            )
            counts["inserted"] += 1

    ingest("schedules", "personal", "personal")
    ingest("master_schedules", "master", "company")
    return counts


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
            users = _import_users(src, dest)
            _by_id, by_handle, _emails = _user_maps(src)
            _wipe_views_and_schedules(dest)
            view_map: dict[str, int] = {}
            views = {"inserted": 0, "updated": 0, "skipped": 0}
            schedules = {"inserted": 0, "updated": 0, "skipped": 0}
            source_tables = _source_table_counts(src)
            source_views = source_tables["views"]
            source_schedules = source_tables["report_schedules"]
            blob_views, blob_schedules = _json_backup_counts(src)
            if source_views:
                view_map, views = _import_normalized_views(src, dest, by_handle)
            json_views_map, json_views = _import_json_views(src, dest, _by_id)
            view_map.update(json_views_map)
            views["inserted"] += json_views["inserted"]
            views["skipped"] += json_views["skipped"]
            sched_legacy: dict[tuple[str, int], int] = {}
            if source_schedules:
                schedules, sched_legacy = _import_report_schedules(src, dest, view_map, by_handle)
            json_schedules = _import_json_schedules(src, dest, _by_id, sched_legacy)
            schedules["inserted"] += json_schedules["inserted"]
            schedules["updated"] += json_schedules["updated"]
            schedules["skipped"] += json_schedules["skipped"]
            visibility = _import_visibility(src, dest)
            settings = _import_settings(src, dest)
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
        "blob_views": blob_views,
        "blob_schedules": blob_schedules,
        "source_tables": source_tables,
        "visibility": visibility,
        "settings": settings,
    }


def import_users(source_path: Path, dest_path: Path | None = None) -> dict:
    result = import_precious(source_path, dest_path)
    return {"inserted": result["users_inserted"], "skipped": result["users_skipped"]}


def summarize(result: dict) -> str:
    text = (
        f"People {result['users_inserted']} added, {result['users_skipped']} already here. "
        f"Dummy views/schedules cleared. "
        f"Column tables had {result['source_views']} views and {result['source_schedules']} schedules. "
        f"JSON backups had {result.get('blob_views', 0)} views and {result.get('blob_schedules', 0)} schedules. "
        f"Imported {result['views_inserted']} views and {result['schedules_inserted']} schedules into columns."
    )
    tables = result.get("source_tables") or {}
    if tables:
        bits = ", ".join(f"{name} {tables[name]}" for name in SOURCE_COUNT_TABLES)
        text += f" Live file tables: {bits}."
    filled = result.get("schedules_updated") or 0
    if filled:
        text += f" Filled {filled} column schedules from JSON backups."
    skipped = result["views_skipped"] + result["schedules_skipped"]
    if skipped:
        text += (
            f" Skipped {result['views_skipped']} views, "
            f"{result['schedules_skipped']} schedules (already in columns, or no report)."
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
