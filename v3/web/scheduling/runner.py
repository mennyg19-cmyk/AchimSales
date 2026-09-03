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
from datetime import date, datetime, timezone

from report_engine import registry
from web.auth.authorization import Authorization
from web.auth.principal import Principal
from web.data.repositories.app_settings import AppSettingsRepository
from web.data.repositories.company_views import CompanyViewRepository
from web.data.repositories.report_defaults import (
    DEFAULT_VIEW_NAME,
    ReportDefaultRepository,
    normalize_view_name,
    resolve_send_layout,
)
from web.data.repositories.saved_reports import SavedReportRepository
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import UserRepository
from web.delivery.email import DeliveryResult
from web.delivery.service import DeliveryOutcome, DeliveryService
from web.jobs.trace import JobCancelled, raise_if_cancelled, step as job_step
from web.delivery.sharepoint import TEST_SHAREPOINT_FOLDER
from web.scheduling import cadence as C
from web.scheduling.catchup import eastern_date_of, run_param_windows
from web.scheduling.sabbath import melacha_assur, skip_sabbath_enabled

log = logging.getLogger(__name__)

# One extra full run after a short wait so a dropped Graph call is not the
# last word. [FAIL] mail waits so a later retry/success can replace it.
# A retry that succeeds is one report email that names the failure, not
# [FAIL] plus a pass.
_TRANSIENT_ATTEMPTS = 2
_TRANSIENT_RETRY_WAIT_S = 30
_FAIL_NOTICE_WAIT_S = 15 * 60
_FAIL_NOTICE_PENDING = "pending"
_FAIL_NOTICE_SENT = "sent"
_FAIL_NOTICE_SUPERSEDED = "superseded"
_RETRY_SUBJECT_MARK = " — retried after a failure"
_RECOVERED_RETRY_REASON = "an earlier worker run failed or was interrupted"
_PRIOR_FAIL_REASON = "an earlier run of this schedule failed today"


def _inbox_already_got_mail(result: DeliveryResult) -> bool:
    return bool(result.sent_via_smtp or result.send_channel in ("graph", "smtp"))


def _retry_success_mail(subject: str, prior_errors: list[str]) -> tuple[str, str]:
    reasons = "; ".join(
        str(err).strip() for err in prior_errors if str(err).strip()
    ) or "unknown error"
    marked = subject if _RETRY_SUBJECT_MARK in subject else f"{subject}{_RETRY_SUBJECT_MARK}"
    body = (
        "This send failed once, then retried and succeeded.\n"
        f"First attempt: {reasons}\n\n"
        "There is no separate failure email for this run.\n"
    )
    return marked, body


def _sharepoint_for_test(test_to, live_path: str) -> str:
    """Test mode writes to Test, never to the live Daily/YTD folder."""
    if not test_to:
        return live_path or ""
    return TEST_SHAREPOINT_FOLDER if live_path else ""


class _NoSalesmen:
    def get_email(self, key: str) -> str:
        return ""

    def keys_with_email(self) -> list[str]:
        return []


class ScheduleRunner:
    def __init__(self, *, schedule_repo: ScheduleRepository,
                 master_repo: MasterScheduleRepository, run_repo: ScheduleRunRepository,
                 user_repo: UserRepository, authz: Authorization, delivery: DeliveryService,
                 settings: AppSettingsRepository | None = None, salesmen=None):
        self.schedule_repo = schedule_repo
        self.master_repo = master_repo
        self.run_repo = run_repo
        self.user_repo = user_repo
        self.authz = authz
        self.delivery = delivery
        self.settings = settings or AppSettingsRepository(user_repo.db)
        # Split-mail addresses come from the SalesmanDirectory (salesmen_master SP).
        # None (tests without one) means no salesman has an address.
        self.salesmen = salesmen or _NoSalesmen()
        self.defaults = ReportDefaultRepository(user_repo.db)
        self.company_views = CompanyViewRepository(user_repo.db)
        self.saved_reports = SavedReportRepository(user_repo.db)

    def _params_for(self, sched, schedule_type: str) -> dict:
        """Personal named views send the live saved view, not a stale snapshot.

        Delivery keys (cc, folder, no-data mail) stay on the schedule row.
        Company schedules keep their own period; company views do not store one.
        """
        stored = dict(sched.params or {})
        if schedule_type != PERSONAL:
            return stored
        name = getattr(sched, "view_name", None)
        if not name or normalize_view_name(name) == DEFAULT_VIEW_NAME:
            return stored
        view = self.saved_reports.get_by_name(
            sched.owner_user_id, sched.report_key, name)
        if view is None:
            return stored
        live = dict(view.params or {})
        for key in _DELIVERY_PARAM_KEYS:
            if key in stored:
                live[key] = stored[key]
        return live

    def _layout_for(self, sched) -> dict:
        name = getattr(sched, "view_name", None)
        named = {}
        if name and normalize_view_name(name) != DEFAULT_VIEW_NAME:
            named = self.company_views.get_layout(sched.report_key, name)
        return resolve_send_layout(
            name,
            sched.layout,
            self.defaults.get_layout(sched.report_key),
            named,
        )

    def run(self, schedule_id: int, schedule_type: str = PERSONAL,
            *, ignore_sabbath: bool = False, catch_up_for_date: str | None = None,
            include_regular: bool = True, recovered: bool = False,
            manual: bool = False, job_id: str | None = None) -> int:
        sched = self._load(schedule_id, schedule_type)
        if sched is None:
            raise RuntimeError(f"schedule {schedule_type}:{schedule_id} not found")

        extra = {"job_id": job_id} if job_id else None
        run_id = self.run_repo.start(
            schedule_id, schedule_type, manual=manual, extra_meta=extra,
        )
        try:
            raise_if_cancelled()
            if recovered and not manual and self._already_sent_today(schedule_id, schedule_type):
                self.run_repo.finish(
                    run_id, status="skipped",
                    debug_log="Already sent today; not sending again after a restart",
                )
                self._supersede_pending_fail_notices(schedule_id, schedule_type)
                return run_id
            if not ignore_sabbath and skip_sabbath_enabled(getattr(sched, "params", None)):
                assur, reason = melacha_assur()
                if assur:
                    self.run_repo.finish(
                        run_id, status="skipped",
                        debug_log=(
                            f"Skipped ({reason or 'Shabbos'}); "
                            "will run at the next scheduled time"
                        ),
                    )
                    self._set_catch_up(
                        schedule_id, schedule_type, True, for_date=C.eastern_date_iso(),
                    )
                    return run_id
            identity, scope = self._scope(sched, schedule_type)
            spec = registry.get(sched.report_key)
            base_params = _with_viewer_limits(
                self.authz, sched, schedule_type,
                self._params_for(sched, schedule_type),
            )
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
            subject = self._subject(sched, schedule_type, report_name, manual=manual)
            test_to = self._test_recipients()
            if test_to is not None:
                subject = f"[TEST] {subject}"
            od_user = "" if test_to else _onedrive_user(sched, schedule_type, identity)
            today = date.fromisoformat(C.eastern_date_iso())
            windows = run_param_windows(
                base_params, sched.report_key,
                skipped_iso=catch_up_for_date,
                today=today,
                last_success=eastern_date_of(
                    self.run_repo.last_success_at(schedule_id, schedule_type),
                ),
                include_regular=include_regular,
            )
            prior_errors: list[str] = []
            if recovered:
                prior_errors.append(_RECOVERED_RETRY_REASON)
            elif self._had_failure_today(schedule_id, schedule_type):
                prior_errors.append(_PRIOR_FAIL_REASON)
            outcomes: list[DeliveryOutcome] = []
            window_errors: list[str] = []
            for window in windows:
                raise_if_cancelled()
                window_subject, window_name = _window_labels(
                    subject, _schedule_label(sched, report_name), window,
                )
                try:
                    outcome = self._deliver_window(
                        sched=sched, schedule_type=schedule_type, schedule_id=schedule_id,
                        identity=identity, scope=scope, spec=spec, params=window,
                        subject=window_subject, report_name=report_name,
                        od_user=od_user, test_to=test_to, schedule_name=window_name,
                        prior_errors=prior_errors + window_errors,
                    )
                    outcomes.append(outcome)
                except JobCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - try remaining windows
                    log.warning(
                        "schedule %s:%s window failed; continuing",
                        schedule_type, schedule_id, exc_info=True,
                    )
                    window_errors.append(str(exc))
            if not outcomes:
                err = "; ".join(window_errors) or "delivery failed"
                self._hold_fail_notice(run_id, schedule_id, schedule_type, err)
                raise RuntimeError(err)
            combined = _combine_outcomes(outcomes)
            meta = _output_meta(combined, manual=manual)
            summary = _summary_message(combined, ok=True)
            if window_errors:
                summary = (
                    f"{summary}; a window failed, then a later window succeeded: "
                    f"{'; '.join(window_errors)}"
                )
            self.run_repo.finish(
                run_id, status="success",
                rows=combined.row_count, output_meta=meta, debug_log=summary,
            )
            self._supersede_pending_fail_notices(schedule_id, schedule_type)
            if catch_up_for_date:
                self._set_catch_up(schedule_id, schedule_type, False)
        except JobCancelled:
            existing = self.run_repo.get(run_id)
            if existing is None or existing.status == "running":
                self.run_repo.finish(
                    run_id, status="cancelled", debug_log="Cancelled",
                    output_meta=_log_meta(),
                )
            raise
        except Exception as exc:  # noqa: BLE001 - record then re-raise to fail the job
            log.exception("schedule run failed (%s:%s)", schedule_type, schedule_id)
            existing = self.run_repo.get(run_id)
            # Don't wipe a detailed finish() already written for a delivery failure.
            if existing is None or existing.status == "running":
                self._hold_fail_notice(run_id, schedule_id, schedule_type, str(exc))
            raise
        return run_id

    # -- internals ----------------------------------------------------------

    def _already_sent_today(self, schedule_id: int, schedule_type: str) -> bool:
        last = eastern_date_of(self.run_repo.last_success_at(schedule_id, schedule_type))
        return last is not None and last.isoformat() == C.eastern_date_iso()

    def _had_failure_today(self, schedule_id: int, schedule_type: str) -> bool:
        today = C.eastern_date_iso()
        for row in self.run_repo.list_for_schedule(schedule_id, schedule_type, limit=20):
            if row.status != "failure":
                continue
            day = eastern_date_of(row.started_at or row.finished_at)
            if day is not None and day.isoformat() == today:
                return True
        return False

    def _hold_fail_notice(self, run_id: int, schedule_id: int, schedule_type: str,
                          error: str) -> None:
        self._supersede_pending_fail_notices(schedule_id, schedule_type)
        self.run_repo.finish(
            run_id, status="failure", debug_log=error,
            output_meta=_log_meta({
                "fail_notice": _FAIL_NOTICE_PENDING,
                "fail_error": error,
            }),
        )

    def _supersede_pending_fail_notices(self, schedule_id: int, schedule_type: str) -> None:
        for row in self.run_repo.list_for_schedule(schedule_id, schedule_type, limit=20):
            meta = dict(row.output_meta or {})
            if row.status == "failure" and meta.get("fail_notice") == _FAIL_NOTICE_PENDING:
                meta["fail_notice"] = _FAIL_NOTICE_SUPERSEDED
                self.run_repo.patch_output_meta(row.id, meta)

    def flush_pending_fail_notices(self, now: datetime | None = None,
                                   wait_s: int | None = None) -> int:
        """Send held [FAIL] mail after the wait if no later success landed."""
        now = now or datetime.now(timezone.utc)
        wait_s = _FAIL_NOTICE_WAIT_S if wait_s is None else wait_s
        sent = 0
        for row in self.run_repo.list_recent_failures(limit=80):
            meta = dict(row.output_meta or {})
            if meta.get("fail_notice") != _FAIL_NOTICE_PENDING:
                continue
            if row.schedule_id is None:
                continue
            last_ok = self.run_repo.last_success_at(row.schedule_id, row.schedule_type)
            if last_ok and (not row.started_at or last_ok >= row.started_at):
                meta["fail_notice"] = _FAIL_NOTICE_SUPERSEDED
                self.run_repo.patch_output_meta(row.id, meta)
                continue
            age = _iso_age_s(row.finished_at or row.started_at, now)
            if age is None or age < wait_s:
                continue
            sched = self._load(row.schedule_id, row.schedule_type)
            if sched is not None:
                self._notify_failure(
                    sched, row.schedule_type, meta.get("fail_error") or row.debug_log,
                )
            meta["fail_notice"] = _FAIL_NOTICE_SENT
            self.run_repo.patch_output_meta(row.id, meta)
            sent += 1
        return sent

    def _load(self, schedule_id: int, schedule_type: str):
        if schedule_type == MASTER:
            return self.master_repo.get(schedule_id)
        return self.schedule_repo.get_any(schedule_id)

    def _set_catch_up(self, schedule_id: int, schedule_type: str, pending: bool,
                      for_date: str | None = None) -> None:
        if schedule_type == MASTER:
            self.master_repo.set_catch_up(schedule_id, pending, for_date)
        else:
            self.schedule_repo.set_catch_up(schedule_id, pending, for_date)

    def _deliver_window(self, *, sched, schedule_type: str, schedule_id: int,
                        identity: str, scope, spec, params: dict,
                        subject: str, report_name: str, od_user: str,
                        test_to: list[str] | None, schedule_name: str,
                        recovered: bool = False,
                        prior_errors: list[str] | None = None) -> DeliveryOutcome:
        builder_version = spec.builder_version if spec else 1
        last_error: Exception | None = None
        prior_errors = list(prior_errors or [])
        job_step(
            "schedule",
            f"{schedule_type} #{schedule_id} {report_name} "
            f"{_compact_params(params)}",
        )
        if recovered and _RECOVERED_RETRY_REASON not in prior_errors:
            prior_errors.append(_RECOVERED_RETRY_REASON)
        for attempt in range(1, _TRANSIENT_ATTEMPTS + 1):
            send_subject, send_body = subject, ""
            if prior_errors:
                send_subject, send_body = _retry_success_mail(subject, prior_errors)
            try:
                if schedule_type == MASTER and self._salesman_targets(params):
                    outcome = self._run_master_fanout(
                        sched=sched, identity=identity, scope=scope,
                        builder_version=builder_version,
                        subject=send_subject, report_name=report_name,
                        onedrive_user=od_user, test_to=test_to,
                        params=params, schedule_name=schedule_name,
                        body_text=send_body,
                    )
                else:
                    no_data_all = bool(params.get("email_on_no_data"))
                    no_data_me = bool(params.get("email_on_no_data_me_only"))
                    test_empty = self.settings.test_emails()
                    empty_to_test = no_data_me and not no_data_all and bool(test_empty)
                    outcome = self.delivery.run_and_deliver(
                        report_key=sched.report_key, identity=identity,
                        visible_salesman_keys=scope,
                        builder_version=builder_version,
                        params=_report_params(params), layout=self._layout_for(sched),
                        recipients="; ".join(test_to) if test_to else sched.recipients,
                        subject=send_subject, report_name=report_name,
                        sharepoint_path=_sharepoint_for_test(test_to, sched.sharepoint_path),
                        filename_template=getattr(sched, "filename_template", "") or "",
                        onedrive_user=od_user,
                        cc_raw="" if test_to else str(params.get("email_cc") or ""),
                        bcc_raw="" if test_to else str(params.get("email_bcc") or ""),
                        email_on_empty=no_data_all or empty_to_test,
                        empty_recipients_override=(
                            None if test_to
                            else ("; ".join(test_empty) if empty_to_test else None)
                        ),
                        schedule_name=schedule_name,
                        body_text=send_body,
                    )
                if not outcome.result.ok:
                    if _inbox_already_got_mail(outcome.result):
                        return outcome
                    raise RuntimeError(outcome.result.error or "delivery failed")
                return outcome
            except Exception as exc:
                last_error = exc
                prior_errors.append(str(exc))
                if attempt >= _TRANSIENT_ATTEMPTS:
                    raise
                log.warning(
                    "schedule %s:%s attempt %d/%d failed; retrying in %ss",
                    schedule_type, schedule_id, attempt, _TRANSIENT_ATTEMPTS,
                    _TRANSIENT_RETRY_WAIT_S, exc_info=True,
                )
                time.sleep(_TRANSIENT_RETRY_WAIT_S)
        raise last_error or RuntimeError("delivery failed")

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

    def _test_recipients(self) -> list[str] | None:
        """Test-mode address list for any schedule, or None to send as stored."""
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

    def _subject(self, sched, schedule_type: str, report_name: str,
                 *, manual: bool = False) -> str:
        now = datetime.now(timezone.utc).astimezone(C.EASTERN)
        stamp = now.strftime("%Y-%m-%d %H:%M") if manual else now.strftime("%Y-%m-%d")
        label = "Master" if schedule_type == MASTER else "Scheduled"
        name = getattr(sched, "name", "") or report_name
        return f"{label}: {name} ({stamp})"

    def _run_master_fanout(self, *, sched, identity: str,
                           scope: set[str] | None, builder_version: int,
                           subject: str, report_name: str,
                           onedrive_user: str = "",
                           test_to: list[str] | None = None,
                           params: dict | None = None,
                           schedule_name: str = "",
                           body_text: str = "") -> DeliveryOutcome:
        outcomes: list[DeliveryOutcome] = []
        deliveries: list[dict] = []
        skip_notes: list[str] = []
        params = params if params is not None else (sched.params or {})
        test_recips = "; ".join(test_to) if test_to else ""
        sched_name = schedule_name or getattr(sched, "name", "") or report_name

        if sched.recipients or sched.sharepoint_path:
            no_data_all = bool(params.get("email_on_no_data"))
            no_data_me = bool(params.get("email_on_no_data_me_only"))
            test_empty = self.settings.test_emails()
            empty_to_test = no_data_me and not no_data_all and bool(test_empty)
            full = self.delivery.run_and_deliver(
                report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                builder_version=builder_version, params=_report_params(params),
                layout=self._layout_for(sched),
                recipients=test_recips if test_to else sched.recipients,
                subject=subject,
                report_name=report_name,
                sharepoint_path=_sharepoint_for_test(test_to, sched.sharepoint_path),
                filename_template=getattr(sched, "filename_template", "") or "",
                onedrive_user="" if test_to else onedrive_user,
                schedule_name=sched_name,
                body_text=body_text,
                email_on_empty=no_data_all or empty_to_test,
                empty_recipients_override=(
                    None if test_to
                    else ("; ".join(test_empty) if empty_to_test else None)
                ),
            )
            outcomes.append(full)
            deliveries.append(_delivery_leg(full, kind="full"))

        for key in self._salesman_targets(params):
            email = self.salesmen.get_email(key)
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
                builder_version=builder_version, params=split_params, layout=self._layout_for(sched),
                recipients=test_recips if test_to else email,
                subject=f"{subject} - {key}",
                report_name=f"{report_name} - {key}", sharepoint_path="",
                filename_template=getattr(sched, "filename_template", "") or "",
                schedule_name=f"{sched_name} - {key}",
                body_text=body_text,
                email_on_empty=False,
            )
            if outcome.row_count == 0:
                notice_fn = getattr(self.delivery, "send_no_data_notice", None)
                if callable(notice_fn):
                    period_label = str(split_params.get("period") or "this run")
                    nsubj, nbody = _no_data_email(
                        report_name, period_label, key,
                        customers=_as_str_list(split_params.get("customers")),
                    )
                    outcome = notice_fn(
                        recipients=test_recips if test_to else email,
                        subject=nsubj, body_text=nbody, report_name=report_name,
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
            return self.salesmen.keys_with_email()
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
        kind = str((getattr(sched, "params", None) or {}).get("folder_kind") or "")
        if kind == "sharepoint":
            return ""
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


def _no_data_email(report_name: str, period_label: str, salesman: str,
                   customers: list[str] | None = None) -> tuple[str, str]:
    """Subject + body matching the old Ordered runbook no-data mail."""
    filter_parts = [f"Salesman: {salesman}"]
    if customers:
        filter_parts.append("Customer(s): " + ", ".join(customers))
    subject = f"{report_name} - No Data Found ({period_label})"
    body = (
        f"Your requested {report_name} for period '{period_label}' returned no results.\n\n"
        f"Filters applied: {', '.join(filter_parts)}\n\n"
        "Reason: No data for this salesman in the selected period.\n\n"
        "Please verify the customer account and salesman combination and try again."
    )
    return subject, body


def _report_params(params: dict | None) -> dict:
    return {k: v for k, v in (params or {}).items() if k not in _DELIVERY_PARAM_KEYS}


def _compact_params(params: dict | None) -> str:
    bits: list[str] = []
    for key in ("period", "start_date", "end_date", "year", "salesman", "customers"):
        value = (params or {}).get(key)
        if value not in (None, "", [], {}):
            bits.append(f"{key}={value}")
    return " ".join(bits) or "default filters"


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


def _log_meta(extra: dict | None = None) -> dict:
    from web.jobs.trace import snapshot
    meta = dict(extra or {})
    meta["job_log"] = snapshot()
    return meta


def _output_meta(outcome: DeliveryOutcome, *, manual: bool = False) -> dict:
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
    meta.update(_log_meta())
    if outcome.deliveries:
        meta["deliveries"] = outcome.deliveries
    if manual:
        meta["manual"] = True
    return meta


def _schedule_label(sched, report_name: str) -> str:
    """Name used in {Schedule} on the workbook. Master has a name; personal uses the view."""
    named = str(getattr(sched, "name", "") or "").strip()
    if named:
        return named
    view = str(getattr(sched, "view_name", "") or "").strip()
    if view and normalize_view_name(view) != DEFAULT_VIEW_NAME:
        return view
    return report_name


def _window_labels(subject: str, schedule_name: str, window: dict) -> tuple[str, str]:
    """Keep two catch-up workbooks from sharing one filename/subject."""
    end = str(window.get("end_date") or "").strip()
    if str(window.get("period") or "") != "custom" or not end:
        return subject, schedule_name
    return f"{subject} through {end}", f"{schedule_name} {end}"


def _combine_outcomes(outcomes: list[DeliveryOutcome]) -> DeliveryOutcome:
    if len(outcomes) == 1:
        return outcomes[0]
    deliveries: list[dict] = []
    for outcome in outcomes:
        if outcome.deliveries:
            deliveries.extend(outcome.deliveries)
        else:
            deliveries.append(_delivery_leg(outcome, kind="full"))
    ok = all(o.result.ok for o in outcomes)
    notes = [o.result.error for o in outcomes if o.result.error]
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
        result=result,
        row_count=sum(o.row_count for o in outcomes),
        deliveries=deliveries,
    )


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


def _iso_age_s(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds()
