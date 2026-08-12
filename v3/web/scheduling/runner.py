"""Run one stored schedule through the delivery pipeline and record the result.

A schedule run is owner-scoped: a personal schedule delivers exactly the data its
owner is allowed to see (so a salesman's nightly email can't leak other reps'
rows). Master schedules are admin-owned and run unrestricted. Every run is
bracketed by a ``schedule_runs`` row so the history UI shows success/failure,
row count, and a full message (errors, skips, and success details).
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
                # Personal folder saves go to OneDrive — do not require SharePoint access.
                scope = self.authz.authorize_delivery(
                    principal, sched.report_key, sharepoint=False)
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
                od_user = identity if schedule_type == PERSONAL and sched.sharepoint_path else ""
                params = sched.params or {}
                no_data_all = bool(params.get("email_on_no_data"))
                no_data_me = bool(params.get("email_on_no_data_me_only"))
                outcome = self.delivery.run_and_deliver(
                    report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                    builder_version=spec.builder_version if spec else 1,
                    params=_report_params(params), layout=sched.layout,
                    recipients=sched.recipients, subject=subject, report_name=report_name,
                    sharepoint_path=sched.sharepoint_path,
                    filename_template=getattr(sched, "filename_template", "") or "",
                    onedrive_user=od_user,
                    cc_raw=str(params.get("email_cc") or ""),
                    bcc_raw=str(params.get("email_bcc") or ""),
                    email_on_empty=no_data_all or no_data_me,
                    empty_recipients_override=identity if (no_data_me and not no_data_all) else None,
                )
            meta = _output_meta(outcome)
            summary = _summary_message(outcome, ok=outcome.result.ok)
            self.run_repo.finish(
                run_id, status="success" if outcome.result.ok else "failure",
                rows=outcome.row_count, output_meta=meta, debug_log=summary,
            )
            if not outcome.result.ok:
                raise RuntimeError(outcome.result.error or "delivery failed")
        except Exception as exc:  # noqa: BLE001 - record then re-raise to fail the job
            log.exception("schedule run failed (%s:%s)", schedule_type, schedule_id)
            existing = self.run_repo.get(run_id)
            # Don't wipe a detailed finish() already written for a delivery failure.
            if existing is None or existing.status == "running":
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
        deliveries: list[dict] = []
        skip_notes: list[str] = []
        params = sched.params or {}

        if sched.recipients or sched.sharepoint_path:
            full = self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=builder_version, params=_report_params(params),
                layout=sched.layout, recipients=sched.recipients, subject=subject,
                report_name=report_name, sharepoint_path=sched.sharepoint_path,
                filename_template=getattr(sched, "filename_template", "") or "",
            )
            outcomes.append(full)
            deliveries.append(_delivery_leg(full, kind="full"))

        salesmen = SalesmanRepository(self.user_repo.db)
        for key in self._salesman_targets(params):
            email = salesmen.get_email(key)
            if not email:
                # Skip — don't fail the whole run after management copy already sent.
                note = f"{key}: skipped - no salesman email"
                skip_notes.append(note)
                deliveries.append({
                    "kind": "split", "salesman": key, "recipients": [], "ok": False,
                    "skipped": True, "error": "no salesman email", "rows": 0,
                    "send_channel": "", "sent": False,
                })
                continue
            split_params = _report_params(params)
            split_params["salesman"] = [key]
            outcome = self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=builder_version, params=split_params, layout=sched.layout,
                recipients=email, subject=f"{subject} - {key}",
                report_name=f"{report_name} - {key}", sharepoint_path="",
                filename_template=getattr(sched, "filename_template", "") or "",
            )
            outcomes.append(outcome)
            deliveries.append(_delivery_leg(outcome, kind="split", salesman=key))

        if not outcomes:
            return DeliveryOutcome(
                result=DeliveryResult(
                    ok=False,
                    error="; ".join(skip_notes) or "No delivery targets.",
                ),
                row_count=0,
                deliveries=deliveries,
            )
        ok = all(o.result.ok for o in outcomes)
        notes = [o.result.error for o in outcomes if o.result.error] + skip_notes
        recipients = [email for o in outcomes for email in o.result.recipients]
        eml_names = [o.result.eml_name for o in outcomes if o.result.eml_name]
        channels = [o.result.send_channel for o in outcomes if o.result.send_channel]
        result = DeliveryResult(
            ok=ok,
            error="; ".join(notes),
            recipients=recipients,
            eml_name=", ".join(eml_names),
            sent_via_smtp=any(o.result.sent_via_smtp for o in outcomes),
            send_channel=channels[0] if len(set(channels)) == 1 else ("mixed" if channels else ""),
            sharepoint_saved=any(o.result.sharepoint_saved for o in outcomes),
            sharepoint_url=next((o.result.sharepoint_url for o in outcomes if o.result.sharepoint_url), None),
            sharepoint_error=next((o.result.sharepoint_error for o in outcomes if o.result.sharepoint_error), None),
            outbox_id=next((o.result.outbox_id for o in outcomes if o.result.outbox_id is not None), None),
        )
        return DeliveryOutcome(
            result=result, row_count=sum(o.row_count for o in outcomes), deliveries=deliveries,
        )

    def _salesman_targets(self, params: dict | None) -> list[str]:
        p = params or {}
        selected = _as_str_list(p.get("salesman"))
        if selected and p.get("email_to_salesmen"):
            return selected
        email_keys = _as_str_list(p.get("email_salesman_keys"))
        return email_keys


_DELIVERY_PARAM_KEYS = {
    "split_by_salesman", "email_to_salesmen", "email_salesman_keys",
    "email_cc", "email_bcc", "email_on_no_data", "email_on_no_data_me_only",
}


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


def _delivery_leg(outcome: DeliveryOutcome, *, kind: str, salesman: str = "") -> dict:
    r = outcome.result
    return {
        "kind": kind,
        "salesman": salesman,
        "recipients": list(r.recipients),
        "ok": r.ok,
        "skipped": False,
        "error": r.error or r.sharepoint_error or "",
        "rows": outcome.row_count,
        "send_channel": r.send_channel,
        "sent": r.sent_via_smtp,
        "sharepoint_saved": r.sharepoint_saved,
        "sharepoint_url": r.sharepoint_url or "",
        "eml": r.eml_name,
        "outbox_id": r.outbox_id,
    }


def _output_meta(outcome: DeliveryOutcome) -> dict:
    r = outcome.result
    meta = {
        "summary": _summary_message(outcome, ok=r.ok),
        "outbox_id": r.outbox_id,
        "eml": r.eml_name,
        "sent_smtp": r.sent_via_smtp,
        "send_channel": r.send_channel,
        "sharepoint_saved": r.sharepoint_saved,
        "sharepoint_url": r.sharepoint_url,
        "sharepoint_error": r.sharepoint_error,
        "recipients": r.recipients,
        "error": r.error or "",
    }
    if outcome.deliveries:
        meta["deliveries"] = outcome.deliveries
    return meta


def _summary_message(outcome: DeliveryOutcome, *, ok: bool) -> str:
    """Plain-English line for History: success details and/or failures/skips."""
    r = outcome.result
    bits: list[str] = []
    if outcome.deliveries:
        for d in outcome.deliveries:
            if d.get("skipped"):
                bits.append(f"{d.get('salesman')}: skipped — no salesman email")
                continue
            who = ", ".join(d.get("recipients") or []) or "(no email)"
            channel = d.get("send_channel") or ("sent" if d.get("sent") else "outbox")
            label = "Full workbook" if d.get("kind") == "full" else f"Split {d.get('salesman')}"
            if d.get("ok"):
                part = f"{label} → {who} via {channel}"
                if d.get("sharepoint_saved"):
                    part += " (+ SharePoint)"
                bits.append(part)
            else:
                bits.append(f"{label} failed: {d.get('error') or 'delivery failed'}")
    else:
        if r.recipients:
            channel = r.send_channel or ("sent" if r.sent_via_smtp else "outbox")
            bits.append(f"Email → {', '.join(r.recipients)} via {channel}")
        if r.sharepoint_saved:
            bits.append("SharePoint saved" + (f" ({r.sharepoint_url})" if r.sharepoint_url else ""))
        elif r.sharepoint_error:
            bits.append(f"SharePoint failed: {r.sharepoint_error}")
        if r.error and not ok:
            bits.append(r.error)
    if not bits:
        return "OK" if ok else (r.error or "delivery failed")
    prefix = "OK: " if ok else "Failed: "
    # On success, skip notes may still live in r.error — append if not already covered.
    body = "; ".join(bits)
    if ok and r.error and r.error not in body:
        body = f"{body}; {r.error}"
    return prefix + body
