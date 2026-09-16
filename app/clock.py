"""One-minute schedule clock. Daemon thread, not APScheduler. Off under pytest."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import cadence
import catchup
import config
import hebcal
import store
from deliver import deliver_schedule

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows / no flock — claim_today_slot still serializes sends

log = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def start() -> None:
    global _thread
    if config.clock_disabled():
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="schedule-clock", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=2)


def _loop() -> None:
    while True:
        try:
            tick()
        except Exception:
            log.exception("schedule tick failed")
        if _stop.wait(60):
            break


def _lock_path() -> Path:
    path = config.db_path()
    return path.with_name(path.name + ".clock.lock")


def tick(now: datetime | None = None) -> int:
    """Fire every active due schedule. Returns how many were claimed this pass."""
    now = now or datetime.now(timezone.utc)
    lock_file = None
    if fcntl is not None:
        lock_path = _lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(lock_path, "a", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return 0
    try:
        return _tick_locked(now)
    finally:
        if lock_file is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_file.close()


def _tick_locked(now: datetime) -> int:
    mode, reason = hebcal.restriction(now)
    if mode == "hold":
        log.info("holding clock (%s); will retry next minute", reason)
        return 0
    claimed = 0
    for schedule in store.list_active_schedules():
        claimed += _consider(schedule, now, mode, reason)
    return claimed


def _consider(schedule: dict, now: datetime, mode: str, reason: str) -> int:
    cad = cadence.from_schedule(schedule)
    skip = hebcal.skip_sabbath_enabled(schedule.get("params"))
    last_run = schedule.get("last_run")
    due = cadence.due_now(cad, last_run, now)
    if mode == "hold" and due:
        log.info(
            "holding schedule %s (%s); will retry next minute",
            schedule["id"],
            reason,
        )
        return 0
    if mode == "assur" and skip and due:
        if not store.claim_today_slot(schedule["id"], now):
            return 0
        store.mark_schedule_run(
            schedule["id"],
            "skipped",
            f"Skipped ({reason or 'Shabbos'}); will run at the next scheduled time",
            at=now,
        )
        store.set_catch_up(schedule["id"], True, for_date=cadence.eastern_date_iso(now))
        return 1

    pending = bool(schedule.get("catch_up_pending"))
    skipped_iso = schedule.get("catch_up_for_date")
    action = "skip"
    if pending and skipped_iso:
        skipped = catchup.as_date(str(skipped_iso))
        if skipped is None:
            action = "reschedule"
        else:
            action = catchup.classify_action(
                schedule.get("params"), schedule["report_key"], skipped, cad
            )
    makeup = pending and catchup.makeup_due(
        cad, last_run, now, action=action, assur=mode == "assur"
    )
    regular = due and not (skip and mode == "assur")
    if pending:
        weekday = now.astimezone(cadence.EASTERN).weekday() if now.tzinfo else now.weekday()
        if weekday == 5 or (action == "reschedule" and weekday >= 5):
            regular = False
    if not makeup and not regular:
        return 0
    if not store.claim_today_slot(schedule["id"], now):
        return 0
    if pending:
        store.set_catch_up(schedule["id"], False)
    owner = store.get_user(schedule["owner_email"])
    if owner is None or not owner["is_active"]:
        store.mark_schedule_run(
            schedule["id"], "failure", "Schedule owner is missing or disabled.", at=now
        )
        return 1
    work = dict(schedule)
    if pending:
        work["catch_up_for_date"] = skipped_iso
    deliver_schedule(work, owner, at=now)
    return 1
