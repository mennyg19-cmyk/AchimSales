"""Which saved views can become a personal schedule."""

from __future__ import annotations

from web.auth.principal import _PRIVILEGED
from web.data.connection import Database
from web.data.repositories.report_defaults import DEFAULT_VIEW_NAME, normalize_view_name
from web.data.repositories.saved_reports import SavedReport, SavedReportRepository
from web.data.repositories.schedules import Schedule, ScheduleRepository, next_copy_name
from web.data.repositories.users import User, UserRepository


def is_custom_date_params(params: dict | None) -> bool:
    """True when the view is a custom from/to range, not a named period."""
    raw = params or {}
    period = str(raw.get("period") or "").strip().lower()
    if period == "custom":
        return True
    if period:
        return False
    return bool(raw.get("from") and raw.get("to"))


def is_schedulable_saved_view(preset: SavedReport) -> bool:
    if is_custom_date_params(preset.params):
        return False
    name = (preset.name or "").strip()
    if not name or normalize_view_name(name) == DEFAULT_VIEW_NAME:
        return False
    return True


def owner_is_privileged(user: User | None) -> bool:
    return bool(user and user.role in _PRIVILEGED)


def convert_personal_schedules(db: Database) -> int:
    """One-time: snapshot each personal schedule into a named saved view.

    Idempotent. Company (master) rows are not touched. Custom from/to views
    are still created so the schedule keeps running; they stay off the picker.
    """
    users = UserRepository(db)
    saved = SavedReportRepository(db)
    schedules = ScheduleRepository(db)
    converted = 0
    for sched in schedules.list_all():
        owner = users.get_by_id(sched.owner_user_id)
        if owner is None:
            continue
        if _already_backed_by_view(saved, sched):
            _normalize_recipients(schedules, sched, owner)
            continue
        view_name = _imported_view_name(saved, sched)
        saved.create(
            sched.owner_user_id, sched.report_key, view_name,
            sched.params or {}, sched.layout or {},
        )
        schedules.update(
            sched.id, sched.owner_user_id,
            params=sched.params or {}, layout=sched.layout or {},
            cadence=sched.cadence or {},
            recipients=_recipients_for_owner(sched.recipients, owner),
            sharepoint_path=sched.sharepoint_path,
            start_date=sched.start_date, end_date=sched.end_date,
            filename_template=sched.filename_template,
            view_name=view_name,
        )
        converted += 1
    return converted


def _already_backed_by_view(saved: SavedReportRepository, sched: Schedule) -> bool:
    name = normalize_view_name(getattr(sched, "view_name", None))
    if name == DEFAULT_VIEW_NAME:
        return False
    existing = saved.get_by_name(sched.owner_user_id, sched.report_key, name)
    return existing is not None


def _imported_view_name(saved: SavedReportRepository, sched: Schedule) -> str:
    existing = {p.name for p in saved.list_for_user(sched.owner_user_id)
                if p.report_key == sched.report_key}
    raw = (sched.view_name or "").strip()
    base = raw if raw and normalize_view_name(raw) != DEFAULT_VIEW_NAME else (
        f"Imported {sched.report_key} {sched.id}"
    )
    if base not in existing:
        return base[:120]
    return next_copy_name(base, existing)


def _recipients_for_owner(current: str, owner: User) -> str:
    from web.delivery.email import split_recipients

    emails = split_recipients(current or "")
    mine = (owner.email or "").strip().lower()
    if not mine:
        return ", ".join(emails)
    if owner_is_privileged(owner):
        if mine not in {e.lower() for e in emails}:
            emails = [owner.email] + emails
        return ", ".join(emails)
    return owner.email


def _normalize_recipients(schedules: ScheduleRepository, sched: Schedule, owner: User) -> None:
    wanted = _recipients_for_owner(sched.recipients, owner)
    if wanted == (sched.recipients or ""):
        return
    schedules.update(
        sched.id, sched.owner_user_id,
        params=sched.params or {}, layout=sched.layout or {},
        cadence=sched.cadence or {},
        recipients=wanted, sharepoint_path=sched.sharepoint_path,
        start_date=sched.start_date, end_date=sched.end_date,
        filename_template=sched.filename_template,
        view_name=sched.view_name,
    )
