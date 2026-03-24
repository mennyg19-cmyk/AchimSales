"""
Report run history -- SQLite-backed storage.

Public API unchanged from the original JSON version so callers in
app.py don't need modification.

Statuses: running, completed, failed, no_data
"""

import json
import logging
import os
import uuid
from datetime import datetime

from webapp.db import get_db

log = logging.getLogger(__name__)

MAX_HISTORY = 50


def add_record(email: str, report_key: str, report_name: str,
               params: dict, status: str = "running",
               filepath: str | None = None, filename: str | None = None,
               summary: dict | None = None, error: str | None = None) -> str:
    """Insert a report run into the history table. Returns the record_id."""
    record_id = uuid.uuid4().hex[:12]
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO history
               (record_id, user_email, timestamp, report_key, report_name,
                params, status, filepath, filename, summary, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, email,
             datetime.now().isoformat(timespec="seconds"),
             report_key, report_name,
             json.dumps(params), status,
             filepath, filename,
             json.dumps(summary or {}), error),
        )
        conn.commit()

        _trim_history(conn, email)
    finally:
        conn.close()
    return record_id


def update_record(email: str, record_id: str, **fields):
    """Update fields on an existing history record."""
    if not fields:
        return
    allowed = {"status", "filepath", "filename", "summary", "error"}
    set_parts = []
    values = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("summary", "params"):
            v = json.dumps(v) if not isinstance(v, str) else v
        set_parts.append(f"{k} = ?")
        values.append(v)

    if not set_parts:
        return

    values.extend([record_id, email])
    conn = get_db()
    try:
        conn.execute(
            f"UPDATE history SET {', '.join(set_parts)} WHERE record_id = ? AND user_email = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_history(email: str) -> list[dict]:
    """Return the user's report history, newest first."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT record_id, user_email, timestamp, report_key, report_name,
                      params, status, filepath, filename, summary, error
               FROM history
               WHERE user_email = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (email, MAX_HISTORY),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"]) if d["params"] else {}
            d["summary"] = json.loads(d["summary"]) if d["summary"] else {}
            fp = d.get("filepath")
            if fp and not os.path.isfile(fp):
                d["file_available"] = False
            else:
                d["file_available"] = bool(fp)
            result.append(d)
        return result
    finally:
        conn.close()


def delete_record(email: str, record_id: str) -> bool:
    """Delete a single history record. Also removes the output file if present.
    Returns True if a row was actually deleted."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT filepath FROM history WHERE record_id = ? AND user_email = ?",
            (record_id, email),
        ).fetchone()
        if not row:
            return False
        filepath = row["filepath"] if row else None
        conn.execute(
            "DELETE FROM history WHERE record_id = ? AND user_email = ?",
            (record_id, email),
        )
        conn.commit()
        if filepath and os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
        return True
    finally:
        conn.close()


def _trim_history(conn, email: str):
    """Keep only the newest MAX_HISTORY records per user."""
    conn.execute(
        """DELETE FROM history WHERE user_email = ? AND id NOT IN (
               SELECT id FROM history WHERE user_email = ?
               ORDER BY timestamp DESC LIMIT ?
           )""",
        (email, email, MAX_HISTORY),
    )
    conn.commit()
