"""Run-and-deliver orchestration shared by "email now" and scheduled runs.

Builds the report (forcing a fresh recompute), replays the saved grid layout
onto the payload, exports to xlsx, and hands off to the email service. Decoupled
from Flask so the job worker and the scheduler can both call it.

While normalized views coexist with JSON blobs, an optional ``compare_layout``
(the raw old JSON) triggers a silent second workbook write + score. Delivery
always uses ``layout`` (the new / live path).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from web.delivery.email import DeliveryResult, EmailService
from web.delivery.filename_template import resolve_filename_template, resolve_folder_template
from web.delivery.layout import apply_layout, expand_clones
from web.delivery.sharepoint import strip_reports_home
from web.delivery.workbook_parity import (
    ViewWorkbookParityRepository,
    parity_root,
    run_parity_files,
)
from web.jobs.trace import raise_if_cancelled, step as job_step
from web.reporting.export import _MAX_SHEET_ROWS_IN_MAIN, build_workbook_bundle
from web.reporting.jobs import BuilderResolver
from web.reporting.report_service import invoiced_skip_commissions
from web.reporting.runner import ReportRunner

log = logging.getLogger(__name__)

# Silent dual-build + full cell compare of a second YTD Ordered workbook (500k+
# grid rows) can OOM / wedge the B1 worker after the real file is already built.
# Deliveries still go out; digests just miss that one dual score.
# Keep in lockstep with the companion-split threshold: after a split, oversized
# tab rows are cleared, so parity must skip whenever any sheet was large enough
# to leave the main book.
_MAX_PARITY_GRID_ROWS = _MAX_SHEET_ROWS_IN_MAIN


@dataclass
class DeliveryOutcome:
    result: DeliveryResult
    row_count: int
    # Optional per-leg details for fan-out runs (kind, recipients, salesman, …).
    deliveries: list[dict] | None = None


class DeliveryService:
    def __init__(self, runner: ReportRunner, builder_resolver: BuilderResolver,
                 email: EmailService, *, db=None, precious_db_path=None,
                 parity_enabled: bool = True):
        self.runner = runner
        self.builder_resolver = builder_resolver
        self.email = email
        self.db = db
        self.precious_db_path = precious_db_path
        self.parity_enabled = parity_enabled

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
                        schedule_name: str = "",
                        subject_template: str = "",
                        body_html_template: str = "",
                        compare_layout: dict | None = None,
                        parity_view_name: str = "",
                        parity_view_id: str | None = None,
                        parity_schedule_kind: str = "",
                        parity_schedule_id: int | None = None) -> DeliveryOutcome:
        builder = self.builder_resolver(report_key)
        run_params = dict(params or {})
        if report_key == "invoiced" and invoiced_skip_commissions(run_params, layout):
            run_params["_skip_commissions"] = True
        raise_if_cancelled()
        job_step("report", f"building {report_key}")
        outcome = self.runner.run(
            report_key=report_key, identity=identity,
            visible_salesman_keys=visible_salesman_keys, builder_version=builder_version,
            params=run_params, builder=builder, force_refresh=True,
        )
        payload = apply_layout(expand_clones(outcome.payload, layout), layout)
        rows = sum(len(t.get("rows") or []) for t in payload.get("tabs") or [])
        job_step("report", f"{report_key} {rows} grid rows after layout")
        if rows == 0 and not email_on_empty:
            return DeliveryOutcome(
                result=DeliveryResult(
                    ok=True,
                    error="No data — email/folder delivery skipped (no-data checkbox off).",
                ),
                row_count=0,
            )
        raise_if_cancelled()
        job_step("workbook", "building xlsx")
        bundle = build_workbook_bundle(payload, layout)
        xlsx = bundle.main
        job_step(
            "workbook",
            f"{len(xlsx)} bytes main"
            + (f"; {len(bundle.extras)} companion file(s)" if bundle.extras else ""),
        )
        self._maybe_parity(
            report_key=report_key, payload=outcome.payload, layout=layout,
            compare_layout=compare_layout, delivered_xlsx=xlsx,
            view_name=parity_view_name, view_id=parity_view_id,
            schedule_kind=parity_schedule_kind, schedule_id=parity_schedule_id,
            schedule_name=schedule_name, row_count=rows,
        )
        raise_if_cancelled()
        filename = resolve_filename_template(
            filename_template, report_name=report_name, params=params or {},
            schedule_name=schedule_name,
        )
        folder = strip_reports_home(resolve_folder_template(
            sharepoint_path, report_name=report_name, params=params or {},
            schedule_name=schedule_name,
        ))
        to = recipients
        cc = cc_raw
        bcc = bcc_raw
        if rows == 0 and empty_recipients_override:
            to = empty_recipients_override
            cc = ""
            bcc = ""
        companions: list[tuple[str, bytes]] = []
        if bundle.extras:
            base, dot, ext = filename.rpartition(".")
            if not dot:
                base, ext = filename, "xlsx"
            for part in bundle.extras:
                companions.append((f"{base}__{part.stem}.{ext}", part.data))
                job_step(
                    "workbook",
                    f"companion ready {base}__{part.stem}.{ext} "
                    f"({part.row_count} rows, {len(part.data)} bytes)",
                )
            note = "\n".join(
                f"- {name} ({part.row_count} rows)"
                for (name, _), part in zip(companions, bundle.extras)
            )
            body_text = (
                (body_text or "").rstrip()
                + "\n\nLarge sheets were written as separate files in the same folder:\n"
                + note
                + "\n"
            ).lstrip()
        result = self.email.deliver(
            subject=subject or report_name, recipients_raw=to, body_text=body_text,
            report_name=report_name, filename=filename, xlsx_bytes=xlsx,
            sharepoint_path=folder or None,
            onedrive_user=(onedrive_user or "").strip() or None,
            cc_raw=cc or "", bcc_raw=bcc or "",
            subject_template=subject_template, body_html_template=body_html_template,
            schedule_name=schedule_name, params=params or {},
            companion_files=companions or None,
        )
        return DeliveryOutcome(result=result, row_count=rows)

    def send_no_data_notice(self, *, recipients: str, subject: str, body_text: str,
                            report_name: str) -> DeliveryOutcome:
        """Text-only mail when a split salesman file has no rows. No workbook."""
        result = self.email.deliver(
            subject=subject, recipients_raw=recipients, body_text=body_text,
            report_name=report_name, filename="", xlsx_bytes=None,
        )
        return DeliveryOutcome(result=result, row_count=0)

    def _maybe_parity(self, *, report_key: str, payload: dict, layout: dict,
                      compare_layout: dict | None, delivered_xlsx: bytes,
                      view_name: str, view_id: str | None,
                      schedule_kind: str, schedule_id: int | None,
                      schedule_name: str, row_count: int) -> None:
        if not self.parity_enabled or compare_layout is None or self.db is None:
            return
        if row_count == 0:
            return
        if row_count > _MAX_PARITY_GRID_ROWS:
            job_step(
                "parity",
                f"skipped ({row_count} grid rows > {_MAX_PARITY_GRID_ROWS})",
            )
            return
        try:
            root = parity_root(self.precious_db_path or ".")
            result = run_parity_files(
                root=root, report_key=report_key, view_name=view_name,
                schedule_name=schedule_name, payload=payload,
                new_layout=layout or {}, old_layout=compare_layout or {},
                delivered_xlsx=delivered_xlsx,
            )
            ViewWorkbookParityRepository(self.db).record(
                report_key=report_key, view_name=view_name, view_id=view_id,
                schedule_kind=schedule_kind, schedule_id=schedule_id,
                schedule_name=schedule_name, result=result,
            )
            job_step(
                "parity",
                f"{'MATCH' if result.matched else 'DIFF'} "
                f"old={result.old_path} new={result.new_path}",
            )
        except Exception:  # noqa: BLE001 - never fail a delivery on parity
            log.exception("view workbook parity failed (delivery continues)")
