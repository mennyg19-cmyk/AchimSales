"""Copy People rows from a live v3 precious.db into this rebuild's sqlite.

Opt-in CLI. Does not invent salesman maps. Does not overwrite emails already
in the destination. Views and schedules stay behind (different schema).

  python3 import_precious.py /path/to/precious.db
  APP_DB_PATH=/tmp/home.sqlite python3 import_precious.py ./precious.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import config
from db import db, init_db

ROLES = {"admin", "developer", "manager", "salesman"}


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def import_users(source_path: Path, dest_path: Path | None = None) -> dict:
    if dest_path is not None:
        os.environ["APP_DB_PATH"] = str(dest_path)
    init_db()
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row
    try:
        if "users" not in {
            row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }:
            raise SystemExit(f"{source_path} has no users table.")
        user_cols = _cols(src, "users")
        extra_groups: dict[int, list[str]] = {}
        tables = {row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
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
        inserted = 0
        skipped = 0
        with db() as dest:
            dest_emails = {
                row["email"] for row in dest.execute("SELECT email FROM users").fetchall()
            }
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
                theme = themes.get(email) or (
                    row["theme"] if "theme" in user_cols else "light"
                )
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
            email_to_id = {
                row["email"]: row["id"] for row in dest.execute("SELECT id, email FROM users")
            }
            for email, report_key, allowed in report_access:
                uid = email_to_id.get(email)
                if not uid:
                    continue
                dest.execute(
                    """INSERT OR IGNORE INTO user_report_access (user_id, report_key, allowed)
                       VALUES (?, ?, ?)""",
                    (uid, report_key, allowed),
                )
    finally:
        src.close()
    return {"inserted": inserted, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import People rows from a v3 precious.db")
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
    result = import_users(args.precious, dest)
    print(f"Imported {result['inserted']} people; skipped {result['skipped']} existing emails into {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
