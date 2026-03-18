"""
Azure Automation management client.

Wraps the Azure Management SDK to list, create, update, and delete
schedules on the DailyInvoicedReport Automation Account, and to link
them to the universal_runbook.
"""

import logging
import os
import uuid
from datetime import datetime

from azure.identity import ClientSecretCredential
from azure.mgmt.automation import AutomationClient
from azure.mgmt.automation.models import (
    JobCreateParameters,
    JobScheduleCreateParameters,
    RunbookAssociationProperty,
    ScheduleAssociationProperty,
    ScheduleCreateOrUpdateParameters,
)

from config.settings import get_client_id, get_client_secret, get_tenant_id

log = logging.getLogger(__name__)

RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "Daily_Invoiced_Report")
AUTOMATION_ACCOUNT = os.environ.get("AZURE_AUTOMATION_ACCOUNT", "DailyInvoicedReport")
RUNBOOK_NAME = os.environ.get("AZURE_RUNBOOK_NAME", "universal_runbook")


def _get_subscription_id() -> str:
    sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    if not sub_id:
        raise RuntimeError(
            "AZURE_SUBSCRIPTION_ID is not set. Add it to your .env / App Service settings."
        )
    return sub_id


def get_client() -> AutomationClient:
    """Return an authenticated AutomationClient."""
    credential = ClientSecretCredential(
        tenant_id=get_tenant_id(),
        client_id=get_client_id(),
        client_secret=get_client_secret(),
    )
    return AutomationClient(credential, _get_subscription_id())


# -- Schedules -------------------------------------------------------------

def list_schedules() -> list[dict]:
    """List all schedules on the Automation Account."""
    client = get_client()
    results = []
    for s in client.schedule.list_by_automation_account(RESOURCE_GROUP, AUTOMATION_ACCOUNT):
        results.append(_schedule_to_dict(s))
    return results


def get_schedule(name: str) -> dict | None:
    """Get a single schedule by name."""
    client = get_client()
    try:
        s = client.schedule.get(RESOURCE_GROUP, AUTOMATION_ACCOUNT, name)
        return _schedule_to_dict(s)
    except Exception:
        log.debug("Schedule '%s' not found", name)
        return None


def create_or_update_schedule(
    name: str,
    frequency: str = "Day",
    interval: int = 1,
    start_time: str = "",
    time_zone: str = "America/New_York",
    description: str = "",
    days_of_week: list[str] | None = None,
    month_days: list[int] | None = None,
) -> dict:
    """Create or update a schedule. Returns the schedule dict."""
    client = get_client()

    params = ScheduleCreateOrUpdateParameters(
        name=name,
        description=description,
        frequency=frequency,
        interval=interval,
        start_time=start_time or datetime.utcnow().isoformat(),
        time_zone=time_zone,
    )

    from azure.mgmt.automation.models import AdvancedSchedule
    advanced = None
    if frequency == "Week" and days_of_week:
        advanced = AdvancedSchedule(week_days=days_of_week)
    elif frequency == "Month" and month_days:
        advanced = AdvancedSchedule(month_days=month_days)
    if advanced:
        params.advanced_schedule = advanced

    result = client.schedule.create_or_update(
        RESOURCE_GROUP, AUTOMATION_ACCOUNT, name, params
    )
    log.info("Created/updated schedule: %s", name)
    return _schedule_to_dict(result)


def update_schedule_enabled(name: str, enabled: bool) -> dict:
    """Enable or disable a schedule. Raises on failure."""
    client = get_client()
    from azure.mgmt.automation.models import ScheduleUpdateParameters
    result = client.schedule.update(
        RESOURCE_GROUP, AUTOMATION_ACCOUNT, name,
        ScheduleUpdateParameters(is_enabled=enabled),
    )
    log.info("Schedule '%s' enabled=%s", name, enabled)
    return _schedule_to_dict(result)


def delete_schedule(name: str) -> None:
    """Delete a schedule by name. Raises on failure."""
    client = get_client()
    client.schedule.delete(RESOURCE_GROUP, AUTOMATION_ACCOUNT, name)
    log.info("Deleted schedule: %s", name)


# -- Job Schedules (schedule <-> runbook links) ----------------------------

def list_job_schedules() -> list[dict]:
    """List all job-schedule links for the Automation Account.

    The list endpoint often omits parameters, so we fetch each
    job-schedule individually to get the full details.
    """
    client = get_client()
    results = []
    for js in client.job_schedule.list_by_automation_account(
        RESOURCE_GROUP, AUTOMATION_ACCOUNT
    ):
        js_id = getattr(js, "job_schedule_id", None)
        if js_id:
            try:
                full = client.job_schedule.get(
                    RESOURCE_GROUP, AUTOMATION_ACCOUNT, js_id
                )
                results.append(_job_schedule_to_dict(full))
            except Exception:
                log.warning("Could not fetch job-schedule %s, using summary", js_id)
                results.append(_job_schedule_to_dict(js))
        else:
            results.append(_job_schedule_to_dict(js))
    return results


def link_schedule_to_runbook(
    schedule_name: str,
    report_name: str,
    extra_args: str = "",
) -> dict:
    """Create a job-schedule linking a schedule to universal_runbook with parameters."""
    client = get_client()
    job_schedule_id = str(uuid.uuid4())

    parameters = {"report_name": report_name}
    if extra_args:
        parameters["extra_args"] = extra_args

    params = JobScheduleCreateParameters(
        schedule=ScheduleAssociationProperty(name=schedule_name),
        runbook=RunbookAssociationProperty(name=RUNBOOK_NAME),
        parameters=parameters,
    )

    result = client.job_schedule.create(
        RESOURCE_GROUP, AUTOMATION_ACCOUNT, job_schedule_id, params
    )
    log.info("Linked schedule '%s' to runbook with report_name='%s'", schedule_name, report_name)
    return _job_schedule_to_dict(result)


def unlink_schedule_from_runbook(job_schedule_id: str) -> None:
    """Remove a job-schedule link. Raises on failure."""
    client = get_client()
    client.job_schedule.delete(
        RESOURCE_GROUP, AUTOMATION_ACCOUNT, job_schedule_id
    )
    log.info("Unlinked job schedule: %s", job_schedule_id)


# -- Sync from Azure -------------------------------------------------------

def sync_from_azure() -> list[dict]:
    """Pull all schedules and job-schedule links from Azure into local DB.

    Returns the list of schedule dicts that were synced.
    """
    from webapp.db import delete_all_schedules_db, upsert_schedule

    schedules = list_schedules()
    job_schedules = list_job_schedules()

    log.info("Found %d schedules and %d job-schedule links", len(schedules), len(job_schedules))

    js_by_schedule = {}
    for js in job_schedules:
        sched_name = js.get("schedule_name", "")
        log.info("Job-schedule link: schedule=%r, runbook=%r, params=%r, id=%r",
                 sched_name, js.get("runbook_name"), js.get("parameters"), js.get("job_schedule_id"))
        if sched_name:
            js_by_schedule[sched_name] = js

    delete_all_schedules_db()

    synced = []
    now = datetime.now().isoformat(timespec="seconds")
    for s in schedules:
        js = js_by_schedule.get(s["name"], {})
        report_key, extra_args = _extract_params(js.get("parameters") or {})
        log.info("Schedule '%s': matched job-schedule=%r, report_key=%r, extra_args=%r",
                 s["name"], bool(js), report_key, extra_args)

        upsert_schedule(
            name=s["name"],
            report_key=report_key,
            extra_args=extra_args,
            frequency=s.get("frequency", "Day"),
            interval_val=s.get("interval", 1),
            start_time=s.get("start_time", ""),
            time_zone=s.get("time_zone", "America/New_York"),
            days_of_week=s.get("days_of_week", ""),
            month_days=s.get("month_days", ""),
            enabled=s.get("is_enabled", True),
            description=s.get("description", ""),
            azure_schedule_name=s["name"],
            azure_job_schedule_id=js.get("job_schedule_id", ""),
        )
        synced.append({**s, "report_key": report_key, "extra_args": extra_args})

    log.info("Synced %d schedules from Azure Automation", len(synced))
    return synced


def start_job(report_name: str, extra_args: str = "") -> str:
    """Start an Azure Automation Job for the universal_runbook.

    Returns the job name (a UUID) which can be used to poll status.
    """
    client = get_client()
    job_name = str(uuid.uuid4())

    parameters = {"report_name": report_name}
    if extra_args:
        parameters["extra_args"] = extra_args

    params = JobCreateParameters(
        runbook=RunbookAssociationProperty(name=RUNBOOK_NAME),
        parameters=parameters,
    )

    client.job.create(RESOURCE_GROUP, AUTOMATION_ACCOUNT, job_name, params)
    log.info("Started job %s (report=%s, args=%s)", job_name, report_name, extra_args)
    return job_name


def list_jobs(limit: int = 200) -> list[dict]:
    """List recent jobs from Azure Automation.

    Returns a list of dicts with job_id, runbook, status, start_time,
    end_time, parameters (report_name, extra_args).
    """
    client = get_client()
    jobs = []
    try:
        for i, job in enumerate(
            client.job.list_by_automation_account(RESOURCE_GROUP, AUTOMATION_ACCOUNT)
        ):
            if i >= limit:
                break
            raw_params = getattr(job, "parameters", None) or {}
            params = {k.lower(): v for k, v in raw_params.items()}
            report_name, extra_args = _extract_params(params)

            rb = getattr(job, "runbook", None)
            start = getattr(job, "start_time", None)
            end = getattr(job, "end_time", None)
            creation = getattr(job, "creation_time", None)

            jobs.append({
                "job_id": getattr(job, "name", "") or "",
                "runbook_name": rb.name if rb else "",
                "status": getattr(job, "status", "") or "",
                "start_time": start.isoformat() if start else None,
                "end_time": end.isoformat() if end else None,
                "creation_time": creation.isoformat() if creation else None,
                "report_name": report_name,
                "extra_args": extra_args,
                "webapp_record_id": params.get("webapp_record_id", ""),
            })
        log.info("Listed %d jobs from Azure Automation", len(jobs))
    except Exception:
        log.exception("Failed to list jobs from Azure Automation")
    return jobs


# -- Helpers ---------------------------------------------------------------

def _extract_params(params: dict) -> tuple[str, str]:
    """Extract report_key and extra_args from job-schedule parameters.

    Handles two formats:
    1. Named params (created by this app):
       {'report_name': 'ordered', 'extra_args': '--period daily'}
    2. Positional params (created via Azure Portal):
       {'[parameter 1]': '"invoiced"', '[parameter 2]': '"--salesman all"', ...}
       Parameter 1 is always the report name; the rest are extra args.
    """
    if not params:
        return "", ""

    if "report_name" in params:
        return params["report_name"].strip().strip('"'), params.get("extra_args", "").strip().strip('"')

    positional = sorted(
        ((k, v) for k, v in params.items() if k.startswith("[parameter")),
        key=lambda x: x[0],
    )
    if not positional:
        return "", ""

    report_key = positional[0][1].strip().strip('"')
    extra_parts = [v.strip().strip('"') for _, v in positional[1:]]
    extra_args = " ".join(extra_parts)
    return report_key, extra_args

def _schedule_to_dict(s) -> dict:
    """Convert an Azure Schedule model to a plain dict."""
    advanced = getattr(s, "advanced_schedule", None)
    week_days = []
    month_days = []
    if advanced:
        week_days = getattr(advanced, "week_days", None) or []
        month_days = getattr(advanced, "month_days", None) or []

    start = getattr(s, "start_time", None)
    next_run = getattr(s, "next_run", None)

    month_days_str = ",".join(str(d) for d in month_days) if month_days else ""

    return {
        "name": s.name,
        "description": getattr(s, "description", "") or "",
        "frequency": getattr(s, "frequency", "Day") or "Day",
        "interval": getattr(s, "interval", 1) or 1,
        "start_time": start.isoformat() if start else "",
        "time_zone": getattr(s, "time_zone", "America/New_York") or "America/New_York",
        "is_enabled": bool(getattr(s, "is_enabled", True)),
        "next_run": next_run.isoformat() if next_run else "",
        "days_of_week": ",".join(week_days) if week_days else "",
        "month_days": month_days_str,
    }


def _job_schedule_to_dict(js) -> dict:
    """Convert an Azure JobSchedule model to a plain dict."""
    sched = getattr(js, "schedule", None)
    rb = getattr(js, "runbook", None)

    raw_params = getattr(js, "parameters", None) or {}
    params = {k.lower(): v for k, v in raw_params.items()}

    return {
        "job_schedule_id": getattr(js, "job_schedule_id", "") or "",
        "schedule_name": sched.name if sched else "",
        "runbook_name": rb.name if rb else "",
        "parameters": params,
    }
