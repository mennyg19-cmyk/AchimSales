"""Durable ``schedule.run`` job: runs a stored schedule off the request thread.

Both the "Run now" button and the periodic cron tick enqueue this job; the
handler delegates to ScheduleRunner (which records the run + delivers).
"""

from __future__ import annotations

from web.data.repositories.jobs import JobRepository
from web.data.repositories.schedules import PERSONAL
from web.jobs.worker import Handler, JobContext
from web.scheduling.runner import ScheduleRunner

SCHEDULE_RUN_JOB_TYPE = "schedule.run"


def enqueue_schedule_run(job_repo: JobRepository, *, schedule_id: int,
                         schedule_type: str = PERSONAL,
                         owner_user_id: int | None = None) -> str:
    # Dedup so a cron tick that fires twice (coalesced) or overlaps a "Run now"
    # collapses to a single in-flight run per schedule.
    return job_repo.enqueue(
        SCHEDULE_RUN_JOB_TYPE, owner_user_id=owner_user_id,
        dedup_key=f"schedrun:{schedule_type}:{schedule_id}",
        params={"schedule_id": schedule_id, "schedule_type": schedule_type},
    )


def make_schedule_run_handler(runner: ScheduleRunner) -> Handler:
    def handler(ctx: JobContext) -> str:
        p = ctx.job.params
        run_id = runner.run(p["schedule_id"], p.get("schedule_type", PERSONAL))
        return f"run:{run_id}"

    return handler
