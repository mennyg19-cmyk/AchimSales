"""Chunked mirror refresh + admin backfill helpers.

The salesline and invoice mirrors have no retention window -- every row
that's ever been upserted stays forever. This module owns the *fetch*
side of that contract:

* :func:`refresh_window_chunked` -- what the daily cron calls. Pulls the
  last N months (default 6) one calendar month at a time so each API
  call is small and a single bad month doesn't poison the rest. Each
  chunk lands in the mirror via the existing piggyback path on
  :func:`test.webapp.services.reporting_api.run`.

* :func:`backfill_since_golive` -- what the admin "Backfill since D365
  go-live" button calls. Same chunking, but the window starts at
  ``core.dates.D365_GO_LIVE`` and runs forward to today. This is the
  only way to populate older history; the daily cron never touches it.

Both helpers accept an optional ``progress_cb`` so a foreground caller
(the admin diag page) can render a live "chunk N of M" strip while a
backfill is in flight.

Failure handling: per-chunk errors are caught, logged, and appended to
``result["errors"]``. We never abort the whole run because one month
fails -- partial coverage is far better than zero coverage. The mirror's
stats output (rows_in / inserted / updated) is aggregated across chunks.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Literal

from core.dates import D365_GO_LIVE, get_today_eastern
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)


Scope = Literal["salesline", "invoice", "all"]
ProgressCb = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Calendar-month chunking
# ---------------------------------------------------------------------------


def _month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split ``[start, end]`` into calendar-month chunks.

    Each chunk is ``(chunk_start, chunk_end)`` inclusive, where
    ``chunk_end`` is the last day of that calendar month (or ``end`` if
    the month overflows the window). Empty range -> empty list.
    """
    if end < start:
        return []

    chunks: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        # Last day of cur's calendar month: jump to the first of next
        # month, subtract a day.
        if cur.month == 12:
            next_month_first = date(cur.year + 1, 1, 1)
        else:
            next_month_first = date(cur.year, cur.month + 1, 1)
        chunk_end = min(next_month_first - timedelta(days=1), end)
        chunks.append((cur, chunk_end))
        cur = next_month_first
    return chunks


# ---------------------------------------------------------------------------
# Per-scope API call
# ---------------------------------------------------------------------------


_REPORT_KEY = {
    "salesline": "ordered",
    "invoice":   "invoiced",
}


def _scopes_for(scope: Scope) -> list[str]:
    if scope == "all":
        return ["salesline", "invoice"]
    return [scope]


def _run_chunk(report_key: str, start: date, end: date) -> int:
    """Pull one month for one report. Returns the row count.

    The piggyback path inside ``reporting_api.run`` already writes the
    rows into the mirror, so we don't need to call ``upsert_*`` here.
    """
    rows = reporting_api.run(
        report_key,
        {
            "period":     "custom",
            "start_date": start.isoformat(),
            "end_date":   end.isoformat(),
        },
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _run_chunks_for_scope(
    scope_name: str,
    chunks: list[tuple[date, date]],
    *,
    trigger: str,
    triggered_by: str | None,
    progress_cb: ProgressCb | None,
    base_offset: int,
    total_chunks: int,
) -> dict[str, Any]:
    """Inner loop shared by :func:`refresh_window_chunked` and
    :func:`backfill_since_golive`. Returns aggregated stats for one
    scope (``salesline`` or ``invoice``).
    """
    report_key = _REPORT_KEY[scope_name]
    out: dict[str, Any] = {
        "scope":          scope_name,
        "chunks_total":   len(chunks),
        "chunks_done":    0,
        "rows_in":        0,
        "errors":         [],
    }
    if not reporting_api.is_configured():
        msg = f"{scope_name} chunked refresh skipped -- reporting API not configured"
        log.warning(msg)
        out["errors"].append(msg)
        return out

    for idx, (cstart, cend) in enumerate(chunks, start=1):
        chunk_started = time.monotonic()
        try:
            n = _run_chunk(report_key, cstart, cend)
            out["rows_in"] += n
            out["chunks_done"] += 1
            log.info(
                "%s chunk %d/%d (%s..%s): %d rows in %.2fs (trigger=%s)",
                scope_name, idx, len(chunks),
                cstart.isoformat(), cend.isoformat(),
                n, time.monotonic() - chunk_started, trigger,
            )
            if progress_cb:
                try:
                    progress_cb({
                        "scope":         scope_name,
                        "chunk_index":   base_offset + idx,
                        "chunk_total":   total_chunks,
                        "chunk_start":   cstart.isoformat(),
                        "chunk_end":     cend.isoformat(),
                        "rows":          n,
                        "status":        "ok",
                    })
                except Exception:
                    log.exception("progress_cb raised; ignoring")
        except Exception as exc:
            err = (
                f"{scope_name} chunk {cstart.isoformat()}..{cend.isoformat()} "
                f"failed: {exc}"
            )
            log.exception(err)
            out["errors"].append(err)
            if progress_cb:
                try:
                    progress_cb({
                        "scope":         scope_name,
                        "chunk_index":   base_offset + idx,
                        "chunk_total":   total_chunks,
                        "chunk_start":   cstart.isoformat(),
                        "chunk_end":     cend.isoformat(),
                        "status":        "error",
                        "error":         str(exc),
                    })
                except Exception:
                    log.exception("progress_cb raised; ignoring")
    return out


def _refresh_range(*, scope: Scope, start: date, end: date,
                   trigger: str, triggered_by: str | None,
                   progress_cb: ProgressCb | None) -> dict[str, Any]:
    """Common driver: chunk ``[start, end]`` per requested scope."""
    chunks = _month_chunks(start, end)
    scopes = _scopes_for(scope)
    total_chunks = len(chunks) * len(scopes)
    log.info(
        "mirror chunked %s: scope=%s window=%s..%s chunks=%d (per scope=%d)",
        trigger, scope, start.isoformat(), end.isoformat(),
        total_chunks, len(chunks),
    )

    overall: dict[str, Any] = {
        "scope":          scope,
        "trigger":        trigger,
        "start":          start.isoformat(),
        "end":            end.isoformat(),
        "chunks_total":   total_chunks,
        "chunks_done":    0,
        "rows_in":        0,
        "errors":         [],
        "by_scope":       {},
    }

    started = time.monotonic()
    offset = 0
    for s in scopes:
        scope_result = _run_chunks_for_scope(
            s, chunks,
            trigger=trigger, triggered_by=triggered_by,
            progress_cb=progress_cb,
            base_offset=offset, total_chunks=total_chunks,
        )
        overall["by_scope"][s] = scope_result
        overall["chunks_done"] += scope_result["chunks_done"]
        overall["rows_in"] += scope_result["rows_in"]
        overall["errors"].extend(scope_result["errors"])
        offset += len(chunks)

    overall["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    log.info(
        "mirror chunked %s done: rows=%d chunks=%d/%d errors=%d elapsed=%dms",
        trigger, overall["rows_in"], overall["chunks_done"],
        total_chunks, len(overall["errors"]), overall["elapsed_ms"],
    )
    return overall


def refresh_window_chunked(*, scope: Scope = "all",
                           days_back: int = 180,
                           trigger: str = "manual",
                           triggered_by: str | None = None,
                           progress_cb: ProgressCb | None = None) -> dict[str, Any]:
    """Refresh the trailing ``days_back`` days, one calendar month at a time.

    Called by the daily cron and by the dashboard's "refresh now" button.
    Each chunk is a separate API call so a single bad month doesn't
    poison the rest. The mirror's piggyback path writes the rows.
    """
    today = get_today_eastern()
    start = max(D365_GO_LIVE, today - timedelta(days=days_back))
    return _refresh_range(
        scope=scope, start=start, end=today,
        trigger=trigger, triggered_by=triggered_by,
        progress_cb=progress_cb,
    )


def backfill_since_golive(*, scope: Scope = "all",
                          trigger: str = "manual",
                          triggered_by: str | None = None,
                          progress_cb: ProgressCb | None = None) -> dict[str, Any]:
    """Pull every calendar month from D365 go-live to today.

    Admin-only entry point. Expensive (~17 API calls per scope as of
    2026-05) so it's behind a button rather than running on a schedule.
    """
    today = get_today_eastern()
    return _refresh_range(
        scope=scope, start=D365_GO_LIVE, end=today,
        trigger=trigger, triggered_by=triggered_by,
        progress_cb=progress_cb,
    )
