"""Developer diagnostics (destructive ones are POST + CSRF)."""
from __future__ import annotations

import json
import os
import re
import socket
import time
from urllib.parse import urlparse

from flask import abort, current_app, jsonify, request

from web.auth.decorators import require_login
from web.blueprints.reports import (
    _authz, _job_repo, _principal_or_401, _require_developer, _user_id, reports_bp,
)

_SQLITE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sqlite_ident(name: str) -> str:
    """Quote a sqlite_master table name. Rejects anything that is not a plain ident."""
    if not _SQLITE_IDENT.fullmatch(name or ""):
        raise ValueError(f"Refusing to dump non-identifier table {name!r}")
    return '"' + name + '"'

def _probe_reporting_api(cfg, *, run_live: bool = False) -> dict:
    """Hit the on-prem Reporting API straight from this request (no worker, no
    cache, no dedup) so we can prove whether our calls leave the app and reach
    the endpoint at all. Checks, all with short timeouts so the request can't hang:

      tcp  - open a raw socket to host:port. Proves the Azure Hybrid Connection
             tunnel reaches the on-prem listener (no HTTP, no stored procedure).
      http - a GET to the API root. ANY status code means the API process
             answered and the DBA should see this request land. A connect/read
             timeout here (with tcp ok) points at the API, not the tunnel.
      live_query (only when run_live) - POST a real but tiny reference-data SP
             (customer_master, no date window) with a short read timeout and no
             retries. This is the ONLY check that proves the stored-proc layer
             actually executes and returns - reachability can't. It's also a call
             the DBA can watch land on the SQL box.

    Never returns the API key. host:port is operational info, not a secret.
    """
    base = (cfg.reporting_api_base_url or "").rstrip("/")
    out: dict = {"configured": bool(base and cfg.reporting_api_key),
                 "host": None, "port": None, "tcp": None, "http": None}
    if not base:
        return out
    parsed = urlparse(base)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    out["host"], out["port"] = host, port

    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=5):
            out["tcp"] = {"ok": True, "ms": int((time.monotonic() - t0) * 1000)}
    except Exception as exc:  # noqa: BLE001 - report the failure, don't raise
        out["tcp"] = {"ok": False, "ms": int((time.monotonic() - t0) * 1000),
                      "error": f"{type(exc).__name__}: {exc}"}

    import requests
    t1 = time.monotonic()
    try:
        r = requests.get(f"{base}/", timeout=(5, 10),
                         headers={"X-API-Key": cfg.reporting_api_key})
        out["http"] = {"ok": True, "status": r.status_code,
                       "ms": int((time.monotonic() - t1) * 1000)}
    except Exception as exc:  # noqa: BLE001 - report the failure, don't raise
        out["http"] = {"ok": False, "ms": int((time.monotonic() - t1) * 1000),
                       "error": f"{type(exc).__name__}: {exc}"}

    if run_live:
        t2 = time.monotonic()
        try:
            r = requests.post(
                f"{base}/api/reports/customer_master/run", json={},
                headers={"X-API-Key": cfg.reporting_api_key,
                         "Content-Type": "application/json"},
                timeout=(5, 25))
            body = r.json() if r.ok else None
            out["live_query"] = {
                "ok": r.ok, "status": r.status_code,
                "ms": int((time.monotonic() - t2) * 1000),
                "report_id": "customer_master",
                "row_count": (body or {}).get("row_count"),
            }
        except Exception as exc:  # noqa: BLE001 - report the failure, don't raise
            out["live_query"] = {"ok": False, "ms": int((time.monotonic() - t2) * 1000),
                                 "report_id": "customer_master",
                                 "error": f"{type(exc).__name__}: {exc}"}
    return out


@reports_bp.get("/api/reports/diagnostics/reporting-api")
@require_login
def reporting_api_diagnostics():
    """Admin/developer check: is the Reporting API reachable from the app right
    now, and is the job worker backed up? Answers 'why aren't our calls hitting
    the endpoint' without guessing. Developer-only (exposes the API host)."""
    p = _require_developer()
    cfg = current_app.config["APP_CONFIG"]
    from web import is_background_leader_process
    worker = current_app.config["JOB_WORKER"]
    run_live = request.args.get("live") in ("1", "true", "yes")
    return jsonify({
        "reporting_api": _probe_reporting_api(cfg, run_live=run_live),
        "jobs": _job_repo().status_summary(),
        "host": _host_metrics(cfg),
        "claim_probe": _claim_probe(current_app.config["DB"]),
        "me": {"email": p.email, "user_id": _user_id(p.email), "role": p.role},
        "recent_jobs": _recent_jobs(current_app.config["DB"]),
        "wiring": _worker_wiring(worker, current_app.config["DB"]),
        "worker": {
            "pid": os.getpid(),
            "is_leader_process": is_background_leader_process(),
            **worker.health(),
        },
    })


def _reporting_client():
    service = current_app.config.get("REPORT_SERVICE")
    client = getattr(service, "client", None) if service is not None else None
    if client is None or not getattr(client, "configured", False):
        return None
    return client


def _body_or_args():
    body = request.get_json(silent=True) or {}
    return body if isinstance(body, dict) else {}


@reports_bp.post("/api/reports/diagnostics/reconcile-salesman-invoiced")
@require_login
def reconcile_salesman_invoiced_diagnostic():
    """One-shot: monthly_salesman_yoy vs invoiced_report Total Invoice.

    Developer + CSRF (POST). Optional scope=ty|ly|all (default all).
    """
    _require_developer()
    client = _reporting_client()
    if client is None:
        return jsonify({"ok": False, "error": "Reporting API not configured"}), 503

    body = _body_or_args()
    year = body.get("year")
    if year is None:
        year = request.args.get("year", type=int)
    through = body.get("through_month")
    if through is None:
        through = request.args.get("through_month", type=int)
    scope = str(body.get("scope") or request.args.get("scope") or "all").strip().lower()
    only_month = body.get("month")
    if only_month is None:
        only_month = request.args.get("month", type=int)
    if scope not in ("ty", "ly", "all"):
        return jsonify({"ok": False, "error": "scope must be ty, ly, or all"}), 400
    try:
        from web.reporting.reconcile_salesman import reconcile
        return jsonify(reconcile(
            client, year=year, through_month=through, scope=scope,
            only_month=only_month,
        ))
    except Exception as exc:  # noqa: BLE001 - surface to the caller for one-shot ops
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


@reports_bp.post("/api/reports/diagnostics/reconcile-number4-invoiced")
@require_login
def reconcile_number4_invoiced_diagnostic():
    """One-shot: Number 4 rolling-12 vs invoiced_report (subtotal + Total Invoice).

    Developer + CSRF (POST). Optional view=by_customer|by_item,
    month=1..12 (index into the rolling window, 1=oldest).
    """
    _require_developer()
    client = _reporting_client()
    if client is None:
        return jsonify({"ok": False, "error": "Reporting API not configured"}), 503

    body = _body_or_args()
    view = str(body.get("view") or request.args.get("view") or "by_customer").strip().lower()
    if view not in ("by_customer", "by_item"):
        return jsonify({"ok": False, "error": "view must be by_customer or by_item"}), 400
    only_month = body.get("month")
    if only_month is None:
        only_month = request.args.get("month", type=int)
    as_of_raw = str(body.get("as_of") or request.args.get("as_of") or "").strip()
    as_of = None
    if as_of_raw:
        try:
            from datetime import date as _date
            as_of = _date.fromisoformat(as_of_raw[:10])
        except ValueError:
            return jsonify({"ok": False, "error": "as_of must be YYYY-MM-DD"}), 400
    try:
        from web.reporting.reconcile_number4 import reconcile
        return jsonify(reconcile(
            client, as_of=as_of, view=view, only_month=only_month,
        ))
    except Exception as exc:  # noqa: BLE001 - surface to the caller for one-shot ops
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


def _host_metrics(cfg) -> dict:
    """Disk, memory, and DB file age for the admin diagnostic. No secrets."""
    import shutil
    path = cfg.precious_db_path
    disk = {}
    try:
        usage = shutil.disk_usage(str(path.parent))
        disk = {"free_bytes": usage.free, "total_bytes": usage.total}
    except OSError as exc:
        disk = {"error": str(exc)}
    mem = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:") or line.startswith("MemTotal:"):
                    key, raw, _unit = line.split()
                    mem[key.rstrip(":").lower()] = int(raw) * 1024
    except OSError:
        mem = {}
    db_bytes = None
    try:
        db_bytes = path.stat().st_size if path.exists() else None
    except OSError:
        db_bytes = None
    from web.ops.metrics import snapshot as metrics_snapshot
    return {
        "disk": disk, "memory": mem, "precious_bytes": db_bytes,
        "counters": metrics_snapshot(),
    }


def _recent_jobs(db, limit: int = 10) -> list[dict]:
    """Last few jobs with owner + status, so 'Lost track of the job' can be told
    apart: a 404 on poll is either the job not existing or its owner_user_id not
    matching the caller. NULL-owner (system) jobs are unreadable through the user
    API by design - that mismatch shows up plainly here."""
    with db.precious() as conn:
        rows = conn.execute(
            "SELECT id, type, status, owner_user_id, created_at FROM jobs"
            " ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [
        {"id": r["id"], "type": r["type"], "status": r["status"],
         "owner_user_id": r["owner_user_id"], "created_at": r["created_at"]}
        for r in rows
    ]


@reports_bp.post("/api/reports/diagnostics/claim-once")
@require_login
def claim_once_diagnostic():
    """Developer-only: call the REAL worker.repo.claim_next() from this request
    thread (the poller calls the same method but always gets None). If this
    claims a job, the poller's failure is thread-specific; if it returns None,
    the method itself is the problem. Safe: any claimed job is immediately set
    back to 'queued' so the actual handler never runs and nothing is lost."""
    _require_developer()
    from datetime import datetime, timezone
    db = current_app.config["DB"]
    # Replicate claim_next() step by step so we can see WHICH step bails: does the
    # SELECT find the row, and does the UPDATE (id + status='queued') actually
    # match it? Then revert so the job is never really claimed.
    with db.precious() as conn:
        sel = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        out: dict = {"select_found_id": sel["id"] if sel else None}
        if sel:
            upd = conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
                (datetime.now(timezone.utc).isoformat(), sel["id"]),
            )
            out["update_rowcount"] = upd.rowcount
            verify = conn.execute(
                "SELECT status FROM jobs WHERE id=?", (sel["id"],)
            ).fetchone()
            out["status_after_update"] = verify["status"] if verify else None
            # Revert no matter what so this is a pure read-only probe.
            conn.execute(
                "UPDATE jobs SET status='queued', started_at=NULL WHERE id=?", (sel["id"],)
            )
            out["reverted"] = True
    return jsonify(out)


_PRECIOUS_REPAIR_MUTATING = frozenset({
    "reindex", "delete-ghosts", "backup", "rebuild-jobs",
})


@reports_bp.get("/api/reports/diagnostics/precious-repair")
@require_login
def precious_repair_diagnostic_get():
    """Read-only integrity check. Mutating actions must POST (CSRF-protected)."""
    _require_developer()
    action = request.args.get("action", "check")
    if action in _PRECIOUS_REPAIR_MUTATING:
        abort(405, description="Use POST for this action")
    if action != "check":
        abort(400, description="action must be check, backup, reindex, delete-ghosts, or rebuild-jobs")
    return jsonify(_run_precious_repair("check"))


@reports_bp.post("/api/reports/diagnostics/precious-repair")
@require_login
def precious_repair_diagnostic_post():
    """Developer-only mutating repair. CSRF required (POST is not CSRF-exempt)."""
    _require_developer()
    body = request.get_json(silent=True) or {}
    action = request.args.get("action") or body.get("action")
    if action not in _PRECIOUS_REPAIR_MUTATING:
        abort(400, description="POST action must be backup, reindex, delete-ghosts, or rebuild-jobs")
    return jsonify(_run_precious_repair(action))


def _require_developer():
    p = _principal_or_401()
    _authz().assert_developer(p)
    return p


def _run_precious_repair(action: str) -> dict:
    """Developer-only. The jobs 'status' index disagrees with the table by id
    (a queued row found by status doesn't exist by id) - SQLite corruption from
    the old /home SMB WAL, carried into the restore. check reports integrity +
    index-vs-scan counts. backup dumps every table to JSON on /home. reindex
    rebuilds indexes. delete-ghosts removes stuck queued rows. rebuild-jobs
    drops + recreates the corrupt jobs table."""
    db = current_app.config["DB"]
    out: dict = {"action": action}
    with db.precious() as conn:
        if action == "check":
            out["integrity_check"] = [r[0] for r in conn.execute("PRAGMA integrity_check(30)").fetchall()]
            out["quick_check"] = [r[0] for r in conn.execute("PRAGMA quick_check(30)").fetchall()]
            out["jobs_indexes"] = [
                {"seq": r[0], "name": r[1], "unique": r[2], "origin": r[3], "partial": r[4]}
                for r in conn.execute("PRAGMA index_list('jobs')").fetchall()
            ]
            # status index path vs forced full table scan - if these disagree the
            # index has ghost entries the table doesn't back.
            out["queued_via_index"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            out["queued_via_table_scan"] = conn.execute(
                "SELECT COUNT(*) FROM jobs NOT INDEXED WHERE status='queued'").fetchone()[0]
        elif action == "reindex":
            conn.execute("REINDEX jobs")
            out["reindexed"] = True
            out["queued_via_index"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            out["queued_via_table_scan"] = conn.execute(
                "SELECT COUNT(*) FROM jobs NOT INDEXED WHERE status='queued'").fetchone()[0]
        elif action == "delete-ghosts":
            deleted = conn.execute("DELETE FROM jobs WHERE status='queued'").rowcount
            out["deleted"] = deleted
            out["queued_remaining"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
        elif action == "backup":
            out["backup"] = _backup_precious(conn)
        elif action == "rebuild-jobs":
            schema = [r[0] for r in conn.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name='jobs' AND sql IS NOT NULL"
                " ORDER BY (type='table') DESC").fetchall()]
            out["captured_schema"] = schema
            conn.execute("DROP TABLE jobs")
            for stmt in schema:
                conn.execute(stmt)
            out["rebuilt"] = True
            out["jobs_count"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            out["integrity_check"] = [r[0] for r in conn.execute("PRAGMA integrity_check(30)").fetchall()]
        else:
            abort(400, description="action must be check, backup, reindex, delete-ghosts, or rebuild-jobs")
    return out


def _backup_precious(conn) -> dict:
    """Dump every table to a timestamped JSON file under /home (persistent across
    container recycles). Reads each table on its own so a corrupt table records an
    error instead of killing the whole backup. Returns the path + per-table counts."""
    import json
    from datetime import datetime, timezone

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    dump: dict = {"created_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    counts: dict = {}
    errors: dict = {}
    for table in tables:
        try:
            ident = _sqlite_ident(table)
            # ident is quoted from sqlite_master names only (never request input).
            rows = conn.execute("SELECT * FROM " + ident).fetchall()  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            dump["tables"][table] = [dict(r) for r in rows]
            counts[table] = len(rows)
        except Exception as exc:  # noqa: BLE001 - one bad table must not lose the rest
            errors[table] = f"{type(exc).__name__}: {exc}"

    backup_dir = "/home/site/v3data"
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(backup_dir, f"precious-backup-{stamp}.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dump, fh)
    os.replace(tmp, path)
    return {"path": path, "row_counts": counts, "errors": errors}


def _worker_wiring(worker, app_db) -> dict:
    """Is the poller running the code we think, against the DB we think? The
    poller's claim_next() returns None while an identical inline query in this
    same process finds the job. Dump the ACTUAL deployed source of claim_next
    (a stale .pyc on the wwwroot share would differ from the repo) and confirm
    the worker's repo points at the very same Database object/path as requests."""
    import inspect
    repo = worker.repo
    out: dict = {
        "worker_db_is_app_db": repo.db is app_db,
        "worker_db_path": str(getattr(repo.db, "precious_path", None)),
        "app_db_path": str(getattr(app_db, "precious_path", None)),
    }
    try:
        out["claim_next_source"] = inspect.getsource(type(repo).claim_next)
    except Exception as exc:  # noqa: BLE001 - best-effort introspection
        out["claim_next_source_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["claim_next_file"] = inspect.getsourcefile(type(repo).claim_next)
    except Exception:  # noqa: BLE001
        out["claim_next_file"] = None
    return out


def _claim_probe(db) -> dict:
    """The poller's claim_next() returns None even though status_summary() sees
    'queued' jobs in the SAME file/process. Run the EXACT read claim_next uses
    and dump the RAW status/created_at of every active row, so we can see what's
    different about these rows (hidden characters in status, a NULL/odd
    created_at that breaks ORDER BY, a value that only LOOKS like 'queued')."""
    with db.precious() as conn:
        picked = conn.execute(
            "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        rows = conn.execute(
            "SELECT id, status, created_at, typeof(status) AS s_type,"
            " typeof(created_at) AS ca_type FROM jobs"
            " WHERE status IN ('queued', 'running') ORDER BY created_at LIMIT 20"
        ).fetchall()
        eq_count = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE status = 'queued'"
        ).fetchone()["n"]
        total = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        jmode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    return {
        "db_file": _db_file_identity(db.precious_path),
        "journal_mode": jmode,
        "total_jobs": total,
        "claim_next_would_pick": picked["id"] if picked else None,
        "rows_where_status_equals_queued": eq_count,
        "active_rows": [
            {"id": r["id"], "status_repr": repr(r["status"]), "status_type": r["s_type"],
             "created_at_repr": repr(r["created_at"]), "created_at_type": r["ca_type"]}
            for r in rows
        ],
    }


def _db_file_identity(path) -> dict:
    """Inode/size/mtime of the precious.db file (and its -wal). If the leader and
    a follower report different inodes for the same path, they're literally
    reading different files - that's the whole bug. If same inode but a big -wal,
    the data may be sitting in a WAL the poller's connection isn't seeing."""
    out: dict = {"path": str(path)}
    for label, p in (("main", path), ("wal", path.with_name(path.name + "-wal"))):
        try:
            st = os.stat(p)
            out[label] = {"inode": st.st_ino, "size": st.st_size, "mtime": int(st.st_mtime)}
        except OSError:
            out[label] = None
    return out
