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
    allowed = {"status", "filepath", "filename", "summary", "error", "extra_files"}
    set_parts = []
    values = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("summary", "params", "extra_files"):
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


def _hydrate_row(row) -> dict:
    """Convert a raw history row into the dict shape consumers expect."""
    d = dict(row)
    d["params"] = json.loads(d["params"]) if d["params"] else {}
    d["summary"] = json.loads(d["summary"]) if d["summary"] else {}
    try:
        extra = json.loads(d.get("extra_files") or "[]")
        if not isinstance(extra, list):
            extra = []
    except (ValueError, TypeError):
        extra = []
    d["extra_files"] = [
        ef for ef in extra
        if isinstance(ef, dict) and ef.get("filepath") and os.path.isfile(ef["filepath"])
    ]
    fp = d.get("filepath")
    d["file_available"] = bool(fp) and os.path.isfile(fp)
    d["file_count"] = (1 if d["file_available"] else 0) + len(d["extra_files"])
    return d


# Ties on `timestamp` (second-precision) are broken by `id DESC` so ordering is
# stable -- without this, two reports started in the same second could swap
# positions between page render and a later click.
_HISTORY_COLUMNS = (
    "record_id, user_email, timestamp, report_key, report_name, "
    "params, status, filepath, filename, summary, error, extra_files"
)


def get_history(email: str) -> list[dict]:
    """Return the user's report history, newest first."""
    conn = get_db()
    try:
        rows = conn.execute(
            f"""SELECT {_HISTORY_COLUMNS}
               FROM history
               WHERE user_email = ?
               ORDER BY timestamp DESC, id DESC
               LIMIT ?""",
            (email, MAX_HISTORY),
        ).fetchall()
        return [_hydrate_row(r) for r in rows]
    finally:
        conn.close()


def get_record(email: str, record_id: str) -> dict | None:
    """Return a single history record by its stable record_id, or None."""
    conn = get_db()
    try:
        row = conn.execute(
            f"""SELECT {_HISTORY_COLUMNS}
               FROM history
               WHERE user_email = ? AND record_id = ?""",
            (email, record_id),
        ).fetchone()
        return _hydrate_row(row) if row else None
    finally:
        conn.close()


def delete_record(email: str, record_id: str) -> bool:
    """Delete a single history record. Also removes the output files (primary + extras)
    if present. Returns True if a row was actually deleted."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT filepath, extra_files FROM history WHERE record_id = ? AND user_email = ?",
            (record_id, email),
        ).fetchone()
        if not row:
            return False
        filepath = row["filepath"] if row else None
        extra_raw = row["extra_files"] if row and "extra_files" in row.keys() else None
        conn.execute(
            "DELETE FROM history WHERE record_id = ? AND user_email = ?",
            (record_id, email),
        )
        conn.commit()

        paths_to_remove = []
        if filepath:
            paths_to_remove.append(filepath)
        try:
            extras = json.loads(extra_raw or "[]")
            for ef in extras:
                if isinstance(ef, dict) and ef.get("filepath"):
                    paths_to_remove.append(ef["filepath"])
        except (ValueError, TypeError):
            pass

        for p in paths_to_remove:
            if p and os.path.isfile(p):
                try:
                    os.remove(p)
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
