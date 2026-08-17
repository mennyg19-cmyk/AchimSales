"""Run-and-deliver orchestration shared by "email now" and scheduled runs.

Builds the report (forcing a fresh recompute), replays the saved grid layout
onto the payload, exports to xlsx, and hands off to the email service. Decoupled
from Flask so the job worker and the scheduler can both call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from web.delivery.email import DeliveryResult, EmailService
from web.delivery.filename_template import resolve_filename_template
from web.delivery.layout import apply_layout, expand_clones
from web.reporting.export import build_workbook
from web.reporting.jobs import BuilderResolver
from web.reporting.runner import ReportRunner


@dataclass
class DeliveryOutcome:
    result: DeliveryResult
    row_count: int
    # Optional per-leg details for fan-out runs (kind, recipients, salesman, …).
    deliveries: list[dict] | None = None


class DeliveryService:
    def __init__(self, runner: ReportRunner, builder_resolver: BuilderResolver,
                 email: EmailService):
        self.runner = runner
        self.builder_resolver = builder_resolver
        self.email = email

    def run_and_deliver(self, *, report_key: str, identity: str,
                        visible_salesman_keys: Iterable[str] | None,
                        builder_version: int, params: dict, layout: dict,
                        recipients: str, subject: str, report_name: str,
                        sharepoint_path: str = "", body_text: str = "",
                        filename_template: str = "",
                        onedrive_user: str = "",
                        cc_raw: str = "", bcc_raw: str = "",
                        email_on_empty: bool = True,
                        empty_recipients_override: str | None = None,
                        schedule_name: str = "") -> DeliveryOutcome:
        builder = self.builder_resolver(report_key)
        outcome = self.runner.run(
            report_key=report_key, identity=identity,
            visible_salesman_keys=visible_salesman_keys, builder_version=builder_version,
            params=params or {}, builder=builder, force_refresh=True,
        )
        payload = apply_layout(expand_clones(outcome.payload, layout), layout)
        rows = sum(len(t.get("rows") or []) for t in payload.get("tabs") or [])
        if rows == 0 and not email_on_empty:
            return DeliveryOutcome(
                result=DeliveryResult(
                    ok=True,
                    error="No data — email/folder delivery skipped (no-data checkbox off).",
                ),
                row_count=0,
            )
        xlsx = build_workbook(payload, layout)
        filename = resolve_filename_template(
            filename_template, report_name=report_name, params=params or {},
            schedule_name=schedule_name,
        )
        to = recipients
        cc = cc_raw
        bcc = bcc_raw
        if rows == 0 and empty_recipients_override:
            to = empty_recipients_override
            cc = ""
            bcc = ""
        result = self.email.deliver(
            subject=subject or report_name, recipients_raw=to, body_text=body_text,
            report_name=report_name, filename=filename, xlsx_bytes=xlsx,
            sharepoint_path=sharepoint_path or None,
            onedrive_user=(onedrive_user or "").strip() or None,
            cc_raw=cc or "", bcc_raw=bcc or "",
        )
        return DeliveryOutcome(result=result, row_count=rows)
