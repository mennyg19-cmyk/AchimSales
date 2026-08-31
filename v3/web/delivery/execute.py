"""Build first, then send each email/folder/notice as its own persisted leg."""

from __future__ import annotations

from web.data.repositories.delivery_legs import DeliveryLegRepository, attempt_key
from web.delivery.email import DeliveryResult
from web.delivery.graph_mail import GraphUnknownError
from web.delivery.service import DeliveryOutcome, DeliveryService, PreparedWorkbook
from web.delivery.states import SENT, UNKNOWN
from web.jobs.worker import JobCancelled


def deliver_with_legs(
    delivery: DeliveryService,
    legs: DeliveryLegRepository,
    *,
    slot_id: str,
    job_id: str,
    run_id: int | None,
    window: dict | None,
    salesman: str = "",
    cancel_check=None,
    **deliver_kwargs,
) -> DeliveryOutcome:
    recipients = str(deliver_kwargs.get("recipients") or "")
    path = str(deliver_kwargs.get("sharepoint_path") or "")
    onedrive_user = str(deliver_kwargs.get("onedrive_user") or "").strip()
    if not recipients.strip() and not path.strip():
        raise RuntimeError("No delivery targets.")
    built = delivery.prepare(
        report_key=deliver_kwargs["report_key"],
        identity=deliver_kwargs["identity"],
        visible_salesman_keys=deliver_kwargs.get("visible_salesman_keys"),
        builder_version=deliver_kwargs["builder_version"],
        params=deliver_kwargs.get("params") or {},
        layout=deliver_kwargs.get("layout") or {},
        report_name=deliver_kwargs.get("report_name") or deliver_kwargs["report_key"],
        sharepoint_path=path,
        filename_template=deliver_kwargs.get("filename_template") or "",
        schedule_name=deliver_kwargs.get("schedule_name") or "",
        email_on_empty=bool(deliver_kwargs.get("email_on_empty", True)),
        cancel_check=cancel_check,
    )
    if built.skipped_empty:
        return DeliveryOutcome(
            result=DeliveryResult(ok=True, error=built.skip_reason),
            row_count=0,
        )
    to = recipients
    cc = str(deliver_kwargs.get("cc_raw") or "")
    bcc = str(deliver_kwargs.get("bcc_raw") or "")
    override = deliver_kwargs.get("empty_recipients_override")
    if built.row_count == 0 and override:
        to = str(override)
        cc = ""
        bcc = ""
    folder_kind = "onedrive" if onedrive_user else "sharepoint"
    email_key = attempt_key(
        slot_id=slot_id, kind="email", target=to, salesman=salesman, window=window,
    )
    folder_key = attempt_key(
        slot_id=slot_id, kind=folder_kind, target=built.folder or path,
        salesman=salesman, window=window,
    )
    skip_email = bool(to.strip()) and legs.is_settled(email_key)
    skip_folder = bool((built.folder or path).strip()) and legs.is_settled(folder_key)
    if (not to.strip() or skip_email) and (not (built.folder or path).strip() or skip_folder):
        return _skipped_outcome(legs, email_key, folder_key, to, built.folder or path)
    if cancel_check and cancel_check():
        raise JobCancelled()

    folder_result = DeliveryResult(ok=True)
    if (built.folder or path).strip() and not skip_folder:
        folder_result = _send_folder_leg(
            delivery, legs, folder_key, built,
            onedrive_user=onedrive_user, run_id=run_id, slot_id=slot_id,
            job_id=job_id, salesman=salesman, cancel_check=cancel_check,
        )
    email_result = DeliveryResult(ok=True, recipients=[to] if to.strip() else [])
    if to.strip() and not skip_email:
        email_result = _send_email_leg(
            delivery, legs, email_key, built,
            subject=str(deliver_kwargs.get("subject") or ""),
            report_name=str(deliver_kwargs.get("report_name") or ""),
            body_text=str(deliver_kwargs.get("body_text") or ""),
            recipients=to, cc=cc, bcc=bcc,
            folder_url=folder_result.sharepoint_url or "",
            run_id=run_id, slot_id=slot_id, job_id=job_id, salesman=salesman,
            cancel_check=cancel_check,
        )
    return _combine_leg_results(built, email_result, folder_result, to, skip_email, skip_folder)


def send_notice_leg(
    delivery: DeliveryService,
    legs: DeliveryLegRepository,
    *,
    slot_id: str,
    job_id: str,
    run_id: int | None,
    window: dict | None,
    salesman: str,
    recipients: str,
    subject: str,
    body_text: str,
    report_name: str,
    cancel_check=None,
) -> DeliveryOutcome:
    key = attempt_key(
        slot_id=slot_id, kind="notice", target=recipients, salesman=salesman,
        window=window,
    )
    if legs.is_settled(key):
        leg = legs.get(key)
        ok = leg is not None and leg.status == SENT
        return DeliveryOutcome(
            result=DeliveryResult(
                ok=ok, send_channel="skipped", sent_via_smtp=ok,
                recipients=[recipients] if recipients.strip() else [],
                error="" if ok else (leg.error if leg else "notice not sent"),
                unknown=bool(leg and leg.status == UNKNOWN),
            ),
            row_count=0,
        )
    if cancel_check and cancel_check():
        raise JobCancelled()
    if legs.prepare(
        key, run_id=run_id, kind="notice", target=recipients,
        salesman_key=salesman, slot_id=slot_id, job_id=job_id,
    ) == "skip":
        return send_notice_leg(
            delivery, legs, slot_id=slot_id, job_id=job_id, run_id=run_id,
            window=window, salesman=salesman, recipients=recipients, subject=subject,
            body_text=body_text, report_name=report_name, cancel_check=cancel_check,
        )
    legs.mark_sending(key)
    try:
        if cancel_check and cancel_check():
            raise JobCancelled()
        outcome = delivery.send_no_data_notice(
            recipients=recipients, subject=subject, body_text=body_text,
            report_name=report_name, cancel_check=cancel_check,
        )
    except JobCancelled:
        legs.mark_failed(key, "cancelled")
        raise
    except GraphUnknownError as exc:
        legs.mark_unknown(key, str(exc))
        return DeliveryOutcome(
            result=DeliveryResult(ok=False, unknown=True, error=str(exc),
                                  recipients=[recipients]),
            row_count=0,
        )
    except Exception as exc:
        legs.mark_failed(key, str(exc))
        raise
    if outcome.result.unknown:
        legs.mark_unknown(key, outcome.result.error)
    elif outcome.result.ok:
        legs.mark_accepted(key)
        legs.mark_sent(key, row_count=0)
    else:
        legs.mark_failed(key, outcome.result.error or "notice failed")
    return outcome


def _send_folder_leg(delivery, legs, key, built: PreparedWorkbook, *,
                     onedrive_user: str, run_id, slot_id, job_id, salesman,
                     cancel_check) -> DeliveryResult:
    folder = built.folder
    filename = built.filename
    existing = legs.get(key)
    if existing and existing.status == SENT:
        return DeliveryResult(ok=True, sharepoint_saved=True,
                              sharepoint_url=existing.remote_id or None)
    if legs.prepare(
        key, run_id=run_id, kind="onedrive" if onedrive_user else "sharepoint",
        target=folder, salesman_key=salesman, slot_id=slot_id, job_id=job_id,
    ) == "skip":
        skip = legs.get(key)
        return DeliveryResult(
            ok=True, sharepoint_saved=True,
            sharepoint_url=(skip.remote_id if skip else None),
        )
    verified = _verify_folder(delivery, folder, filename, onedrive_user)
    if verified:
        legs.mark_sent(key, row_count=built.row_count, remote_id=verified.get("webUrl") or "")
        return DeliveryResult(ok=True, sharepoint_saved=True,
                              sharepoint_url=verified.get("webUrl"))
    if cancel_check and cancel_check():
        legs.mark_failed(key, "cancelled")
        raise JobCancelled()
    legs.mark_sending(key)
    resume = (legs.get(key).upload_session_url if legs.get(key) else "") or ""

    def _on_session(url: str) -> None:
        legs.set_upload_session(key, url)

    try:
        if onedrive_user:
            if delivery.email.onedrive is None:
                raise RuntimeError("OneDrive service is not configured")
            res = delivery.email.onedrive.upload_file(
                onedrive_user, folder, filename, built.xlsx or b"",
                resume_url=resume, on_session=_on_session,
            )
        else:
            res = delivery.email.sharepoint.upload_file(
                folder, filename, built.xlsx or b"",
                resume_url=resume, on_session=_on_session,
            )
    except JobCancelled:
        legs.mark_failed(key, "cancelled")
        raise
    except Exception as exc:  # noqa: BLE001
        verified = _verify_folder(delivery, folder, filename, onedrive_user)
        if verified:
            legs.mark_accepted(key, remote_id=verified.get("webUrl") or "")
            legs.mark_sent(key, row_count=built.row_count,
                           remote_id=verified.get("webUrl") or "")
            return DeliveryResult(ok=True, sharepoint_saved=True,
                                  sharepoint_url=verified.get("webUrl"))
        legs.mark_failed(key, str(exc))
        return DeliveryResult(ok=False, sharepoint_saved=False, sharepoint_error=str(exc),
                              error=str(exc))
    url = res.get("webUrl") or ""
    legs.mark_accepted(key, remote_id=url)
    legs.mark_sent(key, row_count=built.row_count, remote_id=url)
    legs.set_upload_session(key, "")
    return DeliveryResult(ok=True, sharepoint_saved=True, sharepoint_url=url or None)


def _send_email_leg(delivery, legs, key, built: PreparedWorkbook, *,
                    subject, report_name, body_text, recipients, cc, bcc,
                    folder_url, run_id, slot_id, job_id, salesman,
                    cancel_check) -> DeliveryResult:
    if legs.prepare(
        key, run_id=run_id, kind="email", target=recipients,
        salesman_key=salesman, slot_id=slot_id, job_id=job_id,
    ) == "skip":
        skip = legs.get(key)
        return DeliveryResult(
            ok=bool(skip and skip.status == SENT),
            unknown=bool(skip and skip.status == UNKNOWN),
            error=(skip.error if skip and skip.status != SENT else ""),
            recipients=[recipients],
            send_channel="skipped", sent_via_smtp=True,
        )
    if cancel_check and cancel_check():
        legs.mark_failed(key, "cancelled")
        raise JobCancelled()
    legs.mark_sending(key)
    try:
        result = delivery.email.deliver(
            subject=subject or report_name, recipients_raw=recipients,
            body_text=body_text, report_name=report_name,
            filename=built.filename, xlsx_bytes=built.xlsx,
            sharepoint_path=(built.folder or None) if folder_url else None,
            skip_folder=True,
            cc_raw=cc, bcc_raw=bcc, idempotency_key=key,
        )
        if folder_url and not result.sharepoint_url:
            result.sharepoint_url = folder_url
            result.sharepoint_saved = True
    except JobCancelled:
        legs.mark_failed(key, "cancelled")
        raise
    except GraphUnknownError as exc:
        legs.mark_unknown(key, str(exc))
        return DeliveryResult(ok=False, unknown=True, error=str(exc),
                              recipients=[recipients])
    except Exception as exc:
        legs.mark_failed(key, str(exc))
        raise
    if result.unknown:
        legs.mark_unknown(key, result.error)
        return result
    if result.ok:
        legs.mark_accepted(key)
        legs.mark_sent(key, row_count=built.row_count)
        return result
    legs.mark_failed(key, result.error or "email failed")
    return result


def _verify_folder(delivery, folder: str, filename: str, onedrive_user: str) -> dict | None:
    try:
        if onedrive_user:
            od = delivery.email.onedrive
            if od is None:
                return None
            return od.get_file(onedrive_user, folder, filename)
        return delivery.email.sharepoint.get_file(folder, filename)
    except Exception:  # noqa: BLE001
        return None


def _skipped_outcome(legs, email_key, folder_key, recipients, path) -> DeliveryOutcome:
    email_leg = legs.get(email_key) if recipients.strip() else None
    folder_leg = legs.get(folder_key) if path.strip() else None
    rows = max(
        email_leg.row_count if email_leg else 0,
        folder_leg.row_count if folder_leg else 0,
    )
    unknown = bool(
        (email_leg and email_leg.status == UNKNOWN)
        or (folder_leg and folder_leg.status == UNKNOWN)
    )
    email_failed = bool(email_leg and email_leg.status == FAILED)
    ok = not unknown and not email_failed
    return DeliveryOutcome(
        result=DeliveryResult(
            ok=ok, send_channel="skipped", sent_via_smtp=ok,
            recipients=[recipients] if recipients.strip() else [],
            sharepoint_saved=bool(path.strip()),
            unknown=unknown,
            error=(email_leg.error if email_leg and not ok else ""),
        ),
        row_count=rows,
    )


def _combine_leg_results(built, email_result, folder_result, recipients,
                         skip_email, skip_folder) -> DeliveryOutcome:
    unknown = bool(email_result.unknown)
    folder_needed = folder_result.sharepoint_error or (
        not skip_folder and not folder_result.sharepoint_saved and folder_result.error
    )
    error_bits = [x for x in (email_result.error, folder_result.error, folder_result.sharepoint_error) if x]
    ok = email_result.ok and folder_result.ok and not unknown and not folder_needed
    if skip_email and recipients.strip():
        pass
    return DeliveryOutcome(
        result=DeliveryResult(
            ok=ok,
            error="; ".join(error_bits),
            recipients=email_result.recipients or ([recipients] if recipients.strip() else []),
            eml_name=email_result.eml_name,
            sent_via_smtp=email_result.sent_via_smtp,
            send_channel=email_result.send_channel,
            sharepoint_saved=folder_result.sharepoint_saved or email_result.sharepoint_saved,
            sharepoint_url=folder_result.sharepoint_url or email_result.sharepoint_url,
            sharepoint_error=folder_result.sharepoint_error,
            outbox_id=email_result.outbox_id,
            unknown=unknown,
        ),
        row_count=built.row_count,
    )
