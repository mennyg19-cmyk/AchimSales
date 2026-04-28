"""Schedule runner: fetches data, builds the workbook, delivers via email +/-
SharePoint, and records a full debug log per run.

This is designed to be safe to call from a request handler (manual "Run now"
buttons) as well as from a future background scheduler. There is no implicit
request context -- the caller passes the schedule row and a ``triggered_by``
identifier.

"Expensive logging" means every major step appends a timestamped line to
``schedule_runs.debug_log`` so admins can reconstruct exactly what happened.
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from test.config.reports import get_report
from test.webapp.db import (
    append_schedule_run_log,
    create_schedule_run,
    finalize_schedule_run,
    update_master_schedule_last_run,
    update_personal_schedule_last_run,
)
from test.webapp.services.email_outbox import send_report_email
from test.webapp.services.report_export import build_workbook
from test.webapp.services.report_runner import run_report

log = logging.getLogger(__name__)


def _normalise_layouts(raw) -> tuple[dict, set[str]]:
    out: dict[str, dict] = {}
    dropped: set[str] = set()
    if not isinstance(raw, dict):
        return out, dropped
    for tab_key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("tab_hidden"):
            dropped.add(str(tab_key))
            continue
        out[str(tab_key)] = {
            "order":  list(entry.get("field_order") or entry.get("order") or []),
            "hidden": list(entry.get("hidden_fields") or entry.get("hidden") or []),
        }
    return out, dropped


def _load_json(s: str | None, default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def run_schedule(
    *,
    schedule_type: str,              # 'master' | 'personal'
    schedule: dict,                  # row from master_schedules or schedules
    triggered_by: str | None = None, # email of user, None for automatic runs
    sender_email: str | None = None, # "From" on the outgoing email
) -> dict:
    """Execute a schedule. Always returns a dict with at least {ok, run_id}.

    Never raises. Failures are recorded in the schedule_runs row.
    """
    assert schedule_type in ("master", "personal")
    schedule_id = int(schedule["id"])
    run_id = create_schedule_run(
        schedule_type=schedule_type,
        schedule_id=schedule_id,
        schedule_name=schedule.get("name"),
        report_key=schedule.get("report_key"),
        report_name=schedule.get("report_name"),
        triggered_by=triggered_by,
    )

    def logline(line: str) -> None:
        try:
            append_schedule_run_log(run_id, line)
        except Exception:
            log.exception("append_schedule_run_log failed")
        log.info("run %s: %s", run_id, line)

    logline(f"Run started. type={schedule_type} schedule_id={schedule_id} "
            f"triggered_by={triggered_by or '<auto>'}")

    try:
        report_key  = schedule["report_key"]
        report_name = schedule["report_name"]
        params      = _load_json(schedule.get("params_json"), {})
        layouts_raw = _load_json(schedule.get("layouts_json"), {})
        recipients  = (schedule.get("recipients") or "").strip()
        sp_path     = (schedule.get("sharepoint_path") or "").strip() or None

        try:
            get_report(report_key)
        except Exception:
            raise RuntimeError(f"Unknown report key: {report_key!r}")

        logline(f"Loaded schedule: report={report_key} ({report_name}); "
                f"params keys={list(params.keys())}; "
                f"layouts tabs={list(layouts_raw.keys()) if isinstance(layouts_raw, dict) else '<none>'}; "
                f"recipients={'yes' if recipients else 'no'}; "
                f"sharepoint={'yes' if sp_path else 'no'}")

        layouts, dropped = _normalise_layouts(layouts_raw)
        if dropped:
            logline(f"Dropping {len(dropped)} hidden tab(s): {sorted(dropped)}")

        logline("Running report (fetching data)...")
        payload = run_report(report_key, report_name, params or {})
        if dropped:
            payload = dict(payload)
            payload["tabs"] = [
                t for t in payload.get("tabs", [])
                if str(t.get("key")) not in dropped
            ]
        rows_total = sum(len(t.get("rows") or []) for t in payload.get("tabs", []))
        logline(f"Report returned {rows_total} total rows across {len(payload.get('tabs', []))} tab(s)")

        logline("Building xlsx workbook...")
        xlsx_bytes = build_workbook(payload, layouts)
        logline(f"Workbook built ({len(xlsx_bytes)} bytes)")

        filename = f"{report_name.replace(' ', '_')}.xlsx"
        sharepoint_saved = False
        sharepoint_saved_path: str | None = None
        email_sent = False

        # --- SharePoint upload (first so its URL can appear in the email) ---
        if sp_path:
            try:
                from test.webapp.services.sharepoint import upload_file
                logline(f"Uploading to SharePoint: {sp_path}/{filename}")
                result = upload_file(sp_path, filename, xlsx_bytes)
                sharepoint_saved = True
                sharepoint_saved_path = sp_path
                logline(f"SharePoint upload OK: {result.get('webUrl')}")
            except Exception as e:
                logline(f"SharePoint upload FAILED: {e}")
                logline(traceback.format_exc())

        # --- Email delivery ---
        if recipients:
            effective_sender = sender_email or (schedule.get("created_by") if schedule_type == "master"
                                                else schedule.get("user_email")) or "scheduler@test"
            subject = f"{report_name} -- scheduled run"
            logline(f"Emailing {recipients} (sender={effective_sender})")
            try:
                result = send_report_email(
                    sender_email=effective_sender,
                    recipients_raw=recipients,
                    subject=subject,
                    report_key=report_key,
                    report_name=report_name,
                    xlsx_bytes=xlsx_bytes,
                    filename=filename,
                    # We don't re-upload to SP here -- we already handled it above.
                    sharepoint_path=None,
                )
                if result.get("ok"):
                    email_sent = True
                    logline(f"Email queued into outbox as {result.get('eml_name')}")
                else:
                    logline(f"Email FAILED: {result.get('error')}")
            except Exception as e:
                logline(f"Email exception: {e}")
                logline(traceback.format_exc())

        if not (email_sent or sharepoint_saved):
            raise RuntimeError(
                "Schedule produced no deliveries (no recipients and no SharePoint path, "
                "or both failed). See debug log above."
            )

        finalize_schedule_run(
            run_id,
            status="success",
            rows_returned=rows_total,
            email_sent=email_sent,
            email_recipients=recipients or None,
            sharepoint_saved=sharepoint_saved,
            sharepoint_path=sharepoint_saved_path,
        )
        logline("Run finished SUCCESS")

        if schedule_type == "master":
            update_master_schedule_last_run(schedule_id)
        else:
            update_personal_schedule_last_run(schedule_id)

        return {
            "ok":                True,
            "run_id":            run_id,
            "rows_returned":     rows_total,
            "email_sent":        email_sent,
            "sharepoint_saved":  sharepoint_saved,
        }

    except Exception as e:
        err = str(e)
        tb = traceback.format_exc()
        logline(f"Run FAILED: {err}")
        logline(tb)
        try:
            finalize_schedule_run(run_id, status="failed", error_message=err)
        except Exception:
            log.exception("finalize_schedule_run(failed) crashed")
        return {"ok": False, "run_id": run_id, "error": err}
