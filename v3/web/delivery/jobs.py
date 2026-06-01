"""Wires report deliveries onto the durable job worker.

Endpoints/scheduler enqueue a ``report.deliver`` job (validating recipients up
front so the user gets immediate feedback); the worker builds, exports and
delivers off the request thread. A failed delivery raises so the job is marked
failed and surfaces in the run history.
"""

from __future__ import annotations

from web.auth.authorization import Authorization
from web.data.repositories.jobs import JobRepository
from web.delivery.service import DeliveryService
from web.jobs.worker import Handler, JobContext

DELIVERY_JOB_TYPE = "report.deliver"


def enqueue_delivery(job_repo: JobRepository, *, owner_user_id: int | None,
                     payload: dict) -> str:
    """Enqueue a delivery. Not deduped: each send is an intentional, distinct act."""
    return job_repo.enqueue(DELIVERY_JOB_TYPE, owner_user_id=owner_user_id, params=payload)


def make_delivery_handler(delivery: DeliveryService, authz: Authorization) -> Handler:
    def handler(ctx: JobContext) -> str:
        p = ctx.job.params
        # Re-resolve the owner and RE-AUTHORIZE live at execution time. The
        # identity/scope captured at enqueue can be stale (role changed, user
        # disabled, SharePoint revoked); trusting it could leak data. Fails closed.
        principal = authz.principal_for_user_id(ctx.job.owner_user_id)
        scope = authz.authorize_delivery(
            principal, p["report_key"], sharepoint=bool(p.get("sharepoint_path")))
        outcome = delivery.run_and_deliver(
            report_key=p["report_key"], identity=principal.email,
            visible_salesman_keys=scope,
            builder_version=p["builder_version"], params=p.get("params") or {},
            layout=p.get("layout") or {}, recipients=p.get("recipients", ""),
            subject=p.get("subject", ""), report_name=p.get("report_name") or p["report_key"],
            sharepoint_path=p.get("sharepoint_path", ""),
        )
        if not outcome.result.ok:
            raise RuntimeError(outcome.result.error or "Delivery failed")
        return f"outbox:{outcome.result.outbox_id}"

    return handler
