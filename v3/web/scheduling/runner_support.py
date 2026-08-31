"""Schedule-run helpers that do not need ScheduleRunner state."""

from __future__ import annotations

from web.data.repositories.delivery_legs import DeliveryLegRepository
from web.data.repositories.schedules import MASTER, PERSONAL
from web.delivery.email import DeliveryResult
from web.delivery.service import DeliveryOutcome
from web.delivery.sharepoint import TEST_SHAREPOINT_FOLDER

_DELIVERY_PARAM_KEYS = {
    "split_by_salesman", "email_to_salesmen", "email_salesman_keys",
    "email_cc", "email_bcc", "email_on_no_data", "email_on_no_data_me_only",
    "folder_kind", "skip_sabbath",
}


def _sharepoint_for_test(test_to, live_path: str) -> str:
    """Test mode writes to Test, never to the live Daily/YTD folder."""
    if not test_to:
        return live_path or ""
    return TEST_SHAREPOINT_FOLDER if live_path else ""


def _commit_email_folder_legs(legs: DeliveryLegRepository, email_key: str, folder_key: str,
                              recipients: str, path: str, skip_email: bool, skip_folder: bool,
                              outcome: DeliveryOutcome) -> None:
    error = outcome.result.error or ""
    if recipients.strip() and not skip_email:
        email_failed = (
            "Graph failed" in error or "SMTP failed" in error
            or error.startswith("Mail is not configured")
        )
        if outcome.result.ok and outcome.row_count == 0:
            legs.mark_sent(email_key, row_count=0)
        elif outcome.result.sent_via_smtp or (
            outcome.result.send_channel in ("graph", "smtp", "outbox", "skipped")
            and not email_failed
        ):
            legs.mark_sent(email_key, row_count=outcome.row_count)
        else:
            legs.mark_failed(email_key, error or "email failed")
    if path.strip() and not skip_folder:
        if outcome.result.sharepoint_saved:
            legs.mark_sent(folder_key, row_count=outcome.row_count)
        else:
            legs.mark_failed(folder_key, outcome.result.sharepoint_error or error or "upload failed")


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


def _salesman_targets(db, params: dict | None) -> list[str]:
    p = params or {}
    selected = _as_str_list(p.get("salesman"))
    if selected and p.get("email_to_salesmen"):
        return selected
    email_keys = _as_str_list(p.get("email_salesman_keys"))
    if email_keys:
        return email_keys
    if _as_bool(p.get("split_by_salesman")):
        from web.data.repositories.salesmen import SalesmanRepository
        return SalesmanRepository(db).keys_with_email()
    return []


def _delivery_leg(outcome: DeliveryOutcome, *, kind: str, salesman: str = "") -> dict:
    mail = outcome.result
    return {
        "kind": kind,
        "salesman": salesman,
        "recipients": list(mail.recipients),
        "ok": mail.ok,
        "skipped": False,
        "error": mail.error or mail.sharepoint_error or "",
        "rows": outcome.row_count,
        "send_channel": mail.send_channel,
        "sent": mail.sent_via_smtp,
        "unknown": mail.unknown,
        "sharepoint_saved": mail.sharepoint_saved,
        "sharepoint_url": mail.sharepoint_url or "",
        "eml": mail.eml_name,
        "outbox_id": mail.outbox_id,
    }


def _output_meta(outcome: DeliveryOutcome) -> dict:
    mail = outcome.result
    meta = {
        "summary": _summary_message(outcome, ok=mail.ok),
        "outbox_id": mail.outbox_id,
        "eml": mail.eml_name,
        "sent_smtp": mail.sent_via_smtp,
        "send_channel": mail.send_channel,
        "sharepoint_saved": mail.sharepoint_saved,
        "sharepoint_url": mail.sharepoint_url,
        "sharepoint_error": mail.sharepoint_error,
        "recipients": mail.recipients,
        "error": mail.error or "",
    }
    if outcome.deliveries:
        meta["deliveries"] = outcome.deliveries
    return meta


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
    unknown = any(o.result.unknown for o in outcomes)
    notes = [o.result.error for o in outcomes if o.result.error]
    recipients = [email for o in outcomes for email in o.result.recipients]
    eml_names = [o.result.eml_name for o in outcomes if o.result.eml_name]
    channels = [o.result.send_channel for o in outcomes if o.result.send_channel]
    combined = DeliveryResult(
        ok=ok and not unknown,
        error="; ".join(notes),
        recipients=recipients,
        eml_name=", ".join(eml_names),
        sent_via_smtp=any(o.result.sent_via_smtp for o in outcomes),
        send_channel=channels[0] if len(set(channels)) == 1 else ("mixed" if channels else ""),
        sharepoint_saved=any(o.result.sharepoint_saved for o in outcomes),
        sharepoint_url=next((o.result.sharepoint_url for o in outcomes if o.result.sharepoint_url), None),
        sharepoint_error=next((o.result.sharepoint_error for o in outcomes if o.result.sharepoint_error), None),
        outbox_id=next((o.result.outbox_id for o in outcomes if o.result.outbox_id is not None), None),
        unknown=unknown,
    )
    return DeliveryOutcome(
        result=combined,
        row_count=sum(o.row_count for o in outcomes),
        deliveries=deliveries,
        unknown_attempt_key=next(
            (o.unknown_attempt_key for o in outcomes if o.unknown_attempt_key), ""
        ),
    )


def _summary_message(outcome: DeliveryOutcome, *, ok: bool) -> str:
    """Plain-English line for History: success details and/or failures/skips."""
    mail = outcome.result
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
            elif d.get("unknown"):
                bits.append(f"{label} unknown: {d.get('error') or 'Graph may have accepted the send'}")
            else:
                bits.append(f"{label} failed: {d.get('error') or 'delivery failed'}")
    else:
        if mail.recipients:
            channel = mail.send_channel or ("sent" if mail.sent_via_smtp else "outbox")
            bits.append(f"Email → {', '.join(mail.recipients)} via {channel}")
        if mail.sharepoint_saved:
            bits.append("SharePoint saved" + (f" ({mail.sharepoint_url})" if mail.sharepoint_url else ""))
        elif mail.sharepoint_error:
            bits.append(f"SharePoint failed: {mail.sharepoint_error}")
        if mail.error and not ok:
            bits.append(mail.error)
    if not bits:
        return "OK" if ok else (mail.error or "delivery failed")
    prefix = "OK: " if ok else "Failed: "
    body = "; ".join(bits)
    if ok and mail.error and mail.error not in body:
        body = f"{body}; {mail.error}"
    return prefix + body
