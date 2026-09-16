"""Copy People, views, and schedules from a live precious.db into this site.

Opt-in. Does not invent salesman maps. Existing emails stay. Matching
company/default view names get the live layout. Nightly work is site schedules.

  python3 import_precious.py /path/to/precious.db
  APP_DB_PATH=/tmp/home.sqlite python3 import_precious.py ./precious.db
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
from views import save_filters_and_layout

ROLES = {"admin", "developer", "manager", "salesman"}
KNOWN_REPORTS = {item["key"] for item in catalog.REPORTS}
SETTING_KEYS = {
    "schedule_test_mode",
    "test_emails",
    "show_company_schedule_setup",
}
SECRET_BITS = ("secret", "password", "token", "key")


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


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
            by_handle[str(row["handle"])] = email
        by_handle[email] = email
    return by_id, by_handle, emails


def _filters_from_children(src: sqlite3.Connection, tables: set[str], view_id) -> dict:
    filters: dict = {}
    if "view_salesmen" in tables:
        salesmen = [
            r["salesman"]
            for r in src.execute(
                "SELECT salesman FROM view_salesmen WHERE view_id = ? ORDER BY salesman",
                (view_id,),
            )
        ]
        if salesmen:
            filters["salesman"] = salesmen[0] if len(salesmen) == 1 else ""
            filters["salesmen"] = salesmen
    if "view_statuses" in tables:
        statuses = [
            r["status"]
            for r in src.execute(
                "SELECT status FROM view_statuses WHERE view_id = ? ORDER BY status",
                (view_id,),
            )
        ]
        if statuses:
            filters["status"] = statuses[0]
    if "view_customers" in tables:
        customers = [
            r["customer_account"]
            for r in src.execute(
                "SELECT customer_account FROM view_customers WHERE view_id = ? ORDER BY customer_account",
                (view_id,),
            )
        ]
        if customers:
            filters["customers"] = customers
    return filters


def _layout_from_children(src: sqlite3.Connection, tables: set[str], view_id) -> dict:
    if "layout_tabs" not in tables:
        return {}
    tab_cols = _cols(src, "layout_tabs")
    tabs = src.execute(
        """SELECT * FROM layout_tabs WHERE view_id = ? ORDER BY position, id""",
        (view_id,),
    ).fetchall()
    layout_views: dict = {}
    order: list[str] = []
    clones: list[dict] = []
    for tab in tabs:
        key = tab["tab_key"]
        if tab["position"] is not None:
            order.append(key)
        if tab["clone_of_tab_key"]:
            clones.append(
                {"key": key, "baseKey": tab["clone_of_tab_key"], "name": tab["tab_name"] or key}
            )
        tab_id = tab["id"]
        groups = []
        if "layout_tab_groups" in tables:
            groups = [
                r["column_name"]
                for r in src.execute(
                    "SELECT column_name FROM layout_tab_groups WHERE tab_id = ? ORDER BY position",
                    (tab_id,),
                )
            ]
        sorters = []
        if "layout_tab_sorters" in tables:
            sorters = [
                {"column": r["column_name"], "dir": r["dir"]}
                for r in src.execute(
                    "SELECT column_name, dir FROM layout_tab_sorters WHERE tab_id = ? ORDER BY position",
                    (tab_id,),
                )
            ]
        cols = []
        if "layout_columns" in tables:
            cols = src.execute(
                """SELECT field, position, hidden, frozen, width
                   FROM layout_columns WHERE tab_id = ? ORDER BY position, field""",
                (tab_id,),
            ).fetchall()
        filters = []
        if "layout_column_filters" in tables:
            filters = src.execute(
                "SELECT field, op, v, v2 FROM layout_column_filters WHERE tab_id = ?",
                (tab_id,),
            ).fetchall()
        col_order = [c["field"] for c in cols if c["position"] is not None]
        hidden = [c["field"] for c in cols if c["hidden"]]
        frozen = [c["field"] for c in cols if c["frozen"]]
        widths = {c["field"]: c["width"] for c in cols if c["width"] is not None}
        column_filters = {
            f["field"]: {"op": f["op"], "v": f["v"] or "", "v2": f["v2"] or ""}
            for f in filters
        }
        has_view = int(tab["has_view"]) if "has_view" in tab_cols else 0
        groups_explicit = True
        if "groups_explicit" in tab_cols:
            groups_explicit = bool(tab["groups_explicit"])
        if has_view or groups or sorters or cols or filters:
            layout_views[key] = {
                "hidden": hidden,
                "frozen": frozen,
                "order": col_order or None,
                "sorters": sorters or None,
                "columnFilters": column_filters,
                "group": groups,
                "groups_explicit": groups_explicit,
                "widths": widths,
            }
    return {"order": order, "clones": clones, "views": layout_views}


def _filters_from_view_row(row, src: sqlite3.Connection, tables: set[str]) -> dict:
    filters = _filters_from_children(src, tables, row["id"])
    if row["period"]:
        filters["period"] = row["period"]
    cols = {key for key in row.keys()}
    if "start_date" in cols and row["start_date"]:
        filters["from_date"] = row["start_date"]
    if "end_date" in cols and row["end_date"]:
        filters["to_date"] = row["end_date"]
    if "year" in cols and row["year"]:
        filters["year"] = row["year"]
    if "mode" in cols and row["mode"]:
        filters["n4_mode"] = row["mode"]
    return filters


def _upsert_view(
    dest: sqlite3.Connection,
    *,
    kind: str,
    report_key: str,
    name: str,
    owner_email: str | None,
    filters: dict,
    layout: dict,
    include_period: int,
    active_tab: str | None,
) -> tuple[int, str]:
    if kind == "personal":
        existing = dest.execute(
            """SELECT id FROM views
               WHERE kind = 'personal' AND report_key = ? AND name = ? AND owner_email = ?""",
            (report_key, name, owner_email),
        ).fetchone()
    else:
        existing = dest.execute(
            """SELECT id FROM views
               WHERE kind = ? AND report_key = ? AND name = ? AND owner_email IS NULL""",
            (kind, report_key, name),
        ).fetchone()
    layout = dict(layout or {})
    if active_tab:
        layout["active"] = active_tab
    if existing:
        view_id = int(existing["id"])
        dest.execute(
            "UPDATE views SET include_period = ? WHERE id = ?",
            (include_period, view_id),
        )
        save_filters_and_layout(dest, view_id, filters, layout, include_period)
        return view_id, "updated"
    dest.execute(
        """INSERT INTO views (owner_email, report_key, name, kind, include_period)
           VALUES (?, ?, ?, ?, ?)""",
        (owner_email, report_key, name, kind, include_period),
    )
    view_id = int(dest.execute("SELECT last_insert_rowid()").fetchone()[0])
    save_filters_and_layout(dest, view_id, filters, layout, include_period)
    return view_id, "inserted"


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
    for row in src.execute("SELECT * FROM views"):
        report_key = row["report_key"]
        if report_key not in KNOWN_REPORTS:
            counts["skipped"] += 1
            continue
        kind = row["kind"] if row["kind"] in {"personal", "company", "default"} else "personal"
        owner = None
        if kind == "personal":
            handle = row["owner_handle"] if "owner_handle" in view_cols else None
            owner = by_handle.get(str(handle or ""))
            if not owner and "owner_email" in view_cols:
                owner = (row["owner_email"] or "").strip().lower() or None
            if not owner:
                counts["skipped"] += 1
                continue
        filters = _filters_from_view_row(row, src, tables)
        layout = _layout_from_children(src, tables, row["id"])
        include = 1 if (filters.get("period") or filters.get("from_date") or filters.get("to_date")) else 0
        if "include_period" in view_cols and row["include_period"] is not None:
            include = int(row["include_period"])
        active = row["active_tab_key"] if "active_tab_key" in view_cols else None
        view_id, action = _upsert_view(
            dest,
            kind=kind,
            report_key=report_key,
            name=row["name"] or "Imported view",
            owner_email=owner,
            filters=filters,
            layout=layout,
            include_period=include,
            active_tab=active,
        )
        id_map[str(row["id"])] = view_id
        counts[action] += 1
    return id_map, counts


def _import_json_views(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    by_id: dict[int, str],
) -> tuple[dict, dict]:
    tables = _tables(src)
    id_map: dict[str, int] = {}
    counts = {"inserted": 0, "updated": 0, "skipped": 0}

    def add(kind: str, report_key: str, name: str, owner: str | None, params_raw, layout_raw, old_key: str):
        if report_key not in KNOWN_REPORTS:
            counts["skipped"] += 1
            return
        filters = _json_obj(params_raw)
        layout = _json_obj(layout_raw)
        include = 1 if (filters.get("period") or filters.get("from_date") or filters.get("to_date")) else 0
        view_id, action = _upsert_view(
            dest,
            kind=kind,
            report_key=report_key,
            name=name or "Imported view",
            owner_email=owner,
            filters=filters,
            layout=layout,
            include_period=include,
            active_tab=(layout.get("active") if isinstance(layout.get("active"), str) else None),
        )
        id_map[old_key] = view_id
        counts[action] += 1

    if "saved_reports" in tables:
        for row in src.execute("SELECT * FROM saved_reports"):
            owner = by_id.get(int(row["user_id"]))
            if not owner:
                counts["skipped"] += 1
                continue
            add("personal", row["report_key"], row["name"], owner, row["params_json"], row["layout_json"], f"saved:{row['id']}")
    if "company_views" in tables:
        for row in src.execute("SELECT * FROM company_views"):
            add("company", row["report_key"], row["name"], None, row["params_json"], row["layout_json"], f"company:{row['id']}")
    if "report_defaults" in tables:
        for row in src.execute("SELECT * FROM report_defaults"):
            add("default", row["report_key"], "Default", None, row["params_json"], row["layout_json"], f"default:{row['report_key']}")
    return id_map, counts


def _weekdays_csv(numbers: list[int]) -> str:
    names = []
    for day in numbers:
        if 0 <= day < len(cadence.WEEKDAY_NAMES):
            names.append(cadence.WEEKDAY_NAMES[day])
    return ",".join(names)


def _upsert_schedule(
    dest: sqlite3.Connection,
    *,
    view_id: int,
    owner_email: str,
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
) -> str:
    existing = dest.execute(
        """SELECT id FROM schedules
           WHERE view_id = ? AND owner_email = ? AND freq = ? AND run_time = ?""",
        (view_id, owner_email, freq, run_time),
    ).fetchone()
    values = (
        weekdays,
        monthday,
        recipients,
        cc,
        bcc,
        subject,
        filename,
        sharepoint_folder,
        onedrive_folder,
        is_active,
        last_run,
        catch_up_pending,
        catch_up_for_date,
    )
    if existing:
        dest.execute(
            """UPDATE schedules SET
                   weekdays = ?, monthday = ?, recipients = ?, cc = ?, bcc = ?,
                   subject = ?, filename = ?, sharepoint_folder = ?, onedrive_folder = ?,
                   is_active = ?, last_run = ?, catch_up_pending = ?, catch_up_for_date = ?
               WHERE id = ?""",
            values + (int(existing["id"]),),
        )
        return "updated"
    dest.execute(
        """INSERT INTO schedules (
               view_id, owner_email, freq, run_time, weekdays, monthday,
               recipients, cc, bcc, subject, filename, sharepoint_folder, onedrive_folder,
               is_active, last_run, catch_up_pending, catch_up_for_date
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (view_id, owner_email, freq, run_time) + values,
    )
    return "inserted"


def _fallback_owner(dest: sqlite3.Connection) -> str:
    row = dest.execute(
        """SELECT email FROM users
           WHERE role IN ('admin', 'developer') AND is_active = 1
           ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, id
           LIMIT 1"""
    ).fetchone()
    if row:
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
        owner = by_handle.get(str(row["owner_handle"] or "")) or fallback
        weekdays = ""
        if "schedule_weekdays" in tables:
            days = [
                int(r["weekday"])
                for r in src.execute(
                    "SELECT weekday FROM schedule_weekdays WHERE schedule_id = ? ORDER BY weekday",
                    (row["id"],),
                )
            ]
            weekdays = _weekdays_csv(days)
        monthday = None
        if "schedule_monthdays" in tables:
            md = src.execute(
                "SELECT monthday FROM schedule_monthdays WHERE schedule_id = ? ORDER BY monthday LIMIT 1",
                (row["id"],),
            ).fetchone()
            if md:
                monthday = int(md["monthday"])
        to_addrs, cc_addrs, bcc_addrs = [], [], []
        if "schedule_recipients" in tables:
            for rec in src.execute(
                "SELECT email, role FROM schedule_recipients WHERE schedule_id = ?",
                (row["id"],),
            ):
                email = (rec["email"] or "").strip()
                if rec["role"] == "cc":
                    cc_addrs.append(email)
                elif rec["role"] == "bcc":
                    bcc_addrs.append(email)
                else:
                    to_addrs.append(email)
        folder = row["sharepoint_path"] if "sharepoint_path" in cols else ""
        kind = row["folder_kind"] if "folder_kind" in cols else "sharepoint"
        sharepoint = folder if kind != "onedrive" else ""
        onedrive = folder if kind == "onedrive" else ""
        window = row["window_period"] if "window_period" in cols else None
        if window:
            dest.execute(
                """UPDATE views SET period = COALESCE(NULLIF(period, ''), ?), include_period = 1
                   WHERE id = ?""",
                (window, view_id),
            )
        action = _upsert_schedule(
            dest,
            view_id=view_id,
            owner_email=owner,
            freq=freq,
            run_time=run_time or "08:00",
            weekdays=weekdays,
            monthday=monthday,
            recipients=", ".join(to_addrs),
            cc=", ".join(cc_addrs),
            bcc=", ".join(bcc_addrs),
            subject=row["email_subject"] if "email_subject" in cols else "",
            filename=row["filename_template"] if "filename_template" in cols else "",
            sharepoint_folder=sharepoint or "",
            onedrive_folder=onedrive or "",
            is_active=int(row["is_active"] if "is_active" in cols else 1),
            last_run=row["last_claimed_at"] if "last_claimed_at" in cols else None,
            catch_up_pending=int(row["catch_up_pending"] if "catch_up_pending" in cols else 0),
            catch_up_for_date=row["catch_up_for_date"] if "catch_up_for_date" in cols else None,
        )
        counts[action] += 1
    return counts


def _cadence_fields(raw) -> tuple[str, str, str, int | None]:
    data = _json_obj(raw)
    freq = str(data.get("freq") or "daily").lower()
    if freq not in cadence.VALID_FREQ:
        freq = "daily"
    run_time = str(data.get("time") or "08:00")
    weekdays = _weekdays_csv([int(d) for d in (data.get("weekdays") or [])])
    monthday = None
    if data.get("monthday") not in (None, ""):
        monthday = int(data["monthday"])
    elif data.get("monthdays"):
        monthday = int(data["monthdays"][0])
    return freq, run_time, weekdays, monthday


def _find_json_view(
    dest: sqlite3.Connection,
    view_map: dict[str, int],
    report_key: str,
    view_name: str,
    owner: str | None,
    kind: str,
) -> int | None:
    for key, view_id in view_map.items():
        row = dest.execute("SELECT * FROM views WHERE id = ?", (view_id,)).fetchone()
        if not row:
            continue
        if row["report_key"] != report_key:
            continue
        if (row["name"] or "") == (view_name or "Default") and (
            (kind == "personal" and row["owner_email"] == owner)
            or (kind != "personal" and row["kind"] in {kind, "company", "default"})
        ):
            return view_id
        if key.endswith(f":{report_key}") and kind == "default":
            return view_id
    match = dest.execute(
        """SELECT id FROM views WHERE report_key = ? AND name = ?
           AND ((kind = 'personal' AND owner_email = ?) OR (kind != 'personal' AND owner_email IS NULL))
           ORDER BY CASE kind WHEN 'company' THEN 0 WHEN 'default' THEN 1 ELSE 2 END, id
           LIMIT 1""",
        (report_key, view_name or "Default", owner),
    ).fetchone()
    return int(match["id"]) if match else None


def _import_json_schedules(
    src: sqlite3.Connection,
    dest: sqlite3.Connection,
    view_map: dict[str, int],
    by_id: dict[int, str],
) -> dict:
    tables = _tables(src)
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    fallback = _fallback_owner(dest)

    def ingest(table: str, kind: str) -> None:
        if table not in tables:
            return
        cols = _cols(src, table)
        for row in src.execute(f"SELECT * FROM {table}"):
            report_key = row["report_key"]
            view_name = row["view_name"] if "view_name" in cols else "Default"
            owner = fallback
            if kind == "personal" and "owner_user_id" in cols:
                owner = by_id.get(int(row["owner_user_id"])) or fallback
            view_id = _find_json_view(dest, view_map, report_key, view_name, owner, kind)
            if view_id is None:
                filters = _json_obj(row["params_json"] if "params_json" in cols else None)
                layout = _json_obj(row["layout_json"] if "layout_json" in cols else None)
                include = 1 if filters.get("period") else 0
                view_id, _ = _upsert_view(
                    dest,
                    kind="company" if kind == "master" else "personal",
                    report_key=report_key,
                    name=view_name or "Imported schedule view",
                    owner_email=None if kind == "master" else owner,
                    filters=filters,
                    layout=layout,
                    include_period=include,
                    active_tab=None,
                )
            freq, run_time, weekdays, monthday = _cadence_fields(row["cadence"] if "cadence" in cols else None)
            folder = row["sharepoint_path"] if "sharepoint_path" in cols else ""
            action = _upsert_schedule(
                dest,
                view_id=view_id,
                owner_email=owner,
                freq=freq,
                run_time=run_time,
                weekdays=weekdays,
                monthday=monthday,
                recipients=row["recipients"] if "recipients" in cols else "",
                cc="",
                bcc="",
                subject="",
                filename=row["filename_template"] if "filename_template" in cols else "",
                sharepoint_folder=folder or "",
                onedrive_folder="",
                is_active=int(row["is_active"] if "is_active" in cols else 1),
                last_run=row["last_claimed_at"] if "last_claimed_at" in cols else None,
                catch_up_pending=int(row["catch_up_pending"] if "catch_up_pending" in cols else 0),
                catch_up_for_date=row["catch_up_for_date"] if "catch_up_for_date" in cols else None,
            )
            counts[action] += 1

    ingest("schedules", "personal")
    ingest("master_schedules", "master")
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
            by_id, by_handle, _emails = _user_maps(src)
            tables = _tables(src)
            has_norm_views = "views" in tables and src.execute("SELECT 1 FROM views LIMIT 1").fetchone()
            if has_norm_views:
                view_map, views = _import_normalized_views(src, dest, by_handle)
            else:
                view_map, views = _import_json_views(src, dest, by_id)
            has_norm_sched = (
                "report_schedules" in tables
                and src.execute("SELECT 1 FROM report_schedules LIMIT 1").fetchone()
            )
            if has_norm_sched:
                schedules = _import_report_schedules(src, dest, view_map, by_handle)
            else:
                schedules = _import_json_schedules(src, dest, view_map, by_id)
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
        "visibility": visibility,
        "settings": settings,
    }


def import_users(source_path: Path, dest_path: Path | None = None) -> dict:
    result = import_precious(source_path, dest_path)
    return {"inserted": result["users_inserted"], "skipped": result["users_skipped"]}


def summarize(result: dict) -> str:
    return (
        f"People {result['users_inserted']} added, {result['users_skipped']} already here. "
        f"Views {result['views_inserted']} added, {result['views_updated']} updated. "
        f"Schedules {result['schedules_inserted']} added, {result['schedules_updated']} updated."
    )


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
