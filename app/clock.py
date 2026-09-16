"""One-minute schedule clock. Daemon thread, not APScheduler. Off under pytest."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import cadence
import config
import hebcal
import store
from deliver import deliver_schedule

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


def tick(now: datetime | None = None) -> int:
    """Fire every active due schedule. Returns how many were claimed this pass."""
    now = now or datetime.now(timezone.utc)
    mode, reason = hebcal.restriction(now)
    claimed = 0
    for schedule in store.list_active_schedules():
        cad = cadence.from_schedule(schedule)
        if not cadence.due_now(cad, schedule.get("last_run"), now):
            continue
        if mode == "hold":
            log.info(
                "holding schedule %s (%s); will retry next minute",
                schedule["id"],
                reason,
            )
            continue
        skip = hebcal.skip_sabbath_enabled(schedule.get("params"))
        if mode == "assur" and skip:
            if not store.claim_today_slot(schedule["id"], now):
                continue
            store.mark_schedule_run(
                schedule["id"],
                "skipped",
                f"Skipped ({reason or 'Shabbos'}); will run at the next scheduled time",
                at=now,
            )
            claimed += 1
            continue
        if not store.claim_today_slot(schedule["id"], now):
            continue
        owner = store.get_user(schedule["owner_email"])
        if owner is None or not owner["is_active"]:
            store.mark_schedule_run(
                schedule["id"], "failure", "Schedule owner is missing or disabled.", at=now
            )
            claimed += 1
            continue
        deliver_schedule(schedule, owner, at=now)
        claimed += 1
    return claimed
