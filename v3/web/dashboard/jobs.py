"""Wires the dashboard mirror refresh onto the durable job worker.

A refresh is a single global job (deduped) so a manual "Refresh" and the
4-hourly cron tick collapse to one run rather than stacking. The handler just
calls MirrorService.rebuild().
"""

from __future__ import annotations

from web.dashboard.mirror import MirrorService
from web.data.repositories.jobs import JobRepository
from web.jobs.worker import Handler, JobContext

DASHBOARD_REFRESH_JOB_TYPE = "dashboard.refresh"
_DEDUP_KEY = "dashboard.refresh"


def enqueue_refresh(job_repo: JobRepository, *, owner_user_id: int | None = None) -> str:
    return job_repo.enqueue(
        DASHBOARD_REFRESH_JOB_TYPE, owner_user_id=owner_user_id, dedup_key=_DEDUP_KEY, params={})


def make_refresh_handler(mirror: MirrorService) -> Handler:
    def handler(ctx: JobContext) -> str:
        count = mirror.rebuild()
        return f"customers={count}"

    return handler
