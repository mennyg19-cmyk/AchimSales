"""Run one stored schedule through the delivery pipeline and record the result.

A schedule run is owner-scoped: a personal schedule delivers exactly the data its
owner is allowed to see (so a salesman's nightly email can't leak other reps'
rows). Master schedules are admin-owned and run unrestricted. Every run is
bracketed by a ``schedule_runs`` row so the history UI shows success/failure,
row count, and a debug line.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from report_engine import registry
from web.auth.authorization import Authorization
from web.auth.principal import Principal
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import UserRepository
from web.delivery.service import DeliveryService

log = logging.getLogger(__name__)


class ScheduleRunner:
    def __init__(self, *, schedule_repo: ScheduleRepository,
                 master_repo: MasterScheduleRepository, run_repo: ScheduleRunRepository,
                 user_repo: UserRepository, authz: Authorization, delivery: DeliveryService):
        self.schedule_repo = schedule_repo
        self.master_repo = master_repo
        self.run_repo = run_repo
        self.user_repo = user_repo
        self.authz = authz
        self.delivery = delivery

    def run(self, schedule_id: int, schedule_type: str = PERSONAL) -> int:
        sched = self._load(schedule_id, schedule_type)
        if sched is None:
            raise RuntimeError(f"schedule {schedule_type}:{schedule_id} not found")

        run_id = self.run_repo.start(schedule_id, schedule_type)
        try:
            identity, scope = self._scope(sched, schedule_type)
            spec = registry.get(sched.report_key)
            report_name = spec.title if spec else sched.report_key
            subject = self._subject(sched, schedule_type, report_name)
            outcome = self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=spec.builder_version if spec else 1,
                params=sched.params, layout=sched.layout, recipients=sched.recipients,
                subject=subject, report_name=report_name, sharepoint_path=sched.sharepoint_path,
            )
            r = outcome.result
            self.run_repo.finish(
                run_id, status="success" if r.ok else "failure", rows=outcome.row_count,
                output_meta={"outbox_id": r.outbox_id, "eml": r.eml_name,
                             "sent_smtp": r.sent_via_smtp, "sharepoint_saved": r.sharepoint_saved,
                             "sharepoint_url": r.sharepoint_url, "recipients": r.recipients},
                debug_log=(r.error or r.sharepoint_error or ""),
            )
            if not r.ok:
                raise RuntimeError(r.error or "delivery failed")
        except Exception as exc:  # noqa: BLE001 - record then re-raise to fail the job
            log.exception("schedule run failed (%s:%s)", schedule_type, schedule_id)
            self.run_repo.finish(run_id, status="failure", debug_log=str(exc))
            raise
        return run_id

    # -- internals ----------------------------------------------------------

    def _load(self, schedule_id: int, schedule_type: str):
        if schedule_type == MASTER:
            return self.master_repo.get(schedule_id)
        return self.schedule_repo.get_any(schedule_id)

    def _scope(self, sched, schedule_type: str):
        """Return (identity, visible_salesman_keys) for the delivery build."""
        if schedule_type == MASTER:
            return "master@scheduler", None  # admin-owned: unrestricted
        owner = self._owner(sched.owner_user_id)
        if owner is None:
            return "scheduler", set()  # unknown owner -> see nothing (fail closed)
        principal = Principal(email=owner.email, name=owner.display_name or owner.email,
                              role=owner.role)
        return owner.email, self.authz.visible_salesman_keys(principal)

    def _owner(self, user_id: int):
        # UserRepository has get_by_email; fetch by id via a tiny direct query.
        with self.user_repo.db.precious() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        from web.data.repositories.users import User
        return User.from_row(row) if row else None

    def _subject(self, sched, schedule_type: str, report_name: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        label = "Master" if schedule_type == MASTER else "Scheduled"
        name = getattr(sched, "name", "") or report_name
        return f"{label}: {name} ({stamp})"
