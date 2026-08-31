"""Run one stored schedule: build, deliver, record history."""

from __future__ import annotations

import logging
import time
import uuid
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
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.delivery_legs import (
    DeliveryLegRepository, attempt_key, window_key_parts,
)
from web.jobs.worker import JobCancelled
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.users import UserRepository
from web.delivery.email import DeliveryResult
from web.delivery.service import DeliveryOutcome, DeliveryService
from web.scheduling import cadence as C
from web.scheduling.catchup import eastern_date_of, run_param_windows
from web.scheduling.sabbath import melacha_assur, skip_sabbath_enabled
from web.scheduling.runner_support import (
    _as_str_list, _combine_outcomes, _delivery_leg, _no_data_email, _onedrive_user,
    _output_meta, _report_params,
    _salesman_targets, _sharepoint_for_test, _summary_message, _window_labels,
    _with_viewer_limits,
)

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
        self.defaults = ReportDefaultRepository(user_repo.db)
        self.company_views = CompanyViewRepository(user_repo.db)

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
            include_regular: bool = True, trigger: str = "scheduled",
            cancel_check=None, slot_id: str = "", slot_day: str = "",
            job_id: str = "", slot_when: str = "",
            retry_attempt_key: str = "") -> int:
        sched = self._load(schedule_id, schedule_type)
        if sched is None:
            raise RuntimeError(f"schedule {schedule_type}:{schedule_id} not found")

        run_id = self.run_repo.start(schedule_id, schedule_type, trigger=trigger)
        slot_day = slot_day or C.eastern_date_iso()
        slot_id = slot_id or f"adhoc:{schedule_type}:{schedule_id}:{uuid.uuid4().hex}"
        from web.delivery.filename_template import parse_frozen_when
        when = parse_frozen_when(slot_when, slot_day)
        try:
            if cancel_check and cancel_check():
                raise JobCancelled()
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
            base_params = _with_viewer_limits(self.authz, sched, schedule_type, sched.params)
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
            today = date.fromisoformat(slot_day)
            windows = run_param_windows(
                base_params, sched.report_key,
                skipped_iso=catch_up_for_date,
                today=today,
                last_success=eastern_date_of(
                    self.run_repo.last_success_at(schedule_id, schedule_type),
                ),
                include_regular=include_regular,
            )
            outcomes: list[DeliveryOutcome] = []
            for window in windows:
                if cancel_check and cancel_check():
                    raise JobCancelled()
                window_subject, window_name = _window_labels(
                    subject, getattr(sched, "name", "") or report_name, window,
                )
                outcome = self._deliver_window(
                    sched=sched, schedule_type=schedule_type, schedule_id=schedule_id,
                    identity=identity, scope=scope, spec=spec, params=window,
                    subject=window_subject, report_name=report_name,
                    od_user=od_user, test_to=test_to, schedule_name=window_name,
                    cancel_check=cancel_check, run_id=run_id, trigger=trigger,
                    slot_id=slot_id, job_id=job_id,
                    when=when, retry_attempt_key=retry_attempt_key,
                )
                outcomes.append(outcome)
            combined = _combine_outcomes(outcomes)
            meta = _output_meta(combined)
            summary = _summary_message(combined, ok=combined.result.ok)
            if combined.result.unknown:
                self.run_repo.finish(
                    run_id, status="unknown",
                    rows=combined.row_count, output_meta=meta, debug_log=summary,
                )
                self._notify_unknown(
                    sched, schedule_type, summary, run_id=run_id,
                    attempt_key=combined.unknown_attempt_key,
                )
            elif not combined.result.ok:
                raise RuntimeError(combined.result.error or "delivery failed")
            else:
                self.run_repo.finish(
                    run_id, status="success",
                    rows=combined.row_count, output_meta=meta, debug_log=summary,
                )
                if catch_up_for_date:
                    self._set_catch_up(schedule_id, schedule_type, False)
        except JobCancelled:
            existing = self.run_repo.get(run_id)
            if existing is None or existing.status == "running":
                self.run_repo.finish(run_id, status="cancelled", debug_log="cancelled")
            raise
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
                        cancel_check=None, run_id: int | None = None,
                        trigger: str = "scheduled", slot_id: str = "",
                        job_id: str = "", when=None,
                        retry_attempt_key: str = "") -> DeliveryOutcome:
        builder_version = spec.builder_version if spec else 1
        last_error: Exception | None = None
        for attempt in range(1, _TRANSIENT_ATTEMPTS + 1):
            try:
                if cancel_check and cancel_check():
                    raise JobCancelled()
                if schedule_type == MASTER and _salesman_targets(self.user_repo.db, params):
                    outcome = self._run_master_fanout(
                        sched=sched, identity=identity, scope=scope,
                        builder_version=builder_version,
                        subject=subject, report_name=report_name,
                        onedrive_user=od_user, test_to=test_to,
                        params=params, schedule_name=schedule_name,
                        cancel_check=cancel_check,
                        run_id=run_id, trigger=trigger,
                        schedule_type=schedule_type, schedule_id=schedule_id,
                        slot_id=slot_id, job_id=job_id,
                        when=when, retry_attempt_key=retry_attempt_key,
                    )
                else:
                    no_data_all = bool(params.get("email_on_no_data"))
                    no_data_me = bool(params.get("email_on_no_data_me_only"))
                    test_empty = self.settings.test_emails()
                    empty_to_test = no_data_me and not no_data_all and bool(test_empty)
                    outcome = self._deliver_email_and_folder(
                        run_id=run_id, trigger=trigger,
                        schedule_type=schedule_type, schedule_id=schedule_id,
                        window=params,
                        report_key=sched.report_key, identity=identity,
                        visible_salesman_keys=scope,
                        builder_version=builder_version,
                        params=_report_params(params), layout=self._layout_for(sched),
                        recipients="; ".join(test_to) if test_to else sched.recipients,
                        subject=subject, report_name=report_name,
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
                        cancel_check=cancel_check,
                        slot_id=slot_id, job_id=job_id,
                        when=when, retry_attempt_key=retry_attempt_key,
                    )
                if not outcome.result.ok and not outcome.result.unknown:
                    raise RuntimeError(outcome.result.error or "delivery failed")
                return outcome
            except Exception as exc:
                if isinstance(exc, JobCancelled):
                    raise
                last_error = exc
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

    def _notify_unknown(self, sched, schedule_type: str, summary: str,
                        run_id: int | None = None, attempt_key: str = "") -> None:
        from web.delivery.reconcile import alert_unknown_delivery
        name = getattr(sched, "name", None) or getattr(sched, "report_key", "schedule")
        alert_unknown_delivery(
            self.user_repo.db, self.settings,
            delivery=self.delivery,
            subject=f"[UNKNOWN] {name}",
            body=(
                f"A scheduled send may already be in a mailbox. Do not assume it failed.\n\n"
                f"Schedule: {name}\n"
                f"Kind: {'Company' if schedule_type == MASTER else 'Personal'}\n"
                f"{summary}\n\n"
                "Open History: mark 'I received it' if the mail arrived, or "
                "'Send again' only if it is missing."
            ),
            attempt_key=attempt_key,
            run_id=run_id,
        )

    def _subject(self, sched, schedule_type: str, report_name: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        label = "Master" if schedule_type == MASTER else "Scheduled"
        name = getattr(sched, "name", "") or report_name
        return f"{label}: {name} ({stamp})"

    def _deliver_email_and_folder(self, *, run_id: int | None, trigger: str,
                                  schedule_type: str, schedule_id: int,
                                  window: dict, salesman: str = "",
                                  slot_id: str = "", job_id: str = "",
                                  when=None, retry_attempt_key: str = "",
                                  **deliver_kwargs) -> DeliveryOutcome:
        """Build first, then send each email/folder leg. Fake deliveries skip legs."""
        recipients = str(deliver_kwargs.get("recipients") or "")
        path = str(deliver_kwargs.get("sharepoint_path") or "")
        if not recipients.strip() and not path.strip():
            raise RuntimeError("No delivery targets.")
        if hasattr(self.delivery, "prepare"):
            from web.delivery.execute import deliver_with_legs
            return deliver_with_legs(
                self.delivery,
                DeliveryLegRepository(self.user_repo.db),
                slot_id=slot_id or f"{schedule_type}:{schedule_id}:{trigger}",
                job_id=job_id,
                run_id=run_id,
                window=window,
                salesman=salesman,
                when=when,
                retry_attempt_key=retry_attempt_key,
                **deliver_kwargs,
            )
        # Test doubles with only run_and_deliver still need skip-on-retry.
        legs = DeliveryLegRepository(self.user_repo.db)
        frozen_when = when.isoformat() if hasattr(when, "isoformat") else (when or "")
        wf, wt = window_key_parts(window)
        email_key = attempt_key(
            slot_id=slot_id or f"{schedule_type}:{schedule_id}:{trigger}",
            kind="email", target=recipients, salesman=salesman, window=window,
        )
        folder_key = attempt_key(
            slot_id=slot_id or f"{schedule_type}:{schedule_id}:{trigger}",
            kind="sharepoint", target=path, salesman=salesman, window=window,
        )
        skip_email = bool(recipients.strip()) and legs.is_settled(email_key)
        skip_folder = bool(path.strip()) and legs.is_settled(folder_key)
        if (not recipients.strip() or skip_email) and (not path.strip() or skip_folder):
            email_leg = legs.get(email_key) if recipients.strip() else None
            folder_leg = legs.get(folder_key) if path.strip() else None
            rows = max(
                email_leg.row_count if email_leg else 0,
                folder_leg.row_count if folder_leg else 0,
            )
            return DeliveryOutcome(
                result=DeliveryResult(
                    ok=True, send_channel="skipped", sent_via_smtp=True,
                    recipients=[recipients] if recipients.strip() else [],
                    sharepoint_saved=bool(path.strip()),
                ),
                row_count=rows,
            )
        if recipients.strip() and not skip_email:
            legs.prepare(email_key, run_id=run_id, kind="email", target=recipients,
                         salesman_key=salesman, slot_id=slot_id, job_id=job_id,
                         slot_when=frozen_when, window_from=wf, window_to=wt)
        if path.strip() and not skip_folder:
            legs.prepare(folder_key, run_id=run_id, kind="sharepoint", target=path,
                         salesman_key=salesman, slot_id=slot_id, job_id=job_id,
                         slot_when=frozen_when, window_from=wf, window_to=wt)
        try:
            outcome = self.delivery.run_and_deliver(
                skip_email=skip_email, skip_folder=skip_folder,
                idempotency_key=email_key,
                **deliver_kwargs,
            )
        except Exception as exc:
            if recipients.strip() and not skip_email:
                legs.mark_failed(email_key, "cancelled" if isinstance(exc, JobCancelled) else str(exc))
            if path.strip() and not skip_folder:
                legs.mark_failed(folder_key, "cancelled" if isinstance(exc, JobCancelled) else str(exc))
            raise
        from web.scheduling.runner_support import _commit_email_folder_legs
        _commit_email_folder_legs(
            legs, email_key, folder_key, recipients, path, skip_email, skip_folder, outcome,
        )
        return outcome

    def _run_master_fanout(self, *, sched, identity: str,
                           scope: set[str] | None, builder_version: int,
                           subject: str, report_name: str,
                           onedrive_user: str = "",
                           test_to: list[str] | None = None,
                           params: dict | None = None,
                           schedule_name: str = "",
                           cancel_check=None, run_id: int | None = None,
                           trigger: str = "scheduled",
                           schedule_type: str = MASTER, schedule_id: int = 0,
                           slot_id: str = "", job_id: str = "",
                           when=None, retry_attempt_key: str = "",
                           ) -> DeliveryOutcome:
        outcomes: list[DeliveryOutcome] = []
        deliveries: list[dict] = []
        params = params if params is not None else (sched.params or {})
        test_recips = "; ".join(test_to) if test_to else ""
        sched_name = schedule_name or getattr(sched, "name", "") or report_name

        retry_leg = (
            DeliveryLegRepository(self.user_repo.db).get(retry_attempt_key)
            if retry_attempt_key else None
        )
        if sched.recipients or sched.sharepoint_path:
            no_data_all = bool(params.get("email_on_no_data"))
            no_data_me = bool(params.get("email_on_no_data_me_only"))
            test_empty = self.settings.test_emails()
            empty_to_test = no_data_me and not no_data_all and bool(test_empty)
            if retry_leg is None or not retry_leg.salesman_key:
                full = self._deliver_email_and_folder(
                    run_id=run_id, trigger=trigger,
                    schedule_type=schedule_type, schedule_id=schedule_id,
                    window=params,
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
                    email_on_empty=no_data_all or empty_to_test,
                    empty_recipients_override=(
                        None if test_to
                        else ("; ".join(test_empty) if empty_to_test else None)
                    ),
                    cancel_check=cancel_check,
                    slot_id=slot_id, job_id=job_id,
                    when=when, retry_attempt_key=retry_attempt_key,
                )
                outcomes.append(full)
                deliveries.append(_delivery_leg(full, kind="full"))

        salesmen = SalesmanRepository(self.user_repo.db)
        split_keys = _salesman_targets(self.user_repo.db, params)
        if retry_leg is not None and retry_leg.salesman_key:
            split_keys = [retry_leg.salesman_key]
        for key in split_keys:
            if (
                retry_leg is not None
                and retry_leg.salesman_key == key
                and (retry_leg.target or "").strip()
            ):
                email = retry_leg.target
            else:
                email = salesmen.get_email(key)
            if not email:
                raise RuntimeError(
                    f"Salesman {key} has no email; the schedule cannot send."
                )
            if cancel_check and cancel_check():
                raise JobCancelled()
            split_params = _report_params(params)
            split_params["salesman"] = [key]
            try:
                if retry_leg is not None and retry_leg.kind == "notice":
                    if retry_leg.salesman_key != key:
                        continue
                    from web.delivery.execute import send_notice_leg
                    period_label = str(split_params.get("period") or "this run")
                    nsubj, nbody = _no_data_email(
                        report_name, period_label, key,
                        customers=_as_str_list(split_params.get("customers")),
                    )
                    outcome = send_notice_leg(
                        self.delivery, DeliveryLegRepository(self.user_repo.db),
                        slot_id=slot_id, job_id=job_id, run_id=run_id,
                        window=params, salesman=key,
                        recipients=retry_leg.target,
                        subject=nsubj, body_text=nbody, report_name=report_name,
                        cancel_check=cancel_check,
                        retry_attempt_key=retry_attempt_key,
                        when=when,
                    )
                    outcomes.append(outcome)
                    deliveries.append(_delivery_leg(outcome, kind="split", salesman=key))
                    continue
                if retry_leg is not None and retry_leg.salesman_key != key:
                    continue
                outcome = self._deliver_email_and_folder(
                    run_id=run_id, trigger=trigger,
                    schedule_type=schedule_type, schedule_id=schedule_id,
                    window=params, salesman=key,
                    report_key=sched.report_key, identity=identity, visible_salesman_keys=scope,
                    builder_version=builder_version, params=split_params, layout=self._layout_for(sched),
                    recipients=test_recips if test_to else email,
                    subject=f"{subject} - {key}",
                    report_name=f"{report_name} - {key}", sharepoint_path="",
                    filename_template=getattr(sched, "filename_template", "") or "",
                    schedule_name=f"{sched_name} - {key}",
                    email_on_empty=False,
                    cancel_check=cancel_check,
                    slot_id=slot_id, job_id=job_id,
                    when=when, retry_attempt_key=retry_attempt_key,
                )
                if retry_leg is None and (
                    outcome.row_count == 0 and outcome.result.send_channel != "skipped"
                ):
                    if cancel_check and cancel_check():
                        raise JobCancelled()
                    period_label = str(split_params.get("period") or "this run")
                    nsubj, nbody = _no_data_email(
                        report_name, period_label, key,
                        customers=_as_str_list(split_params.get("customers")),
                    )
                    notice_to = test_recips if test_to else email
                    if hasattr(self.delivery, "prepare"):
                        from web.delivery.execute import send_notice_leg
                        outcome = send_notice_leg(
                            self.delivery, DeliveryLegRepository(self.user_repo.db),
                            slot_id=slot_id, job_id=job_id, run_id=run_id,
                            window=params, salesman=key, recipients=notice_to,
                            subject=nsubj, body_text=nbody, report_name=report_name,
                            cancel_check=cancel_check,
                            when=when,
                        )
                    else:
                        notice_fn = getattr(self.delivery, "send_no_data_notice", None)
                        if callable(notice_fn):
                            outcome = notice_fn(
                                recipients=notice_to,
                                subject=nsubj, body_text=nbody, report_name=report_name,
                                cancel_check=cancel_check,
                            )
            except JobCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - keep other salesmen going
                log.exception("split delivery failed for salesman %s", key)
                outcome = DeliveryOutcome(
                    result=DeliveryResult(
                        ok=False, error=str(exc),
                        recipients=[test_recips if test_to else email],
                    ),
                    row_count=0,
                )
            outcomes.append(outcome)
            deliveries.append(_delivery_leg(outcome, kind="split", salesman=key))

        if not outcomes:
            return DeliveryOutcome(
                result=DeliveryResult(ok=False, error="No delivery targets."),
                row_count=0,
                deliveries=deliveries,
            )
        combined = _combine_outcomes(outcomes)
        return DeliveryOutcome(
            result=combined.result,
            row_count=combined.row_count,
            deliveries=deliveries or combined.deliveries,
        )

