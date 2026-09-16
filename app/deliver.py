"""Build a workbook and send it (Graph when secrets exist, else sqlite outbox)."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

import cadence
import catalog
import catchup
import chips
import config
import drive
import store
from doorway import DoorwayError
from export_xlsx import workbook_bytes
from layout import apply_layout
from mail import GraphMailError, mailer, split_recipients
from reports import build_payload

log = logging.getLogger(__name__)


def _filename(
    template: str,
    view_name: str,
    *,
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
) -> str:
    return chips.expand_filename(
        template,
        schedule_name=view_name,
        report_name=report_name,
        params=params,
        when=when,
    )


def _folder(
    template: str,
    view_name: str,
    *,
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
) -> str:
    return chips.expand_folder(
        template,
        schedule_name=view_name,
        report_name=report_name,
        params=params,
        when=when,
    )


def _extras(schedule: dict) -> str:
    extra = []
    if schedule.get("cc"):
        extra.append(f"CC {schedule['cc']}")
    if schedule.get("bcc"):
        extra.append(f"BCC {schedule['bcc']}")
    if schedule.get("filename"):
        extra.append(f"file {schedule['filename']}")
    if schedule.get("sharepoint_folder"):
        extra.append(f"SharePoint {schedule['sharepoint_folder']}")
    if schedule.get("onedrive_folder"):
        extra.append(f"OneDrive {schedule['onedrive_folder']}")
    return "; ".join(extra)


def send_or_outbox(
    *,
    recipients: str,
    subject: str,
    body: str,
    filename: str = "",
    xlsx_bytes: bytes | None = None,
    cc: str = "",
    bcc: str = "",
    body_html: str = "",
) -> str:
    """Return 'graph' or 'outbox'. Graph failure is raised after the outbox row is written."""
    store.add_outbox(recipients, subject, body)
    if not config.graph_mail_configured():
        return "outbox"
    to_list = split_recipients(recipients)
    try:
        mailer().send(
            sender=config.email_from(),
            to=to_list,
            subject=subject,
            body_text=body,
            filename=filename,
            xlsx_bytes=xlsx_bytes,
            cc=split_recipients(cc) or None,
            bcc=split_recipients(bcc) or None,
            body_html=body_html or None,
        )
    except GraphMailError:
        log.warning("Graph send failed; outbox row already written", exc_info=True)
        raise
    return "graph"


def _run_params(schedule: dict, at: datetime | None) -> dict:
    params = dict(schedule.get("params") or {})
    # Live clock read window_* from report_schedules, not the shared view.
    if schedule.get("window_period"):
        params["period"] = schedule["window_period"]
    if schedule.get("window_start"):
        params["from_date"] = schedule["window_start"]
    if schedule.get("window_end"):
        params["to_date"] = schedule["window_end"]
    skipped = catchup.as_date(schedule.get("catch_up_for_date"))
    if skipped is None:
        return params
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = now.astimezone(cadence.EASTERN).date()
    return catchup.overlay_params(
        params, schedule["report_key"], skipped=skipped, today=today
    )


def _upload_folders(
    schedule: dict,
    filename: str,
    content: bytes,
    owner: dict,
    *,
    report_name: str,
    params: dict,
    when: datetime | None,
) -> str:
    url = ""
    view_name = schedule.get("view_name") or ""
    sp_folder = _folder(
        schedule.get("sharepoint_folder") or "",
        view_name,
        report_name=report_name,
        params=params,
        when=when,
    )
    od_folder = _folder(
        schedule.get("onedrive_folder") or "",
        view_name,
        report_name=report_name,
        params=params,
        when=when,
    )
    if sp_folder:
        uploaded = drive.upload_sharepoint(sp_folder, filename, content)
        url = str(uploaded.get("webUrl") or "")
    if od_folder:
        uploaded = drive.upload_onedrive(owner.get("email") or "", od_folder, filename, content)
        url = url or str(uploaded.get("webUrl") or "")
    return url


def deliver_schedule(schedule: dict, user: dict, at: datetime | None = None) -> str:
    spec = catalog.spec(schedule["report_key"])
    if spec is None:
        store.mark_schedule_run(schedule["id"], "failure", "Unknown report on the saved view.", at=at)
        return "failure"
    params = _run_params(schedule, at)
    try:
        payload = build_payload(schedule["report_key"], user, params)
    except DoorwayError as err:
        store.mark_schedule_run(schedule["id"], "failure", str(err), at=at)
        return "failure"
    payload = apply_layout(payload, schedule.get("layout"))
    store.save_job(schedule["report_key"], schedule["view_name"], payload, owner_email=user["email"])
    recipients = store.mail_recipients(schedule["recipients"])
    cc, bcc = store.mail_copy_lists(schedule.get("cc") or "", schedule.get("bcc") or "")
    source = (payload.get("data") or {}).get("source") or "mock"
    live = source == "reporting_api"
    extra = _extras({**schedule, "cc": cc, "bcc": bcc})
    if config.graph_mail_configured():
        detail = (
            "Scheduled workbook from the office Reporting API."
            if live
            else "Scheduled dummy workbook."
        )
    else:
        detail = (
            "Scheduled workbook from the office Reporting API. Graph secrets are not set; queued to the outbox."
            if live
            else "Scheduled dummy workbook. Graph secrets are not set; queued to the outbox."
        )
    if extra:
        detail += " " + extra
    period = chips.period_label(params)
    report_title = spec.get("title") or schedule["report_key"]
    xlsx = workbook_bytes(payload)
    name = _filename(
        schedule.get("filename") or "",
        schedule["view_name"],
        report_name=report_title,
        params=params,
        when=at,
    )
    try:
        file_url = _upload_folders(
            schedule,
            name,
            xlsx,
            user,
            report_name=report_title,
            params=params,
            when=at,
        )
    except drive.DriveError as err:
        store.mark_schedule_run(schedule["id"], "failure", str(err), at=at)
        return "failure"
    subject_raw = schedule.get("subject") or (
        schedule["view_name"] if live else f"[MOCK] {schedule['view_name']}"
    )
    subject = chips.expand(
        subject_raw,
        schedule_name=schedule["view_name"],
        period=period,
        sharepoint_url=file_url,
        download_url=file_url,
        html_button=False,
        report_name=report_title,
        params=params,
        when=at,
        filename=name,
    )
    body_text = chips.expand(
        detail,
        schedule_name=schedule["view_name"],
        period=period,
        sharepoint_url=file_url,
        download_url=file_url,
        report_name=report_title,
        params=params,
        when=at,
        filename=name,
    )
    if file_url:
        body_text += f"\n{file_url}"
    body_html = (
        "<pre style='font-family:inherit;white-space:pre-wrap'>"
        + html.escape(body_text)
        + "</pre>"
    )
    if file_url:
        body_html += chips.download_button_html(file_url, label=schedule["view_name"])
    try:
        channel = send_or_outbox(
            recipients=recipients,
            subject=subject,
            body=body_text,
            filename=name,
            xlsx_bytes=xlsx,
            cc=cc,
            bcc=bcc,
            body_html=body_html,
        )
    except GraphMailError as err:
        store.mark_schedule_run(schedule["id"], "failure", str(err), at=at)
        return "failure"
    dest = "Graph" if channel == "graph" else "the outbox"
    message = f"Mail queued to {recipients} via {dest}"
    if file_url:
        message += f"; uploaded {file_url}"
    store.mark_schedule_run(schedule["id"], "success", message, at=at)
    return "success"


def deliver_report_email(
    *,
    report_key: str,
    payload: dict,
    recipients: str,
    subject: str,
    sharepoint_folder: str = "",
) -> dict:
    source = (payload.get("data") or {}).get("source") or "mock"
    live = source == "reporting_api"
    if config.graph_mail_configured():
        body = "Excel attached." if live else "Dummy Excel attached."
    else:
        body = (
            "Excel attached. Graph secrets are not set; queued to the outbox."
            if live
            else "Dummy Excel attached. Graph secrets are not set; queued to the outbox."
        )
    xlsx = workbook_bytes(payload)
    filename = f"{report_key}.xlsx"
    file_url = ""
    if sharepoint_folder:
        try:
            uploaded = drive.upload_sharepoint(sharepoint_folder, filename, xlsx)
            file_url = str(uploaded.get("webUrl") or "")
            if file_url:
                body += f" Uploaded to {file_url}."
        except drive.DriveError as err:
            return {"ok": False, "error": str(err), "recipients": recipients, "mock": not live}
    body_html = ""
    if file_url:
        body_html = (
            "<pre style='font-family:inherit;white-space:pre-wrap'>"
            + html.escape(body)
            + "</pre>"
            + chips.download_button_html(file_url)
        )
    try:
        channel = send_or_outbox(
            recipients=recipients,
            subject=subject,
            body=body,
            filename=filename,
            xlsx_bytes=xlsx,
            body_html=body_html,
        )
    except GraphMailError as err:
        return {"ok": False, "error": str(err), "recipients": recipients, "mock": not live}
    return {"ok": True, "recipients": recipients, "mock": not live, "channel": channel, "file_url": file_url}
