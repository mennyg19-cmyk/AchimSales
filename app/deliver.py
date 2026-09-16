"""Build a workbook and send it (Graph when secrets exist, else sqlite outbox)."""

from __future__ import annotations

import logging

from datetime import datetime

import catalog
import config
import store
from doorway import DoorwayError
from export_xlsx import workbook_bytes
from layout import apply_layout
from mail import GraphMailError, mailer, split_recipients
from reports import build_payload

log = logging.getLogger(__name__)


def _filename(template: str, view_name: str) -> str:
    raw = (template or "").strip() or f"{view_name}.xlsx"
    name = raw.replace("{Schedule}", view_name)
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    return name[:180]


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
        )
    except GraphMailError:
        log.warning("Graph send failed; outbox row already written", exc_info=True)
        raise
    return "graph"


def deliver_schedule(schedule: dict, user: dict, at: datetime | None = None) -> str:
    spec = catalog.spec(schedule["report_key"])
    if spec is None:
        store.mark_schedule_run(schedule["id"], "failure", "Unknown report on the saved view.", at=at)
        return "failure"
    try:
        payload = build_payload(schedule["report_key"], user, schedule.get("params") or {})
    except DoorwayError as err:
        store.mark_schedule_run(schedule["id"], "failure", str(err), at=at)
        return "failure"
    payload = apply_layout(payload, schedule.get("layout"))
    store.save_job(schedule["report_key"], schedule["view_name"], payload, owner_email=user["email"])
    recipients = store.mail_recipients(schedule["recipients"])
    source = (payload.get("data") or {}).get("source") or "mock"
    live = source == "reporting_api"
    extra = _extras(schedule)
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
    if schedule.get("sharepoint_folder") or schedule.get("onedrive_folder"):
        detail += " SharePoint/OneDrive upload is not Graph-wired yet."
    subject = schedule.get("subject") or (
        schedule["view_name"] if live else f"[MOCK] {schedule['view_name']}"
    )
    xlsx = workbook_bytes(payload)
    name = _filename(schedule.get("filename") or "", schedule["view_name"])
    try:
        channel = send_or_outbox(
            recipients=recipients,
            subject=subject,
            body=detail,
            filename=name,
            xlsx_bytes=xlsx,
            cc=schedule.get("cc") or "",
            bcc=schedule.get("bcc") or "",
        )
    except GraphMailError as err:
        store.mark_schedule_run(schedule["id"], "failure", str(err), at=at)
        return "failure"
    dest = "Graph" if channel == "graph" else "the outbox"
    store.mark_schedule_run(schedule["id"], "success", f"Mail queued to {recipients} via {dest}", at=at)
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
    if sharepoint_folder:
        body += f" Would upload to {sharepoint_folder}. SharePoint upload is not Graph-wired yet."
    xlsx = workbook_bytes(payload)
    try:
        channel = send_or_outbox(
            recipients=recipients,
            subject=subject,
            body=body,
            filename=f"{report_key}.xlsx",
            xlsx_bytes=xlsx,
        )
    except GraphMailError as err:
        return {"ok": False, "error": str(err), "recipients": recipients, "mock": not live}
    return {"ok": True, "recipients": recipients, "mock": not live, "channel": channel}
