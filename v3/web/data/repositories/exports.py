"""Blob store for background-built Excel exports (cache.db `report_exports`).

A finished ``report.export`` job writes its .xlsx bytes here keyed by the job id;
the download endpoint streams them back. Kept in cache.db (regenerable, not
Litestream-replicated) and reaped on a TTL, so a missing blob simply means the
user re-runs the export.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.data.connection import Database


EXPORT_TYPE_ONE_TIME = "one_time"
EXPORT_TYPE_SCHEDULED = "scheduled"
EXPORT_TYPE_MASTER = "master"

RETENTION_SECONDS = {
    EXPORT_TYPE_ONE_TIME: 7 * 86400,     # 7 days
    EXPORT_TYPE_SCHEDULED: 30 * 86400,   # 30 days
    EXPORT_TYPE_MASTER: 90 * 86400,      # 90 days (never-expire filled the B1 disk)
}


@dataclass(frozen=True)
class ExportMeta:
    job_id: str
    report_key: str
    filename: str
    size_bytes: int
    built_at: str
    export_type: str = EXPORT_TYPE_ONE_TIME
    owner_email: str = ""


class ExportRepository:
    def __init__(self, db: Database):
        self.db = db

    def put(self, job_id: str, report_key: str, filename: str, content: bytes,
            *, export_type: str = EXPORT_TYPE_ONE_TIME, owner_email: str = "") -> None:
        with self.db.cache() as conn:
            conn.execute(
                "INSERT INTO report_exports(job_id, report_key, filename, content, size_bytes,"
                "   export_type, owner_email)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(job_id) DO UPDATE SET"
                "   report_key=excluded.report_key, filename=excluded.filename,"
                "   content=excluded.content, size_bytes=excluded.size_bytes,"
                "   export_type=excluded.export_type, owner_email=excluded.owner_email,"
                "   built_at=datetime('now')",
                (job_id, report_key, filename, content, len(content), export_type, owner_email),
            )

    def content(self, job_id: str) -> tuple[str, bytes] | None:
        """(filename, bytes) for a download, or None if reaped/never built."""
        with self.db.cache() as conn:
            row = conn.execute(
                "SELECT filename, content FROM report_exports WHERE job_id = ?", (job_id,)
            ).fetchone()
        return (row["filename"], row["content"]) if row else None

    def meta(self, job_id: str) -> ExportMeta | None:
        with self.db.cache() as conn:
            row = conn.execute(
                "SELECT job_id, report_key, filename, size_bytes, built_at"
                " FROM report_exports WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _meta(row) if row else None

    def metas_for(self, job_ids: list[str]) -> dict[str, ExportMeta]:
        """Metadata for a set of export ids (for the user's recent-exports list)."""
        if not job_ids:
            return {}
        placeholders = ",".join("?" * len(job_ids))
        with self.db.cache() as conn:
            rows = conn.execute(
                "SELECT job_id, report_key, filename, size_bytes, built_at"
                f" FROM report_exports WHERE job_id IN ({placeholders})", job_ids
            ).fetchall()
        return {r["job_id"]: _meta(r) for r in rows}

    def prune(self, older_than_seconds: float | None = None) -> int:
        """Tiered cleanup: applies per-type retention unless a flat TTL is given."""
        total = 0
        with self.db.cache() as conn:
            if older_than_seconds is not None:
                modifier = f"-{int(older_than_seconds)} seconds"
                cur = conn.execute(
                    "DELETE FROM report_exports WHERE built_at < datetime('now', ?)", (modifier,)
                )
                total = cur.rowcount
            else:
                for etype, ttl in RETENTION_SECONDS.items():
                    if ttl is None:
                        continue
                    modifier = f"-{int(ttl)} seconds"
                    cur = conn.execute(
                        "DELETE FROM report_exports WHERE export_type = ?"
                        " AND built_at < datetime('now', ?)", (etype, modifier)
                    )
                    total += cur.rowcount
        return total

    def history(self, *, limit: int = 100, report_key: str | None = None,
                owner_email: str | None = None) -> list[ExportMeta]:
        """Recent exports for the history browser (admin)."""
        clauses = []
        params: list = []
        if report_key:
            clauses.append("report_key = ?")
            params.append(report_key)
        if owner_email:
            clauses.append("owner_email = ?")
            params.append(owner_email)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.db.cache() as conn:
            rows = conn.execute(
                "SELECT job_id, report_key, filename, size_bytes, built_at,"
                " export_type, owner_email"
                f" FROM report_exports{where} ORDER BY built_at DESC LIMIT ?", params
            ).fetchall()
        return [_meta(r) for r in rows]


def _meta(row) -> ExportMeta:
    return ExportMeta(
        job_id=row["job_id"], report_key=row["report_key"], filename=row["filename"],
        size_bytes=row["size_bytes"], built_at=row["built_at"],
        export_type=row["export_type"] if "export_type" in row.keys() else EXPORT_TYPE_ONE_TIME,
        owner_email=row["owner_email"] if "owner_email" in row.keys() else "",
    )
