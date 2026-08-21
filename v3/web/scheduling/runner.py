"""Run one stored schedule through the delivery pipeline and record the result.

A schedule run is owner-scoped: a personal schedule delivers exactly the data its
owner is allowed to see (so a salesman's nightly email can't leak other reps'
rows). Master schedules are admin-owned and run unrestricted. Every run is
bracketed by a ``schedule_runs`` row so the history UI shows success/failure,
row count, and a full message (errors, skips, and success details).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from report_engine import registry
from web.auth.authorization import Authorization
from web.auth.principal import Principal
from web.data.repositories.app_settings import AppSettingsRepository
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
from web.scheduling.sabbath import melacha_assur, skip_sabbath_enabled

log = logging.getLogger(__name__)

# One extra full run after a short wait so a dropped Graph call is not the
# last word. [FAIL] mail goes out only after this is exhausted.
_TRANSIENT_ATTEMPTS = 2
_TRANSIENT_RETRY_WAIT_S = 30


class ScheduleRunner:
    def __init__(self, *, schedule_repo: ScheduleRepository,
                 master_repo: MasterScheduleRepository, run_repo: ScheduleRunRepository,
                 user_repo: UserRepository, authz: Authorization, delivery: DeliveryService,
                 settings: AppSettingsRepository | None = None):
        self.schedule_repo = schedule_repo
        self.master_repo = master_repo
        self.run_repo = run_repo
        self.user_repo = user_repo
        self.authz = authz
        self.delivery = delivery
        self.settings = settings or AppSettingsRepository(user_repo.db)

    def run(self, schedule_id: int, schedule_type: str = PERSONAL,
            *, ignore_sabbath: bool = False) -> int:
        sched = self._load(schedule_id, schedule_type)
        if sched is None:
            raise RuntimeError(f"schedule {schedule_type}:{schedule_id} not found")

        run_id = self.run_repo.start(schedule_id, schedule_type)
        try:
            if not ignore_sabbath and skip_sabbath_enabled(getattr(sched, "params", None)):
                assur, reason = melacha_assur()
                if assur:
                    self.run_repo.finish(
                        run_id, status="skipped",
                        debug_log=f"Skipped ({reason or 'Shabbos'}); will run after Shabbos",
                    )
                    self._set_catch_up(schedule_id, schedule_type, True)
                    return run_id
            identity, scope = self._scope(sched, schedule_type)
            spec = registry.get(sched.report_key)
            params = _with_viewer_limits(self.authz, sched, schedule_type, sched.params)
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
            test_to = self._company_test_recipients(schedule_type)
            if test_to is not None:
                subject = f"[TEST] {subject}"
            od_user = "" if test_to else _onedrive_user(sched, schedule_type, identity)
            for attempt in range(1, _TRANSIENT_ATTEMPTS + 1):
                try:
                    if schedule_type == MASTER and self._salesman_targets(params):
                        outcome = self._run_master_fanout(
                            sched=sched, identity=identity, scope=scope,
                            builder_version=spec.builder_version if spec else 1,
                            subject=subject, report_name=report_name,
                            onedrive_user=od_user, test_to=test_to,
                            params=params,
                        )
                    else:
                        no_data_all = bool(params.get("email_on_no_data"))
                        no_data_me = bool(params.get("email_on_no_data_me_only"))
                        test_empty = self.settings.test_emails()
                        empty_to_test = no_data_me and not no_data_all and bool(test_empty)
                        outcome = self.delivery.run_and_deliver(
                            report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                            builder_version=spec.builder_version if spec else 1,
                            params=_report_params(params), layout=sched.layout,
                            recipients="; ".join(test_to) if test_to else sched.recipients,
                            subject=subject, report_name=report_name,
                            sharepoint_path="" if test_to else sched.sharepoint_path,
                            filename_template=getattr(sched, "filename_template", "") or "",
                            onedrive_user=od_user,
                            cc_raw="" if test_to else str(params.get("email_cc") or ""),
                            bcc_raw="" if test_to else str(params.get("email_bcc") or ""),
                            email_on_empty=no_data_all or empty_to_test,
                            empty_recipients_override=(
                                None if test_to
                                else ("; ".join(test_empty) if empty_to_test else None)
                            ),
                            schedule_name=getattr(sched, "name", "") or report_name,
                        )
                    if not outcome.result.ok:
                        raise RuntimeError(outcome.result.error or "delivery failed")
                    meta = _output_meta(outcome)
                    summary = _summary_message(outcome, ok=True)
                    self.run_repo.finish(
                        run_id, status="success",
                        rows=outcome.row_count, output_meta=meta, debug_log=summary,
                    )
                    self._set_catch_up(schedule_id, schedule_type, False)
                    break
                except Exception:
                    if attempt >= _TRANSIENT_ATTEMPTS:
                        raise
                    log.warning(
                        "schedule %s:%s attempt %d/%d failed; retrying in %ss",
                        schedule_type, schedule_id, attempt, _TRANSIENT_ATTEMPTS,
                        _TRANSIENT_RETRY_WAIT_S, exc_info=True,
                    )
                    time.sleep(_TRANSIENT_RETRY_WAIT_S)
        except Exception as exc:  # noqa: BLE001 - record then re-raise to fail the job
            log.exception("schedule run failed (%s:%s)", schedule_type, schedule_id)
            existing = self.run_repo.get(run_id)
            # Don't wipe a detailed finish() already written for a delivery failure.
            if existing is None or existing.status == "running":
                self.run_repo.finish(run_id, status="failure", debug_log=str(exc))
            self._notify_failure(sched, schedule_type, str(exc))
            raise
        return run_id

    # -- internals ----------------------------------------------------------

    def _load(self, schedule_id: int, schedule_type: str):
        if schedule_type == MASTER:
            return self.master_repo.get(schedule_id)
        return self.schedule_repo.get_any(schedule_id)

    def _set_catch_up(self, schedule_id: int, schedule_type: str, pending: bool) -> None:
        if schedule_type == MASTER:
            self.master_repo.set_catch_up(schedule_id, pending)
        else:
            self.schedule_repo.set_catch_up(schedule_id, pending)

    def _scope(self, sched, schedule_type: str):
        """Return (identity, visible_salesman_keys) for the delivery build."""
        if schedule_type == MASTER:
            run_as = getattr(sched, "run_as_user_id", None)
            owner_id = getattr(sched, "owner_user_id", None)
            scoped_id = run_as or owner_id
            if scoped_id:
                principal = self.authz.principal_for_user_id(scoped_id)
                if principal is None:
                    return "scheduler", set()
                if not principal.is_privileged:
                    path = bool(getattr(sched, "sharepoint_path", ""))
                    od = _onedrive_user(sched, MASTER, principal.email)
                    scope = self.authz.authorize_delivery(
                        principal, sched.report_key, sharepoint=path and not od)
                    return principal.email, scope
            return "master@scheduler", None  # unscoped company run
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

    def _company_test_recipients(self, schedule_type: str) -> list[str] | None:
        """Test-mode address list for company schedules, or None to send as stored."""
        if schedule_type != MASTER:
            return None
        if not self.settings.is_schedule_test_mode():
            return None
        emails = self.settings.test_emails()
        if not emails:
            raise RuntimeError(
                "Test mode is on but no test emails are set. "
                "Add addresses in Settings or turn test mode off."
            )
        return emails

    def _notify_failure(self, sched, schedule_type: str, error: str) -> None:
        """Mail the test-email list. Runs even when test mode is off."""
        emails = self.settings.test_emails()
        if not emails:
            log.warning(
                "Schedule failed but no test emails are set; not sending a failure notice"
            )
            return
        email = getattr(self.delivery, "email", None)
        send = getattr(email, "send_notice", None) if email is not None else None
        if send is None:
            return
        name = getattr(sched, "name", None) or getattr(sched, "report_key", "schedule")
        kind = "Company" if schedule_type == MASTER else "Personal"
        body = (
            f"{kind} schedule failed.\n\n"
            f"Schedule: {name}\n"
            f"Report: {getattr(sched, 'report_key', '')}\n"
            f"Error: {error}\n"
        )
        try:
            send(to=emails, subject=f"[FAIL] {name}", body_text=body)
        except Exception:  # noqa: BLE001 - never hide the original failure
            log.exception("Could not send schedule failure notice")

    def _subject(self, sched, schedule_type: str, report_name: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        label = "Master" if schedule_type == MASTER else "Scheduled"
        name = getattr(sched, "name", "") or report_name
        return f"{label}: {name} ({stamp})"

    def _run_master_fanout(self, *, sched, identity: str,
                           scope: set[str] | None, builder_version: int,
                           subject: str, report_name: str,
                           onedrive_user: str = "",
                           test_to: list[str] | None = None,
                           params: dict | None = None) -> DeliveryOutcome:
        outcomes: list[DeliveryOutcome] = []
        deliveries: list[dict] = []
        skip_notes: list[str] = []
        params = params if params is not None else (sched.params or {})
        test_recips = "; ".join(test_to) if test_to else ""
        sched_name = getattr(sched, "name", "") or report_name

        if sched.recipients or sched.sharepoint_path:
            full = self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=builder_version, params=_report_params(params),
                layout=sched.layout,
                recipients=test_recips if test_to else sched.recipients,
                subject=subject,
                report_name=report_name,
                sharepoint_path="" if test_to else sched.sharepoint_path,
                filename_template=getattr(sched, "filename_template", "") or "",
                onedrive_user="" if test_to else onedrive_user,
                schedule_name=sched_name,
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
                recipients=test_recips if test_to else email,
                subject=f"{subject} - {key}",
                report_name=f"{report_name} - {key}", sharepoint_path="",
                filename_template=getattr(sched, "filename_template", "") or "",
                schedule_name=f"{sched_name} - {key}",
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
        if email_keys:
            return email_keys
        if _as_bool(p.get("split_by_salesman")):
            return SalesmanRepository(self.user_repo.db).keys_with_email()
        return []


_DELIVERY_PARAM_KEYS = {
    "split_by_salesman", "email_to_salesmen", "email_salesman_keys",
    "email_cc", "email_bcc", "email_on_no_data", "email_on_no_data_me_only",
    "folder_kind", "skip_sabbath",
}


def _onedrive_user(sched, schedule_type: str, identity: str) -> str:
    path = getattr(sched, "sharepoint_path", "") or ""
    if not path:
        return ""
    if schedule_type == PERSONAL:
        return identity
    kind = str((getattr(sched, "params", None) or {}).get("folder_kind") or "")
    if kind == "onedrive":
        return identity
    if kind == "sharepoint":
        return ""
    if not getattr(sched, "is_shared", True):
        return identity
    return ""


def _with_viewer_limits(authz, sched, schedule_type: str, params: dict | None) -> dict:
    """Salesmen never get the invoiced Commissions tab, even on a scheduled send."""
    out = dict(params or {})
    if getattr(sched, "report_key", "") != "invoiced":
        return out
    owner_id = getattr(sched, "owner_user_id", None)
    if schedule_type == MASTER:
        owner_id = getattr(sched, "run_as_user_id", None)
    if not owner_id:
        return out
    principal = authz.principal_for_user_id(owner_id)
    if principal is not None and not authz.may_see_commissions(principal):
        out["_skip_commissions"] = True
    return out


def _report_params(params: dict | None) -> dict:
    return {k: v for k, v in (params or {}).items() if k not in _DELIVERY_PARAM_KEYS}


def _as_bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


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
