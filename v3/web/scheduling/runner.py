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
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.users import UserRepository
from web.delivery.email import DeliveryResult
from web.delivery.service import DeliveryOutcome, DeliveryService

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
            # Re-authorize the owner live (personal schedules only; masters are
            # admin-owned + unrestricted). A run that the owner can no longer
            # perform - report access pulled, account disabled, SharePoint revoked
            # - fails closed here instead of delivering stale-scoped data.
            if schedule_type != MASTER:
                principal = self.authz.principal_for_user_id(sched.owner_user_id)
                scope = self.authz.authorize_delivery(
                    principal, sched.report_key,
                    sharepoint=bool(sched.sharepoint_path))
                identity = principal.email
            report_name = spec.title if spec else sched.report_key
            subject = self._subject(sched, schedule_type, report_name)
            if schedule_type == MASTER and self._salesman_targets(sched.params):
                outcome = self._run_master_fanout(
                    sched=sched, identity=identity, scope=scope,
                    builder_version=spec.builder_version if spec else 1,
                    subject=subject, report_name=report_name,
                )
            else:
                outcome = self.delivery.run_and_deliver(
                    report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                    builder_version=spec.builder_version if spec else 1,
                    params=_report_params(sched.params), layout=sched.layout,
                    recipients=sched.recipients, subject=subject, report_name=report_name,
                    sharepoint_path=sched.sharepoint_path,
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

    def _run_master_fanout(self, *, sched, identity: str,
                           scope: set[str] | None, builder_version: int,
                           subject: str, report_name: str) -> DeliveryOutcome:
        outcomes: list[DeliveryOutcome] = []
        debug_lines: list[str] = []
        params = sched.params or {}

        if sched.recipients or sched.sharepoint_path:
            outcomes.append(self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=builder_version, params=_report_params(params),
                layout=sched.layout, recipients=sched.recipients, subject=subject,
                report_name=report_name, sharepoint_path=sched.sharepoint_path,
            ))

        salesmen = SalesmanRepository(self.user_repo.db)
        for key in self._salesman_targets(params):
            email = salesmen.get_email(key)
            if not email:
                # Skip — don't fail the whole run after management copy already sent.
                debug_lines.append(f"{key}: skipped - no salesman email")
                continue
            split_params = _report_params(params)
            split_params["salesman"] = [key]
            outcome = self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=builder_version, params=split_params, layout=sched.layout,
                recipients=email, subject=f"{subject} - {key}",
                report_name=f"{report_name} - {key}", sharepoint_path="",
            )
            if not outcome.result.ok:
                debug_lines.append(f"{key}: {outcome.result.error or 'delivery failed'}")
            outcomes.append(outcome)

        if not outcomes:
            return DeliveryOutcome(
                result=DeliveryResult(
                    ok=False,
                    error="; ".join(debug_lines) or "No delivery targets.",
                ),
                row_count=0,
            )
        ok = all(o.result.ok for o in outcomes)
        notes = [o.result.error for o in outcomes if o.result.error] + debug_lines
        recipients = [email for o in outcomes for email in o.result.recipients]
        eml_names = [o.result.eml_name for o in outcomes if o.result.eml_name]
        result = DeliveryResult(
            ok=ok,
            # Notes land in schedule_runs.debug_log (skips on success; failures on fail).
            error="; ".join(notes),
            recipients=recipients,
            eml_name=", ".join(eml_names),
            sent_via_smtp=any(o.result.sent_via_smtp for o in outcomes),
            sharepoint_saved=any(o.result.sharepoint_saved for o in outcomes),
            sharepoint_url=next((o.result.sharepoint_url for o in outcomes if o.result.sharepoint_url), None),
            sharepoint_error=next((o.result.sharepoint_error for o in outcomes if o.result.sharepoint_error), None),
            outbox_id=next((o.result.outbox_id for o in outcomes if o.result.outbox_id is not None), None),
        )
        return DeliveryOutcome(result=result, row_count=sum(o.row_count for o in outcomes))

    def _salesman_targets(self, params: dict | None) -> list[str]:
        p = params or {}
        selected = _as_str_list(p.get("salesman"))
        if selected and p.get("email_to_salesmen"):
            return selected
        email_keys = _as_str_list(p.get("email_salesman_keys"))
        return email_keys


_DELIVERY_PARAM_KEYS = {"split_by_salesman", "email_to_salesmen", "email_salesman_keys"}


def _report_params(params: dict | None) -> dict:
    return {k: v for k, v in (params or {}).items() if k not in _DELIVERY_PARAM_KEYS}


def _as_str_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    if "," in s:
        return [p.strip() for p in s.split(",") if p.strip()]
    return [p for p in s.split() if p]
