"""Enqueue named company schedules on App Service (Kudu). Stdlib only."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path

NAMES = ("DailyOrderReport", "Daily Open Orders Report")


def _db_path() -> Path:
    for key in ("BETA_PRECIOUS_DB_PATH", "PRECIOUS_DB_PATH"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            path = Path(raw)
            if path.is_file():
                return path
    here = Path("/home/web_sierra/wwwroot")
    for rel in (".data/beta_precious.db", ".data/precious.db"):
        path = here / rel
        if path.is_file():
            return path
    tmp = Path("/tmp/v3data")
    for name in ("beta_precious.db", "precious.db"):
        path = tmp / name
        if path.is_file():
            return path
    raise SystemExit("precious db not found (set BETA_PRECIOUS_DB_PATH)")


def main() -> None:
    db = _db_path()
    conn = sqlite3.connect(str(db), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    queued = []
    missing = []
    for name in NAMES:
        row = conn.execute(
            "SELECT id FROM master_schedules WHERE name=? ORDER BY id LIMIT 1",
            (name,),
        ).fetchone()
        if row is None:
            missing.append(name)
            continue
        sid = int(row["id"])
        job_id = uuid.uuid4().hex
        dedup = f"schedrun:master:{sid}"
        existing = conn.execute(
            "SELECT id FROM jobs WHERE dedup_key=? AND status IN ('queued','running')",
            (dedup,),
        ).fetchone()
        if existing:
            queued.append({"name": name, "schedule_id": sid, "job_id": existing["id"],
                           "already": True})
            continue
        params = json.dumps({
            "schedule_id": sid,
            "schedule_type": "master",
            "ignore_sabbath": True,
            "catch_up_for_date": "",
            "include_regular": True,
        })
        conn.execute(
            "INSERT INTO jobs(id, type, status, owner_user_id, dedup_key, params_json)"
            " VALUES (?, 'schedule.run', 'queued', NULL, ?, ?)",
            (job_id, dedup, params),
        )
        queued.append({"name": name, "schedule_id": sid, "job_id": job_id, "already": False})
    conn.commit()
    conn.close()
    out = {"ok": not missing, "db": str(db), "queued": queued, "missing": missing}
    print(json.dumps(out))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
