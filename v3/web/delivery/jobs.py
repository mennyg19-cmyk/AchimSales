"""Wires report deliveries onto the durable job worker.

Endpoints/scheduler enqueue a ``report.deliver`` job (validating recipients up
front so the user gets immediate feedback); the worker builds, exports and
delivers off the request thread. A failed delivery raises so the job is marked
failed and surfaces in the run history.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from web.auth.authorization import Authorization
from web.data.repositories.delivery_legs import DeliveryLegRepository
from web.data.repositories.jobs import JobRepository
from web.delivery.execute import deliver_with_legs
from web.delivery.filename_template import parse_frozen_when
from web.delivery.service import DeliveryService
from web.jobs.worker import Handler, JobContext
from web.scheduling import cadence as C

DELIVERY_JOB_TYPE = "report.deliver"


def enqueue_delivery(job_repo: JobRepository, *, owner_user_id: int | None,
                     payload: dict) -> str:
    """Enqueue a delivery. Not deduped: each send is an intentional, distinct act."""
    params = dict(payload or {})
    params.setdefault("slot_id", f"manual-deliver:{uuid.uuid4().hex}")
    if not params.get("slot_when"):
        now = datetime.now(timezone.utc)
        params["slot_when"] = now.isoformat()
        params.setdefault("slot_day", C.eastern_date_iso(now))
    return job_repo.enqueue(DELIVERY_JOB_TYPE, owner_user_id=owner_user_id, params=params)


def make_delivery_handler(delivery: DeliveryService, authz: Authorization) -> Handler:
    def handler(ctx: JobContext) -> str:
        p = ctx.job.params
        # Re-resolve the owner and RE-AUTHORIZE live at execution time. The
        # identity/scope captured at enqueue can be stale (role changed, user
        # disabled, SharePoint revoked); trusting it could leak data. Fails closed.
        principal = authz.principal_for_user_id(ctx.job.owner_user_id)
        scope = authz.authorize_delivery(
            principal, p["report_key"], sharepoint=bool(p.get("sharepoint_path")))
        outcome = deliver_with_legs(
            delivery, DeliveryLegRepository(authz.db),
            slot_id=str(p.get("slot_id") or ctx.job.id),
            job_id=ctx.job.id,
            run_id=None,
            window=p.get("params") or {},
            report_key=p["report_key"], identity=principal.email,
            visible_salesman_keys=scope,
            builder_version=p["builder_version"], params=p.get("params") or {},
            layout=p.get("layout") or {}, recipients=p.get("recipients", ""),
            subject=p.get("subject", ""), report_name=p.get("report_name") or p["report_key"],
            sharepoint_path=p.get("sharepoint_path", ""),
            filename_template=p.get("filename_template") or "",
            schedule_name=p.get("schedule_name") or "",
            cancel_check=ctx.is_cancelled,
            when=parse_frozen_when(
                str(p.get("slot_when") or ""), str(p.get("slot_day") or ""),
            ),
            retry_attempt_key=str(p.get("retry_attempt_key") or ""),
        )
        if outcome.result.unknown:
            from web.delivery.reconcile import alert_unknown_delivery
            from web.data.repositories.app_settings import AppSettingsRepository
            key = outcome.unknown_attempt_key
            alert_unknown_delivery(
                authz.db, AppSettingsRepository(authz.db), delivery=delivery,
                subject="[UNKNOWN] email-now send",
                body=outcome.result.error or "Graph may have accepted this send.",
                attempt_key=key,
            )
            return f"unknown:{outcome.result.outbox_id or key}"
        if not outcome.result.ok:
            raise RuntimeError(outcome.result.error or "Delivery failed")
        return f"outbox:{outcome.result.outbox_id}"

    return handler
