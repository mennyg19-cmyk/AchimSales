"""Blob store for background-built Excel exports (cache.db `report_exports`).

A finished ``report.export`` job writes its .xlsx bytes here keyed by the job id;
the download endpoint streams them back. Kept in cache.db (regenerable, not
Litestream-replicated) and reaped on a TTL, so a missing blob simply means the
user re-runs the export.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.data.connection import Database


@dataclass(frozen=True)
class ExportMeta:
    job_id: str
    report_key: str
    filename: str
    size_bytes: int
    built_at: str


class ExportRepository:
    def __init__(self, db: Database):
        self.db = db

    def put(self, job_id: str, report_key: str, filename: str, content: bytes) -> None:
        with self.db.cache() as conn:
            conn.execute(
                "INSERT INTO report_exports(job_id, report_key, filename, content, size_bytes)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(job_id) DO UPDATE SET"
                "   report_key=excluded.report_key, filename=excluded.filename,"
                "   content=excluded.content, size_bytes=excluded.size_bytes,"
                "   built_at=datetime('now')",
                (job_id, report_key, filename, content, len(content)),
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

    def prune(self, older_than_seconds: float) -> int:
        # Compare in SQLite's own clock/format on both sides (built_at defaults to
        # datetime('now')); mixing a Python ISO string here would compare wrong.
        modifier = f"-{int(older_than_seconds)} seconds"
        with self.db.cache() as conn:
            cur = conn.execute(
                "DELETE FROM report_exports WHERE built_at < datetime('now', ?)", (modifier,)
            )
            return cur.rowcount


def _meta(row) -> ExportMeta:
    return ExportMeta(
        job_id=row["job_id"], report_key=row["report_key"], filename=row["filename"],
        size_bytes=row["size_bytes"], built_at=row["built_at"],
    )
