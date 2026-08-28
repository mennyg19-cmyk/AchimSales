"""Durable ``schedule.run`` job: runs a stored schedule off the request thread.

Both the "Send now" button and the periodic cron tick enqueue this job; the
handler delegates to ScheduleRunner (which records the run + delivers).
"""

from __future__ import annotations

import uuid

from web.data.repositories.jobs import JobRepository
from web.data.repositories.schedules import PERSONAL
from web.jobs.worker import Handler, JobContext
from web.scheduling.runner import ScheduleRunner

SCHEDULE_RUN_JOB_TYPE = "schedule.run"


def enqueue_schedule_run(job_repo: JobRepository, *, schedule_id: int,
                         schedule_type: str = PERSONAL,
                         owner_user_id: int | None = None,
                         ignore_sabbath: bool = False,
                         catch_up_for_date: str | None = None,
                         include_regular: bool = True,
                         trigger: str = "scheduled") -> str:
    # Clock ticks collapse to one in-flight run per schedule. Send now is a
    # separate job so it cannot steal the scheduled slot's dedup key.
    if trigger == "manual":
        dedup_key = f"schedrun:{schedule_type}:{schedule_id}:manual:{uuid.uuid4().hex}"
    else:
        dedup_key = f"schedrun:{schedule_type}:{schedule_id}"
    return job_repo.enqueue(
        SCHEDULE_RUN_JOB_TYPE, owner_user_id=owner_user_id,
        dedup_key=dedup_key,
        params={"schedule_id": schedule_id, "schedule_type": schedule_type,
                "ignore_sabbath": bool(ignore_sabbath),
                "catch_up_for_date": catch_up_for_date or "",
                "include_regular": bool(include_regular),
                "trigger": trigger},
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
        )
        ctx.abort_if_cancelled()
        return f"run:{run_id}"

    return handler
