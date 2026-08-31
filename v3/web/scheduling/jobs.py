"""Durable ``schedule.run`` job: runs a stored schedule off the request thread.

Both the "Send now" button and the periodic cron tick enqueue this job; the
handler delegates to ScheduleRunner (which records the run + delivers).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from web.data.repositories.delivery_legs import parse_scheduled_slot_id, scheduled_slot_id
from web.data.repositories.jobs import JobRepository
from web.data.repositories.schedules import PERSONAL
from web.jobs.worker import Handler, JobContext
from web.scheduling import cadence as C
from web.scheduling.runner import ScheduleRunner

SCHEDULE_RUN_JOB_TYPE = "schedule.run"


def enqueue_schedule_run(job_repo: JobRepository, *, schedule_id: int,
                         schedule_type: str = PERSONAL,
                         owner_user_id: int | None = None,
                         ignore_sabbath: bool = False,
                         catch_up_for_date: str | None = None,
                         include_regular: bool = True,
                         trigger: str = "scheduled",
                         now: datetime | None = None,
                         slot_id: str | None = None,
                         slot_day: str | None = None) -> str:
    # Clock ticks collapse to one in-flight run per schedule. Send now is a
    # separate job so it cannot steal the scheduled slot's dedup key. Operator
    # retry passes the frozen slot_id so attempt_key matches the reopened leg.
    now = now or datetime.now(timezone.utc)
    frozen_day = slot_day or C.eastern_date_iso(now)
    if slot_id:
        frozen_slot = slot_id
        dedup_key = f"schedrun-retry:{schedule_type}:{schedule_id}:{frozen_slot}"
    elif trigger == "manual":
        frozen_slot = f"manual:{uuid.uuid4().hex}"
        dedup_key = f"schedrun:{schedule_type}:{schedule_id}:{frozen_slot}"
    else:
        frozen_slot = scheduled_slot_id(
            schedule_type=schedule_type, schedule_id=schedule_id, slot_day=frozen_day,
            catch_up_for_date=catch_up_for_date or "", include_regular=include_regular,
        )
        dedup_key = f"schedrun:{schedule_type}:{schedule_id}"
    return job_repo.enqueue(
        SCHEDULE_RUN_JOB_TYPE, owner_user_id=owner_user_id,
        dedup_key=dedup_key,
        params={"schedule_id": schedule_id, "schedule_type": schedule_type,
                "ignore_sabbath": bool(ignore_sabbath),
                "catch_up_for_date": catch_up_for_date or "",
                "include_regular": bool(include_regular),
                "trigger": trigger,
                "slot_id": frozen_slot,
                "slot_day": frozen_day},
    )


def enqueue_leg_retry(job_repo: JobRepository, leg) -> str | None:
    """Queue a run that uses this leg's frozen slot_id. None if we cannot rebuild it."""
    from web.delivery.jobs import DELIVERY_JOB_TYPE, enqueue_delivery

    original = job_repo.get(leg.job_id) if leg.job_id else None
    if original is not None and original.status in ("queued", "running"):
        return None
    if original is not None and original.type == SCHEDULE_RUN_JOB_TYPE:
        p = original.params
        return enqueue_schedule_run(
            job_repo,
            schedule_id=int(p["schedule_id"]),
            schedule_type=str(p.get("schedule_type") or PERSONAL),
            owner_user_id=original.owner_user_id,
            ignore_sabbath=True,
            catch_up_for_date=p.get("catch_up_for_date") or None,
            include_regular=bool(p.get("include_regular", True)),
            trigger="manual",
            slot_id=leg.slot_id,
            slot_day=str(p.get("slot_day") or "") or None,
        )
    if original is not None and original.type == DELIVERY_JOB_TYPE:
        payload = dict(original.params)
        payload["slot_id"] = leg.slot_id
        return enqueue_delivery(
            job_repo, owner_user_id=original.owner_user_id, payload=payload)
    parsed = parse_scheduled_slot_id(leg.slot_id)
    if parsed is None:
        return None
    return enqueue_schedule_run(
        job_repo,
        schedule_id=parsed["schedule_id"],
        schedule_type=parsed["schedule_type"],
        owner_user_id=original.owner_user_id if original is not None else None,
        ignore_sabbath=True,
        catch_up_for_date=parsed["catch_up_for_date"] or None,
        include_regular=parsed["include_regular"],
        trigger="manual",
        slot_id=leg.slot_id,
        slot_day=parsed["slot_day"],
    )


def make_schedule_run_handler(runner: ScheduleRunner) -> Handler:
    def handler(ctx: JobContext) -> str:
        ctx.abort_if_cancelled()
        p = ctx.job.params
        run_id = runner.run(
            p["schedule_id"], p.get("schedule_type", PERSONAL),
            ignore_sabbath=bool(p.get("ignore_sabbath")),
            catch_up_for_date=(p.get("catch_up_for_date") or None),
            include_regular=bool(p.get("include_regular", True)),
            trigger=p.get("trigger") or "scheduled",
            cancel_check=ctx.is_cancelled,
            slot_id=str(p.get("slot_id") or ""),
            slot_day=str(p.get("slot_day") or ""),
            job_id=ctx.job.id,
        )
        ctx.abort_if_cancelled()
        return f"run:{run_id}"

    return handler
