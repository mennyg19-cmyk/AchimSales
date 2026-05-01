"""
Universal Azure Automation Runbook.

This single file handles ALL reports. Paste it into Azure Automation once.
Control which report runs via the ``report_name`` and ``extra_args`` parameters.

Flow:
  1. Check Shabbos/Yom Tov guard (via Hebcal API for Brooklyn):
       - daily/yesterday, no-period, MTD (not month-end), YTD -> SKIP
         (catch-up logic on the next regular run widens the date range)
       - last_7_days/this_week, MTD on last day of month -> RESCHEDULE
         (create one-time Azure schedule after havdalah + 15 min)
     Handles multi-day Yom Tov + Shabbos combos (e.g. 3-day Pesach block).
  2. Read Azure Automation Variables (or env vars for local testing)
  3. Acquire Graph token, resolve SharePoint drive
  4. Download report_registry.json from SharePoint
  5. Look up the requested report -> get its required_paths
  6. Download only the required scripts from SharePoint
  7. Check catch-up: if days were missed, widen date range automatically
     (handles --period daily, last_7_days, mtd, and no-args reports;
      matches on schedule variant so nightly vs salesman don't cross-pollinate)
  8. Log STARTED to run_log.csv on SharePoint
  9. Import and run the report
 10. Log SUCCESS/FAILED to run_log.csv
 11. Upload Direct Reports/ output to SharePoint
 12. Send alert email on failure; heartbeat on success

Azure Automation Parameters:
  report_name (str, required): Key from report_registry.json, e.g. "ordered",
                               "invoiced", "amazon_weekly", or "all" to run every report.
  extra_args  (str, optional): Additional CLI args, e.g. "--period daily".
                               Merged with default_args from the registry.
                               Use "--force" to bypass the Shabbos/Yom Tov guard.
                               Use "--simulate-date 2026-04-02T05:00" to test the
                               guard for any date/time without running real reports.

Reschedule config (needed for automatic rescheduling after Shabbos/Yom Tov):
  AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_AUTOMATION_ACCOUNT,
  AZURE_RUNBOOK_NAME -- set as Automation Variables or env vars.
"""

import importlib
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from urllib.parse import unquote

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("universal_runbook")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
DEFAULT_SCRIPTS_CLOUD = "D365 F&O/scripts"
REGISTRY_FILENAME = "report_registry.json"
RUN_LOG_CLOUD_PATH = "D365 F&O/scripts/logs/run_log.csv"

# ---------------------------------------------------------------------------
# Simulated time (for testing Shabbos/YT guard without waiting for the date)
# ---------------------------------------------------------------------------
_SIMULATED_NOW = None  # Set by --simulate-date; used by _effective_now()


def _effective_now():
    """Return the current Eastern datetime, or the simulated time if set."""
    if _SIMULATED_NOW is not None:
        return _SIMULATED_NOW
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(tz=ZoneInfo("America/New_York"))


# ---------------------------------------------------------------------------
# Azure Automation / env-var config helper
# ---------------------------------------------------------------------------
_AUTOMATION_CHECKED = False
_AUTOMATION_WORKS = False


def _get_config(name, env_keys, default=""):
    """Read from Azure Automation Variables first, then env vars.

    Caches whether ``automationassets`` is usable after the first probe so
    that missing variables don't each incur a multi-minute timeout.
    """
    global _AUTOMATION_CHECKED, _AUTOMATION_WORKS

    if not _AUTOMATION_CHECKED:
        _AUTOMATION_CHECKED = True
        try:
            from automationassets import get_automation_variable  # noqa: F811
            get_automation_variable("GRAPH_TENANT_ID")
            _AUTOMATION_WORKS = True
            log.info("automationassets available -- using Automation Variables")
        except ImportError:
            _AUTOMATION_WORKS = False
        except Exception:
            _AUTOMATION_WORKS = False
            log.info("automationassets unavailable or slow; using env vars only")

    if _AUTOMATION_WORKS:
        try:
            from automationassets import get_automation_variable
            v = get_automation_variable(name)
            if v is not None and str(v).strip():
                return str(v).strip()
        except Exception:
            pass

    for key in env_keys:
        v = os.environ.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


# ---------------------------------------------------------------------------
# Graph token with automatic refresh
# ---------------------------------------------------------------------------
_TOKEN_REFRESH_MARGIN = 300  # refresh 5 min before expiry


class _TokenManager:
    """Acquires and auto-refreshes Graph tokens before they expire."""

    def __init__(self, tenant_id, client_id, client_secret):
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = None
        self._acquired_at = 0.0
        self._lifetime = 3600  # default; updated from actual response

    def _acquire(self):
        import msal
        app = msal.ConfidentialClientApplication(
            self._client_id,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            client_credential=self._client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if not result or "access_token" not in result:
            raise RuntimeError("Graph token error: " + str(result.get("error_description", result)))
        self._token = result["access_token"]
        self._acquired_at = time.monotonic()
        self._lifetime = int(result.get("expires_in", 3600))
        log.info("Graph token acquired (expires_in=%ds)", self._lifetime)

    @property
    def token(self):
        age = time.monotonic() - self._acquired_at
        if self._token is None or age >= (self._lifetime - _TOKEN_REFRESH_MARGIN):
            self._acquire()
        return self._token


def _get_graph_token(tenant_id, client_id, client_secret):
    import msal
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if not result or "access_token" not in result:
        raise RuntimeError("Graph token error: " + str(result.get("error_description", result)))
    return result["access_token"]


# ---------------------------------------------------------------------------
# SharePoint helpers (self-contained -- no dependency on core.graph)
# ---------------------------------------------------------------------------
def _resolve_token(token):
    """Accept a string token or a _TokenManager and return a fresh token string."""
    if isinstance(token, _TokenManager):
        return token.token
    return token


def _sp_resolve_drive(site_url, token):
    import requests
    from urllib.parse import urlparse
    t = _resolve_token(token)
    parsed = urlparse(site_url.strip().rstrip("/"))
    hostname = parsed.netloc
    path_part = (parsed.path or "").strip("/")
    if not path_part or path_part.lower() in ("", "sites", "sites/"):
        req_url = f"{GRAPH_BASE}/sites/root"
    else:
        site_path = "/" + path_part if not path_part.startswith("/") else path_part
        req_url = f"{GRAPH_BASE}/sites/{hostname}:{site_path}"
    headers = {"Authorization": f"Bearer {t}"}
    r = requests.get(req_url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    site_id = r.json()["id"]
    dr = requests.get(f"{GRAPH_BASE}/sites/{site_id}/drive", headers=headers, timeout=TIMEOUT)
    dr.raise_for_status()
    return site_id, dr.json()["id"]


def _sp_list_children(drive_id, cloud_path, token):
    import requests
    t = _resolve_token(token)
    p = cloud_path.replace("\\", "/").strip("/")
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{p}:/children" if p else f"{GRAPH_BASE}/drives/{drive_id}/root/children"
    r = requests.get(url, headers={"Authorization": f"Bearer {t}"}, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("value", [])


def _sp_download_content(drive_id, item_id, token):
    import requests
    t = _resolve_token(token)
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
    r = requests.get(url, headers={"Authorization": f"Bearer {t}"}, timeout=UPLOAD_TIMEOUT)
    r.raise_for_status()
    return r.content


def _sp_download_file(drive_id, cloud_path, local_path, token):
    """Download a single file. Returns True on success."""
    import requests
    t = _resolve_token(token)
    p = cloud_path.replace("\\", "/").strip("/")
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{p}"
    r = requests.get(url, headers={"Authorization": f"Bearer {t}"}, timeout=TIMEOUT)
    if r.status_code != 200:
        log.warning("Download %s returned %d", p, r.status_code)
        return False
    data = r.json()
    if "folder" in data:
        return False
    content = _sp_download_content(drive_id, data["id"], token)
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(content)
    return True


def _sp_download_folder(drive_id, cloud_path, local_path, token):
    """Recursively download a folder."""
    p = cloud_path.replace("\\", "/").strip("/")
    children = _sp_list_children(drive_id, p, token)
    if not children:
        return
    os.makedirs(local_path, exist_ok=True)
    for item in children:
        name = item.get("name", "")
        if not name or name.startswith(".") or name == "__pycache__":
            continue
        child_cloud = f"{p}/{name}" if p else name
        child_local = os.path.join(local_path, name)
        if "folder" in item:
            _sp_download_folder(drive_id, child_cloud, child_local, token)
        elif "file" in item and not name.endswith(".pyc"):
            content = _sp_download_content(drive_id, item["id"], token)
            with open(child_local, "wb") as f:
                f.write(content)
            log.info("  Downloaded: %s", child_cloud)


def _graph_request_with_retry(method, url, *, headers, max_attempts=4,
                              backoff_base=2.0, timeout=None,
                              expect_status=None, **kwargs):
    """Call Graph with exponential-backoff retry on timeouts and 5xx.

    Graph occasionally drops a connection mid-request (real-world read
    timeouts at 30s happen every few thousand calls).  Without retry a
    single hiccup crashes the whole SharePoint upload tree and an entire
    successful report run gets flagged as FAILED.  Back off 1s, 2s, 4s,
    8s between attempts, then let the caller handle the final failure.

    Returns the ``requests.Response`` if the call ultimately succeeded
    (status 2xx, or in ``expect_status`` when provided).  Raises the
    last exception / non-retryable response otherwise.
    """
    import requests
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            if attempt == max_attempts:
                raise
            sleep_s = backoff_base ** (attempt - 1)
            log.warning("Graph %s %s timeout (attempt %d/%d): %s -- retrying in %.0fs",
                        method, url.rsplit("/", 1)[-1], attempt, max_attempts, e, sleep_s)
            time.sleep(sleep_s)
            continue

        code = resp.status_code
        # Retry on 429 (throttle) and 5xx (transient server errors).
        if code == 429 or 500 <= code < 600:
            if attempt == max_attempts:
                return resp
            retry_after = resp.headers.get("Retry-After")
            try:
                sleep_s = float(retry_after) if retry_after else backoff_base ** (attempt - 1)
            except ValueError:
                sleep_s = backoff_base ** (attempt - 1)
            log.warning("Graph %s %s returned %d (attempt %d/%d) -- retrying in %.0fs",
                        method, url.rsplit("/", 1)[-1], code, attempt, max_attempts, sleep_s)
            time.sleep(sleep_s)
            continue

        return resp

    raise RuntimeError(f"Graph retry exhausted for {method} {url}") from last_exc


def _sp_upload_file(drive_id, cloud_folder, local_path, token):
    """Upload a single file to a SharePoint folder.

    Returns the SharePoint webUrl of the uploaded file, or None on failure.
    """
    t = _resolve_token(token)
    folder_clean = cloud_folder.replace("\\", "/").strip("/")
    filename = os.path.basename(local_path)
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{folder_clean}/{filename}:/content"
    with open(local_path, "rb") as f:
        data = f.read()
    try:
        r = _graph_request_with_retry(
            "PUT", url,
            headers={"Authorization": f"Bearer {t}", "Content-Type": "application/octet-stream"},
            data=data, timeout=UPLOAD_TIMEOUT,
        )
    except Exception:
        log.exception("Upload %s/%s failed after retries", folder_clean, filename)
        return None
    if r.status_code not in (200, 201):
        log.warning("Upload %s/%s returned %d", folder_clean, filename, r.status_code)
        return None
    try:
        return r.json().get("webUrl")
    except Exception:
        return None


def _sp_ensure_folder(drive_id, folder_path, token):
    """Ensure a folder exists in the drive."""
    t = _resolve_token(token)
    parts = folder_path.replace("\\", "/").strip("/").split("/")
    current = ""
    headers = {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}
    for part in parts:
        parent = current if current else None
        if parent:
            url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{parent}:/children"
        else:
            url = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
        body = {"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"}
        _graph_request_with_retry("POST", url, headers=headers, json=body, timeout=TIMEOUT)
        current = f"{current}/{part}" if current else part


def _sp_upload_tree(drive_id, cloud_root, local_dir, token, rel_path=""):
    """Recursively upload a local directory tree.

    Returns (file_count, [webUrl, ...]) where webUrl entries are the
    SharePoint URLs of each uploaded file.
    """
    cloud_root = cloud_root.replace("\\", "/").strip("/")
    uploaded = 0
    urls: list[str] = []
    for name in os.listdir(local_dir):
        local_full = os.path.join(local_dir, name)
        cloud_rel = f"{rel_path}/{name}" if rel_path else name
        if os.path.isdir(local_full):
            folder_cloud = f"{cloud_root}/{cloud_rel}".replace("//", "/").strip("/")
            _sp_ensure_folder(drive_id, folder_cloud, token)
            sub_count, sub_urls = _sp_upload_tree(drive_id, cloud_root, local_full, token, cloud_rel)
            uploaded += sub_count
            urls.extend(sub_urls)
        else:
            parent_cloud = f"{cloud_root}/{rel_path}".replace("//", "/").strip("/") if rel_path else cloud_root
            _sp_ensure_folder(drive_id, parent_cloud, token)
            web_url = _sp_upload_file(drive_id, parent_cloud, local_full, token)
            uploaded += 1
            if web_url:
                urls.append(web_url)
    return uploaded, urls


# ---------------------------------------------------------------------------
# Run log helpers (self-contained CSV append + upload)
# ---------------------------------------------------------------------------
import csv

_LOG_COLUMNS = ["timestamp", "report_name", "status", "duration_sec", "rows_output", "files_uploaded", "args", "error"]


def _now_stamp():
    return _effective_now().strftime("%Y-%m-%d %H:%M:%S")


def _log_ensure_header(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(_LOG_COLUMNS)


def _log_append(path, row):
    _log_ensure_header(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_LOG_COLUMNS, extrasaction="ignore").writerow(row)


def _log_download(drive_id, token, tmp_dir):
    local = os.path.join(tmp_dir, "run_log.csv")
    ok = _sp_download_file(drive_id, RUN_LOG_CLOUD_PATH, local, token)
    if not ok:
        _log_ensure_header(local)
    return local


def _log_upload(drive_id, token, local_path):
    cloud_folder = "/".join(RUN_LOG_CLOUD_PATH.replace("\\", "/").split("/")[:-1])
    try:
        _sp_ensure_folder(drive_id, cloud_folder, token)
        _sp_upload_file(drive_id, cloud_folder, local_path, token)
    except Exception:
        log.warning("Could not upload run_log.csv", exc_info=True)


# ---------------------------------------------------------------------------
# Shabbos / Yom Tov check via Hebcal REST API
# ---------------------------------------------------------------------------
HEBCAL_GEONAMEID = 5110302  # Brooklyn, NY
_hebcal_cache: dict[str, dict] = {}


def _is_melacha_time():
    """Check if melacha is currently assur (Shabbos or Yom Tov).

    Calls the Hebcal API for Brooklyn with 18-min candle lighting.
    Returns (is_assur: bool, reason: str, havdalah_dt: datetime | None).
    The havdalah_dt is the end of the current restricted window (used for
    rescheduling). Fails open: returns (False, "", None) on any error.
    """
    try:
        import requests
        from datetime import datetime, timedelta

        now = _effective_now()
        range_start = (now - timedelta(days=4)).strftime("%Y-%m-%d")
        range_end = (now + timedelta(days=3)).strftime("%Y-%m-%d")

        cache_key = f"{range_start}_{range_end}"
        if cache_key in _hebcal_cache:
            data = _hebcal_cache[cache_key]
        else:
            url = (
                f"https://www.hebcal.com/hebcal?cfg=json&v=1&maj=on&leyning=off"
                f"&c=on&geonameid={HEBCAL_GEONAMEID}&M=on"
                f"&start={range_start}&end={range_end}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            _hebcal_cache[cache_key] = data

        candles = []
        havdalahs = []
        yomtov_dates = {}

        for item in data.get("items", []):
            cat = item.get("category", "")
            if cat == "candles":
                dt = datetime.fromisoformat(item["date"])
                memo = item.get("memo", "")
                candles.append((dt, memo))
            elif cat == "havdalah":
                dt = datetime.fromisoformat(item["date"])
                memo = item.get("memo", "")
                havdalahs.append((dt, memo))
            elif item.get("yomtov"):
                yomtov_dates[item.get("date", "")] = item.get("title", "Yom Tov")

        candles.sort(key=lambda x: x[0])
        havdalahs.sort(key=lambda x: x[0])

        for candle_dt, candle_memo in candles:
            matching_havdalah = None
            for hav_dt, _hav_memo in havdalahs:
                if hav_dt > candle_dt:
                    matching_havdalah = hav_dt
                    break

            if matching_havdalah is None:
                continue

            if candle_dt <= now <= matching_havdalah:
                today_str = now.strftime("%Y-%m-%d")
                if today_str in yomtov_dates:
                    return True, f"Yom Tov: {yomtov_dates[today_str]}", matching_havdalah
                if candle_memo and candle_memo not in ("", now.strftime("%A")):
                    return True, f"Yom Tov: {candle_memo}", matching_havdalah
                return True, "Shabbos", matching_havdalah

        return False, "", None

    except Exception:
        log.warning("Hebcal API check failed; proceeding with report run", exc_info=True)
        return False, "", None


# ---------------------------------------------------------------------------
# Azure Automation reschedule helpers
# ---------------------------------------------------------------------------
AZURE_MGMT_BASE = "https://management.azure.com"
AZURE_API_VERSION_SCHEDULE = "2023-11-01"
RESCHEDULE_BUFFER_MINUTES = 15


def _get_azure_mgmt_token(tenant_id, client_id, client_secret):
    """Acquire a token for the Azure Management API using the same service principal."""
    import msal
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://management.azure.com/.default"])
    if not result or "access_token" not in result:
        raise RuntimeError("Azure Mgmt token error: " + str(result.get("error_description", result)))
    return result["access_token"]


def _reschedule_after_havdalah(
    havdalah_dt, report_name, extra_args,
    tenant_id, client_id, client_secret,
):
    """Create a one-time Azure Automation schedule + job-schedule link to run after havdalah.

    Uses the Azure Management REST API directly (no SDK needed).
    Returns True on success, False on failure (caller should fall back to SKIPPED).
    """
    import requests
    from datetime import timedelta
    import uuid

    sub_id = _get_config("AZURE_SUBSCRIPTION_ID", ["AZURE_SUBSCRIPTION_ID"])
    rg = _get_config("AZURE_RESOURCE_GROUP", ["AZURE_RESOURCE_GROUP"], default="Daily_Invoiced_Report")
    account = _get_config("AZURE_AUTOMATION_ACCOUNT", ["AZURE_AUTOMATION_ACCOUNT"], default="DailyInvoicedReport")
    runbook_name = _get_config("AZURE_RUNBOOK_NAME", ["AZURE_RUNBOOK_NAME"], default="universal_runbook")

    if not sub_id:
        log.warning("AZURE_SUBSCRIPTION_ID not set; cannot reschedule")
        return False

    try:
        mgmt_token = _get_azure_mgmt_token(tenant_id, client_id, client_secret)
    except Exception:
        log.warning("Failed to acquire Azure Management token for reschedule", exc_info=True)
        return False

    run_at = havdalah_dt + timedelta(minutes=RESCHEDULE_BUFFER_MINUTES)
    date_tag = run_at.strftime("%Y%m%d_%H%M")
    schedule_name = f"catchup_{report_name}_{date_tag}"

    headers = {
        "Authorization": f"Bearer {mgmt_token}",
        "Content-Type": "application/json",
    }
    base_path = (
        f"{AZURE_MGMT_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
        f"/providers/Microsoft.Automation/automationAccounts/{account}"
    )

    # 1) Create one-time schedule
    schedule_url = f"{base_path}/schedules/{schedule_name}?api-version={AZURE_API_VERSION_SCHEDULE}"
    schedule_body = {
        "properties": {
            "startTime": run_at.isoformat(),
            "frequency": "OneTime",
            "timeZone": "America/New_York",
            "description": f"Auto-rescheduled {report_name} after Shabbos/Yom Tov",
        }
    }
    r = requests.put(schedule_url, headers=headers, json=schedule_body, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        log.warning("Failed to create schedule '%s': %d %s", schedule_name, r.status_code, r.text[:300])
        return False
    log.info("Created one-time schedule '%s' for %s", schedule_name, run_at.isoformat())

    # 2) Link schedule to runbook with parameters (including --force to bypass re-check)
    force_extra = f"--force {extra_args}".strip() if extra_args else "--force"
    job_schedule_id = str(uuid.uuid4())
    link_url = f"{base_path}/jobSchedules/{job_schedule_id}?api-version={AZURE_API_VERSION_SCHEDULE}"
    link_body = {
        "properties": {
            "schedule": {"name": schedule_name},
            "runbook": {"name": runbook_name},
            "parameters": {
                "report_name": report_name,
                "extra_args": force_extra,
            },
        }
    }
    r2 = requests.put(link_url, headers=headers, json=link_body, timeout=TIMEOUT)
    if r2.status_code not in (200, 201):
        log.warning("Failed to link schedule '%s' to runbook: %d %s", schedule_name, r2.status_code, r2.text[:300])
        return False
    log.info("Linked schedule '%s' to runbook '%s' (report=%s, args=%s)",
             schedule_name, runbook_name, report_name, force_extra)
    return True


def _get_last_success_date(log_path, display_name, merged_args=""):
    """Parse run_log.csv and return the date of the last SUCCESS for a report.

    When *merged_args* is provided, only rows whose "base args" match are
    considered.  Base args are the schedule-identifying arguments with
    date-range flags (``--from``, ``--to``, ``--period``, ``--date``,
    ``--force``) stripped out, so that a catch-up row (which replaces
    ``--period yesterday`` with ``--from/--to``) still matches its original
    schedule variant.  This prevents a nightly all-periods run from
    satisfying the catch-up check for a salesman-yesterday run.

    Returns a date object or None if no prior success found.
    """
    from datetime import date as _date, datetime as _datetime

    _FLAGS_WITH_VALUE = {"--from", "--to", "--period", "--date", "--subfolder"}
    _FLAGS_STANDALONE = {"--force", "--test"}

    def _base_args(raw: str) -> str:
        tokens = raw.split()
        out = []
        skip_next = False
        for t in tokens:
            if skip_next:
                skip_next = False
                continue
            if t in _FLAGS_WITH_VALUE:
                skip_next = True
                continue
            if t in _FLAGS_STANDALONE:
                continue
            out.append(t)
        return " ".join(sorted(out))

    target_base = _base_args(merged_args)
    log.info("[run_log] Looking for last SUCCESS for '%s' with base args '%s'",
             display_name, target_base or "(empty)")
    last = None
    rows_checked = 0
    rows_matched = 0
    skipped_names = 0
    skipped_status = 0
    skipped_args = 0
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows_checked += 1
                if row.get("report_name") != display_name:
                    skipped_names += 1
                    continue
                if row.get("status") != "SUCCESS":
                    skipped_status += 1
                    continue
                row_base = _base_args(row.get("args", ""))
                if row_base != target_base:
                    skipped_args += 1
                    log.debug("[run_log]   Skipped row (args mismatch): date=%s row_base='%s' vs target='%s'",
                              row.get("timestamp", "")[:10], row_base, target_base)
                    continue
                ts = row.get("timestamp", "")
                try:
                    last = _datetime.strptime(ts[:10], "%Y-%m-%d").date()
                    rows_matched += 1
                except (ValueError, IndexError):
                    pass
    except Exception:
        log.warning("[run_log] Could not read run_log.csv", exc_info=True)
    log.info("[run_log] Scanned %d rows: %d name-mismatches, %d non-SUCCESS, "
             "%d args-mismatches, %d matched. Last SUCCESS date: %s",
             rows_checked, skipped_names, skipped_status, skipped_args,
             rows_matched, last.isoformat() if last else "(none)")
    return last


_CATCHUP_THEN_NORMAL = "__catchup_then_normal__"


def _maybe_inject_catchup_args(argv, merged_args, log_path, display_name):
    """If days were missed since last success, widen the date range to cover the gap.

    Period-specific behaviour:

    daily / yesterday
        The run on date X covers X-1 ("yesterday"). When the last success was
        on date L, data for date L itself was never reported as "yesterday".
        So catch_from = L (not L+1), catch_to = yesterday.

    mtd
        Same-month gap: no change (MTD already covers the full month to today).
        Cross-month gap (e.g. skipped on last day of month): inject --from/--to
        for the prior month so it gets finished off.

    ytd
        Same-year gap: no change (YTD already covers the full year to today).
        Cross-year gap (e.g. skipped on last day of year): inject --from/--to
        for the prior year so it gets finished off.

    last_7_days
        Widen the 7-day window by the number of missed days.

    No period (all-periods nightly run)
        Two-pass: first run a catch-up --from/--to for missed days into the
        Daily subfolder, then run the normal all-periods pass so MTD/YTD/
        last_7_days files are also generated.  Returns a sentinel tuple so
        the caller can execute both passes.

    Explicit --from / --to / --date
        No change (user specified exact range).
    """
    from datetime import date as _date, timedelta

    tokens = merged_args.split()

    period_val = None
    if "--period" in tokens:
        try:
            period_val = tokens[tokens.index("--period") + 1]
        except IndexError:
            pass

    log.info("[Catch-up] Checking if catch-up is needed for '%s' (period=%s, args=%s)",
             display_name, period_val or "(all)", merged_args or "(none)")

    if "--from" in tokens or "--to" in tokens or "--date" in tokens:
        log.info("[Catch-up] Explicit date range in args -- no catch-up needed.")
        return argv

    now = _effective_now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    log.info("[Catch-up] Today is %s, yesterday is %s.", today.isoformat(), yesterday.isoformat())

    last_success = _get_last_success_date(log_path, display_name, merged_args)
    if last_success is None:
        log.info("[Catch-up] No previous successful run found in run_log. "
                 "Running regular scheduled %s.", period_val or "all-periods")
        return argv

    gap_days = (today - last_success).days
    log.info("[Catch-up] Previous successful run was %s (%d day(s) ago).",
             last_success.isoformat(), gap_days)

    if gap_days <= 1:
        log.info("[Catch-up] Gap is <= 1 day -- no catch-up needed. "
                 "Running regular scheduled %s.", period_val or "all-periods")
        return argv

    log.info("[Catch-up] Gap is %d days -- catch-up IS needed.", gap_days)

    catch_from = None
    catch_to = None
    subfolder = None

    if period_val is None:
        catch_from = last_success.isoformat()
        catch_to = yesterday.isoformat()
        log.info("[Catch-up] No-period (nightly) run: will do two-pass. "
                 "Pass 1: catch-up daily --from %s --to %s. "
                 "Pass 2: normal all-periods.",
                 catch_from, catch_to)
        return _CATCHUP_THEN_NORMAL, catch_from, catch_to

    elif period_val in ("daily", "yesterday"):
        catch_from = last_success.isoformat()
        catch_to = yesterday.isoformat()
        subfolder = "Daily"
        log.info("[Catch-up] Daily catch-up: expanding to --from %s --to %s "
                 "(covers %d missed day(s) + yesterday).",
                 catch_from, catch_to, gap_days - 1)

    elif period_val == "last_7_days":
        widened_start = today - timedelta(days=6 + gap_days - 1)
        catch_from = widened_start.isoformat()
        catch_to = today.isoformat()
        subfolder = "This Week"
        log.info("[Catch-up] last_7_days catch-up: widening to --from %s --to %s.",
                 catch_from, catch_to)

    elif period_val == "mtd":
        if last_success.month != today.month or last_success.year != today.year:
            catch_from = last_success.replace(day=1).isoformat()
            catch_to = (today.replace(day=1) - timedelta(days=1)).isoformat()
            subfolder = "MTD"
            log.info("[Catch-up] MTD cross-month catch-up: finishing prior month "
                     "--from %s --to %s.", catch_from, catch_to)
        else:
            log.info("[Catch-up] MTD same month -- no catch-up needed. "
                     "Running regular scheduled MTD.")
            return argv

    elif period_val == "ytd":
        if last_success.year != today.year:
            catch_from = last_success.replace(month=1, day=1).isoformat()
            catch_to = _date(last_success.year, 12, 31).isoformat()
            subfolder = "YTD"
            log.info("[Catch-up] YTD cross-year catch-up: finishing prior year "
                     "--from %s --to %s.", catch_from, catch_to)
        else:
            log.info("[Catch-up] YTD same year -- no catch-up needed. "
                     "Running regular scheduled YTD.")
            return argv

    else:
        log.info("[Catch-up] Unknown period '%s' -- no catch-up. "
                 "Running regular scheduled run.", period_val)
        return argv

    if catch_from is None:
        return argv

    new_argv = _strip_period(argv)
    new_argv += ["--from", catch_from, "--to", catch_to]
    if subfolder:
        new_argv += ["--subfolder", subfolder]
    log.info("[Catch-up] Final args for runner: %s", " ".join(new_argv))
    return new_argv


def _strip_period(argv):
    """Remove --period and its value from argv."""
    new_argv = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--period":
            skip_next = True
            continue
        new_argv.append(arg)
    return new_argv


# ---------------------------------------------------------------------------
# Alert helper (standalone -- sends via Graph sendMail)
# ---------------------------------------------------------------------------
def _send_alert(subject, body, tenant_id, client_id, client_secret, from_addr, recipients, content_type="Text"):
    """Best-effort alert email via Graph sendMail.

    ``content_type`` can be ``"Text"`` (default) or ``"HTML"``.
    """
    if not recipients or not from_addr:
        log.warning("ALERT (no email config): %s -- %s", subject, body)
        return
    try:
        import requests
        token = _get_graph_token(tenant_id, client_id, client_secret)
        url = f"{GRAPH_BASE}/users/{from_addr}/sendMail"
        mail = {
            "message": {
                "subject": subject,
                "body": {"contentType": content_type, "content": body},
                "toRecipients": [{"emailAddress": {"address": r}} for r in recipients if r],
            }
        }
        r = requests.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=mail, timeout=TIMEOUT)
        if r.status_code in (200, 202):
            log.info("Alert sent: %s", subject)
        else:
            log.warning("Alert send returned %d: %s", r.status_code, r.text[:200])
    except Exception:
        log.warning("Failed to send alert: %s -- %s", subject, body, exc_info=True)


# ---------------------------------------------------------------------------
# Download required paths for a report
# ---------------------------------------------------------------------------
def _download_required(drive_id, scripts_cloud, scripts_local, required_paths, token):
    base = scripts_cloud.replace("\\", "/").strip("/")
    total = len(required_paths)
    dl_start = time.monotonic()
    for i, rel in enumerate(required_paths):
        rel_norm = rel.replace("\\", "/").strip("/")
        cloud_full = f"{base}/{rel_norm}" if base else rel_norm
        local_full = os.path.join(scripts_local, rel_norm)
        is_file = "." in os.path.basename(rel_norm) and not rel_norm.endswith("/")
        log.info("  Downloading [%d/%d]: %s", i + 1, total, rel_norm)
        if is_file:
            _sp_download_file(drive_id, cloud_full, local_full, token)
        else:
            _sp_download_folder(drive_id, cloud_full, local_full, token)
    log.info("  Download complete: %d paths in %.0fs", total, time.monotonic() - dl_start)


# ---------------------------------------------------------------------------
# Run a single report
# ---------------------------------------------------------------------------
def _execute_runner(entry, argv, display):
    """Import and execute a report runner. Returns (exit_code, error_msg, runner_instance)."""
    runner_module = entry["runner_module"]
    runner_class = entry.get("runner_class")
    runner_type = entry.get("runner_type", "class")
    exit_code = 0
    error_msg = ""
    runner_instance = None

    try:
        log.info("[%s] Importing module: %s", display, runner_module)
        mod = importlib.import_module(runner_module)

        log.info("[%s] Executing runner with args: %s", display, argv or "(none)")
        if runner_type == "class" and runner_class:
            cls = getattr(mod, runner_class)
            runner_instance = cls()
            if hasattr(runner_instance, "defer_salesman_emails"):
                runner_instance.defer_salesman_emails = True
            exit_code = runner_instance.main(argv)
        else:
            main_fn = getattr(mod, "main")
            exit_code = main_fn(argv) or 0

        if exit_code != 0:
            error_msg = f"Runner returned exit code {exit_code}"

    except Exception:
        exit_code = 1
        error_msg = traceback.format_exc()
        log.exception("%s raised an exception", display)

    return exit_code, error_msg, runner_instance


def _upload_incremental(drive_id, token, direct_reports, root_path):
    """Upload any files in direct_reports to SharePoint and clear the local dir.

    Returns (count, [urls]).  Used between period passes so earlier periods
    are safely on SharePoint before the next (bigger) period runs.
    """
    if not os.path.isdir(direct_reports) or not os.listdir(direct_reports):
        return 0, []
    cloud_reports = f"{root_path}/Direct Reports" if root_path else "Direct Reports"
    try:
        count, urls = _sp_upload_tree(drive_id, cloud_reports, direct_reports, token)
        log.info("Incremental upload: %d files to SharePoint", count)
        shutil.rmtree(direct_reports, ignore_errors=True)
        os.makedirs(direct_reports, exist_ok=True)
        return count, urls
    except Exception:
        log.exception("Incremental upload failed (non-fatal, files remain for final upload)")
        return 0, []


def _run_one_report(report_key, entry, extra_args, scripts_local, drive_id, token, alert_ctx,
                    direct_reports="", root_path=""):
    """Run a single report. Returns (exit_code, duration, error_msg, runner_instance_or_None).

    When direct_reports/root_path are provided, performs incremental uploads
    between period passes (for memory-safe multi-period mode). Stores URLs
    of incrementally-uploaded files in ``_incremental_urls`` attribute on the
    returned runner_instance (if any), or logs them for the heartbeat.
    """
    display = entry["display_name"]
    _inc_uploaded_urls: list[str] = []

    default_args = entry.get("default_args", "") or ""
    merged_args = f"{default_args} {extra_args}".strip()
    argv = merged_args.split() if merged_args else []

    log.info("--- Running: %s (key=%s, args=%s) ---", display, report_key, argv or "(none)")

    log.info("[%s] Logging STARTED to run_log.csv...", display)
    log_tmp = tempfile.mkdtemp(prefix="runlog_")
    log_path = _log_download(drive_id, token, log_tmp)
    _log_append(log_path, {"timestamp": _now_stamp(), "report_name": display, "status": "STARTED", "args": merged_args})
    _log_upload(drive_id, token, log_path)

    catchup_result = _maybe_inject_catchup_args(argv, merged_args, log_path, display)

    # Two-pass catch-up: for no-period runs with a gap, run the catch-up
    # daily pass first (missed days), then each period individually to keep
    # memory bounded (each period gets its own fetch + GC cycle).
    do_two_pass = (isinstance(catchup_result, tuple)
                   and len(catchup_result) == 3
                   and catchup_result[0] == _CATCHUP_THEN_NORMAL)

    # Multi-period split: when no --period is specified (nightly all-periods run),
    # run each period as a separate invocation so memory is reclaimed between them.
    # This avoids fetching the entire YTD dataset and holding it in RAM while writing
    # all periods (which exceeds the 400 MB sandbox limit for growing datasets).
    is_no_period_run = (not do_two_pass and "--period" not in merged_args
                        and "--from" not in merged_args and "--to" not in merged_args
                        and "--date" not in merged_args)

    start = time.monotonic()
    exit_code = 0
    error_msg = ""
    runner_instance = None

    if do_two_pass:
        _, catch_from, catch_to = catchup_result

        catchup_argv = list(argv) + ["--from", catch_from, "--to", catch_to, "--subfolder", "Daily"]
        log.info(">>> Running CATCH-UP pass for '%s': --from %s --to %s (subfolder=Daily)",
                 display, catch_from, catch_to)
        code1, err1, inst1 = _execute_runner(entry, catchup_argv, display)
        if code1 != 0:
            log.warning("[%s] Catch-up pass failed (code=%d), continuing with normal run", display, code1)
            _send_alert(
                f"FAILURE: {display} catch-up",
                f"{display} catch-up pass failed (--from {catch_from} --to {catch_to}).\n\nError:\n{err1}",
                **alert_ctx,
            )
        # Upload catch-up files immediately so they're safe
        if direct_reports:
            _cnt, _urls = _upload_incremental(drive_id, token, direct_reports, root_path)
            _inc_uploaded_urls.extend(_urls)
        import gc
        gc.collect()

        # Run each period independently instead of one massive all-periods pass.
        # This keeps peak memory to the single largest period (YTD) rather than
        # loading YTD and holding it while also writing Daily/MTD/Last7.
        _ALL_PERIODS_ORDERED = ["daily", "last_7_days", "mtd", "ytd"]
        log.info(">>> Running REGULAR SCHEDULED periods individually for '%s' (memory-safe mode)",
                 display)
        for period_name in _ALL_PERIODS_ORDERED:
            period_argv = list(argv) + ["--period", period_name]
            log.info(">>> [%s] Period pass: %s", display, period_name)
            code_p, err_p, inst_p = _execute_runner(entry, period_argv, display)
            if inst_p is not None:
                runner_instance = inst_p
            if code_p != 0:
                log.warning("[%s] Period '%s' failed (code=%d): %s",
                            display, period_name, code_p, err_p[:200] if err_p else "")
                if not exit_code:
                    exit_code = code_p
                    error_msg = f"Period '{period_name}' failed: {err_p}"
                _send_alert(
                    f"FAILURE: {display} ({period_name})",
                    f"{display} period '{period_name}' failed.\n\nError:\n{err_p}",
                    **alert_ctx,
                )
            else:
                log.info(">>> [%s] Period '%s' completed successfully", display, period_name)
            # Upload completed period files immediately so they're safe on SP
            if direct_reports:
                _cnt, _urls = _upload_incremental(drive_id, token, direct_reports, root_path)
                _inc_uploaded_urls.extend(_urls)
            # Force garbage collection between periods to reclaim DataFrames
            import gc
            gc.collect()

        merged_args_display = merged_args or ""

    elif is_no_period_run:
        # No catch-up needed but still a nightly all-periods run:
        # split into individual periods for memory safety.
        _ALL_PERIODS_ORDERED = ["daily", "last_7_days", "mtd", "ytd"]
        log.info(">>> Running ALL PERIODS individually for '%s' (memory-safe mode)", display)
        for period_name in _ALL_PERIODS_ORDERED:
            period_argv = list(argv) + ["--period", period_name]
            log.info(">>> [%s] Period pass: %s", display, period_name)
            code_p, err_p, inst_p = _execute_runner(entry, period_argv, display)
            if inst_p is not None:
                runner_instance = inst_p
            if code_p != 0:
                log.warning("[%s] Period '%s' failed (code=%d): %s",
                            display, period_name, code_p, err_p[:200] if err_p else "")
                if not exit_code:
                    exit_code = code_p
                    error_msg = f"Period '{period_name}' failed: {err_p}"
                _send_alert(
                    f"FAILURE: {display} ({period_name})",
                    f"{display} period '{period_name}' failed.\n\nError:\n{err_p}",
                    **alert_ctx,
                )
            else:
                log.info(">>> [%s] Period '%s' completed successfully", display, period_name)
            # Upload completed period files immediately so they're safe on SP
            if direct_reports:
                _cnt, _urls = _upload_incremental(drive_id, token, direct_reports, root_path)
                _inc_uploaded_urls.extend(_urls)
            import gc
            gc.collect()

        merged_args_display = merged_args or ""
    else:
        argv = catchup_result if isinstance(catchup_result, list) else argv
        merged_args_display = " ".join(argv) if argv else merged_args
        is_catchup = (catchup_result is not argv)
        if is_catchup:
            log.info(">>> Running CATCH-UP for '%s': %s", display, merged_args_display)
        else:
            log.info(">>> Running REGULAR SCHEDULED '%s': %s", display, merged_args_display)
        exit_code, error_msg, runner_instance = _execute_runner(entry, argv, display)

    elapsed = time.monotonic() - start

    status = "SUCCESS" if exit_code == 0 else "FAILED"
    log.info("[%s] Complete -- %s in %.0fs", display, status, elapsed)
    try:
        log_path = _log_download(drive_id, token, log_tmp)
    except Exception:
        pass
    _log_append(log_path, {
        "timestamp": _now_stamp(),
        "report_name": display,
        "status": status,
        "duration_sec": f"{elapsed:.0f}",
        "args": merged_args_display,
        "error": error_msg[:500] if error_msg else "",
    })
    _log_upload(drive_id, token, log_path)

    shutil.rmtree(log_tmp, ignore_errors=True)

    if exit_code != 0:
        _send_alert(
            f"FAILURE: {display}",
            f"{display} failed after {elapsed:.0f}s.\n\nArgs: {merged_args_display}\n\nError:\n{error_msg}",
            **alert_ctx,
        )
    elif elapsed > 3600:
        _send_alert(
            f"SLOW: {display} execution ({elapsed:.0f}s)",
            f"{display} took {elapsed:.0f}s (threshold 3600s). Check D365 API or data volume.",
            **alert_ctx,
        )

    log.info("--- %s: %s in %.0fs ---", display, status, elapsed)
    return exit_code, elapsed, error_msg, runner_instance, _inc_uploaded_urls


# ---------------------------------------------------------------------------
# Heartbeat HTML builder
# ---------------------------------------------------------------------------
def _build_heartbeat_html(
    report_name: str,
    extra_args: str,
    report_results: list[str],
    uploaded_urls: list[str],
    overall_elapsed: float,
    overall_exit: int,
) -> str:
    """Build an HTML heartbeat email body."""
    from html import escape
    from urllib.parse import unquote

    status_color = "#2e7d32" if overall_exit == 0 else "#c62828"
    status_label = "SUCCESS" if overall_exit == 0 else "FAILED"

    rows_html = ""
    for line in report_results:
        line = line.strip()
        if not line or line.startswith("Total duration:"):
            continue
        # Hide the "Upload: N files" / "Upload: no output files" rows (noise),
        # but surface "Upload: FAILED" so failures are never silent.
        if line.startswith("Upload:") and "FAILED" not in line:
            continue
        if ":" in line:
            parts = line.split(":", 1)
            name = escape(parts[0].strip())
            detail = escape(parts[1].strip())
            color = "#2e7d32" if "SUCCESS" in detail else "#c62828" if "FAILED" in detail else "#333"
            rows_html += f'<tr><td style="padding:4px 12px 4px 0">{name}</td><td style="padding:4px 0;color:{color}">{detail}</td></tr>\n'

    files_html = ""
    if uploaded_urls:
        files_html = '<h3 style="margin:18px 0 8px 0;color:#1a237e">Files Created</h3>\n<ul style="margin:0;padding-left:20px">\n'
        for url in uploaded_urls:
            display = unquote(url.rsplit("/", 1)[-1]) if "/" in url else url
            files_html += f'<li style="margin:4px 0"><a href="{escape(url)}">{escape(display)}</a></li>\n'
        files_html += "</ul>\n"

    return f"""\
<div style="font-family:Segoe UI,Calibri,Arial,sans-serif;max-width:700px;margin:0 auto">
  <h2 style="margin:0 0 4px 0;color:#1a237e">Runbook Heartbeat</h2>
  <p style="margin:0 0 16px 0;color:#555;font-size:13px">{escape(_now_stamp())}</p>

  <table style="border-collapse:collapse;margin-bottom:16px">
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Overall Status</td>
      <td style="padding:4px 0;font-weight:bold;color:{status_color}">{status_label}</td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Parameters</td>
      <td style="padding:4px 0"><code>report_name={escape(report_name)}</code>{(' &nbsp; <code>' + escape(extra_args) + '</code>') if extra_args else ''}</td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Total Duration</td>
      <td style="padding:4px 0">{overall_elapsed:.0f}s</td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Files Uploaded</td>
      <td style="padding:4px 0">{len(uploaded_urls)}</td>
    </tr>
  </table>

  {'<h3 style="margin:18px 0 8px 0;color:#1a237e">Report Results</h3>' if rows_html else ''}
  {'<table style="border-collapse:collapse">' + rows_html + '</table>' if rows_html else ''}

  {files_html}
</div>"""


# ===========================================================================
# MAIN
# ===========================================================================
def _upload_webapp_pickup(drive_id, token_mgr, direct_reports, record_id, root_path):
    """Upload the first Excel file from Direct Reports to the webapp pickup folder.

    The file is saved as ``webapp_reports/{record_id}.xlsx`` so the webapp
    can download it by record_id after the job completes.
    """
    import glob as _g
    xlsx_files = _g.glob(os.path.join(direct_reports, "**", "*.xlsx"), recursive=True)
    if not xlsx_files:
        log.warning("No .xlsx files found in Direct Reports for webapp pickup")
        return

    src = xlsx_files[0]
    pickup_folder = f"{root_path}/webapp_reports" if root_path else "webapp_reports"
    dest_name = f"{record_id}.xlsx"
    dest_path = f"{pickup_folder}/{dest_name}"

    log.info("Uploading webapp pickup: %s -> %s", os.path.basename(src), dest_path)
    try:
        token = token_mgr()
        import requests
        file_size = os.path.getsize(src)
        if file_size < 4 * 1024 * 1024:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{dest_path}:/content"
            with open(src, "rb") as f:
                resp = requests.put(url, headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                }, data=f, timeout=120)
                resp.raise_for_status()
        else:
            _sp_upload_large(drive_id, dest_path, src, token_mgr)
        log.info("Webapp pickup uploaded successfully: %s", dest_path)
    except Exception:
        log.exception("Failed to upload webapp pickup file")


def _upload_webapp_pickup_from_url(drive_id, token_mgr, uploaded_urls, record_id, root_path):
    """Copy the first uploaded xlsx to the webapp pickup folder using a server-side copy.

    Since we now clear local files after upload, this uses the Graph API to
    copy from the already-uploaded SharePoint file to the pickup location.
    """
    xlsx_urls = [u for u in uploaded_urls if u.lower().endswith(".xlsx")]
    if not xlsx_urls:
        log.warning("No .xlsx URLs in uploaded_urls for webapp pickup")
        return

    pickup_folder = f"{root_path}/webapp_reports" if root_path else "webapp_reports"
    dest_path = f"{pickup_folder}/{record_id}.xlsx"
    source_url = xlsx_urls[0]
    log.info("Webapp pickup (from URL): copying first xlsx to %s", dest_path)

    try:
        import requests
        t = _resolve_token(token_mgr)
        # Download the source file content and re-upload to pickup path
        # (Graph copy API is async and complex; simple download+reupload is reliable)
        source_path = source_url.split("/sites/")[1].split("/", 1)[1] if "/sites/" in source_url else None
        if not source_path:
            log.warning("Could not parse source path from URL: %s", source_url)
            return

        # Use the item download URL directly
        dl_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{source_path}:/content"
        dl_resp = requests.get(dl_url, headers={"Authorization": f"Bearer {t}"}, timeout=UPLOAD_TIMEOUT)
        if dl_resp.status_code != 200:
            log.warning("Webapp pickup download failed: %d", dl_resp.status_code)
            return

        _sp_ensure_folder(drive_id, pickup_folder, token_mgr)
        up_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{dest_path}:/content"
        up_resp = requests.put(up_url, headers={
            "Authorization": f"Bearer {t}",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }, data=dl_resp.content, timeout=UPLOAD_TIMEOUT)
        if up_resp.status_code in (200, 201):
            log.info("Webapp pickup uploaded successfully: %s", dest_path)
        else:
            log.warning("Webapp pickup upload returned %d", up_resp.status_code)
    except Exception:
        log.exception("Failed to upload webapp pickup from URL")


def _classify_guard_action(extra_args):
    """Decide whether to SKIP or RESCHEDULE when melacha is assur.

    Returns ``"skip"`` or ``"reschedule"`` based on the period in *extra_args*.

    Rules:
      - daily / yesterday      -> skip  (catch-up on next regular run)
      - no period (nightly)    -> skip  (catch-up on next regular run)
      - mtd (same month)       -> skip  (MTD self-heals within the month)
      - mtd (last day of month)-> reschedule (month-end run would be lost)
      - ytd (same year)        -> skip  (YTD self-heals within the year)
      - last_7_days / weekly   -> reschedule (window shifts, data would be lost)
      - anything else          -> skip  (safe fallback)
    """
    from datetime import timedelta

    tokens = (extra_args or "").split()
    period_val = None
    if "--period" in tokens:
        try:
            period_val = tokens[tokens.index("--period") + 1]
        except IndexError:
            pass

    if period_val in (None, "daily", "yesterday"):
        return "skip"

    if period_val in ("last_7_days", "this_week"):
        return "reschedule"

    if period_val == "mtd":
        today = _effective_now().date()
        tomorrow = today + timedelta(days=1)
        if tomorrow.month != today.month:
            return "reschedule"
        return "skip"

    if period_val == "ytd":
        today = _effective_now().date()
        tomorrow = today + timedelta(days=1)
        if tomorrow.year != today.year:
            return "reschedule"
        return "skip"

    return "skip"


_KNOWN_REPORT_KEYS = {
    "ordered", "invoiced", "salesman", "number_4", "amazon_weekly",
    "customer_activity", "customer_aging", "all",
}


def _parse_runbook_args():
    """Resolve (report_name, extra_args, webapp_record_id) from any source.

    Sources, in priority order:
      1. Module-level globals (rarely set for Python runbooks, but cheap to check).
      2. Command-line arguments.

         Azure Automation ships params to a Python3 runbook as positional
         argv tokens. Two delivery shapes exist:

         a) Positional schedule params or a single ordered call: the first
            argv token is the report key, everything after it is extra_args
            in its original order, e.g.::

                argv = ['ordered', '--customer', '48999', '917', '2267',
                        '--period', 'daily']

            We must keep that order intact -- argparse needs ``--customer``
            adjacent to its values because the flag uses ``nargs='+'``.

         b) Named schedule/webapp params: Azure sorts by parameter name,
            which puts ``extra_args`` before ``report_name`` ('e' < 'r').
            So argv comes back with the flags first and the report key
            stranded at the end, e.g.::

                argv = ['--email', 'salesman']   # report_name='salesman'
                argv = ['--customer', '48999', 'ordered']  # report_name='ordered'

            We detect this by argv[0] not being a known report key and
            then pick the one token that IS a known key as the name,
            leaving the rest in their original relative order.
      3. Environment variables.
    """
    report_name = ""
    extra_args = ""
    webapp_record_id = ""

    g = globals()
    if "report_name" in g and g["report_name"]:
        report_name = str(g["report_name"]).strip()
    if "extra_args" in g and g["extra_args"]:
        extra_args = str(g["extra_args"]).strip()
    if "webapp_record_id" in g and g["webapp_record_id"]:
        webapp_record_id = str(g["webapp_record_id"]).strip()

    tokens = [
        t.strip().strip('"').strip("'")
        for t in sys.argv[1:]
        if t and t not in ("-h", "--help")
    ]
    tokens = [t for t in tokens if t]

    if tokens and (not report_name or not extra_args):
        first = tokens[0]
        first_key = first.lower().replace("-", "_")
        first_is_known = first_key in _KNOWN_REPORT_KEYS

        if first_is_known:
            # Shape (a): ordered positional delivery.  Trust argv order --
            # never re-sort the tail or argparse nargs='+' flags will break.
            if not report_name:
                report_name = first
            if not extra_args:
                extra_args = " ".join(tokens[1:])
        else:
            # Shape (b): alphabetical-named-param swap.  Azure sorts named
            # params by name ('extra_args' < 'report_name'), so the report
            # key always lands as the LAST known-key token in argv.
            # Scan from the right so values like ``--salesman all`` don't
            # steal the report_name slot when the real report name is
            # ``ordered`` sitting at the end.
            name_idx = None
            for i in range(len(tokens) - 1, -1, -1):
                if tokens[i].lower().replace("-", "_") in _KNOWN_REPORT_KEYS:
                    name_idx = i
                    break
            if name_idx is not None:
                if not report_name:
                    report_name = tokens[name_idx]
                if not extra_args:
                    rest = tokens[:name_idx] + tokens[name_idx + 1:]
                    extra_args = " ".join(rest)
            else:
                # No known key in argv -- treat whole thing as extra_args.
                if not extra_args:
                    extra_args = " ".join(tokens)

    if not report_name:
        report_name = os.environ.get("REPORT_NAME", "").strip()
    if not extra_args:
        extra_args = os.environ.get("EXTRA_ARGS", "").strip()
    if not webapp_record_id:
        webapp_record_id = os.environ.get("WEBAPP_RECORD_ID", "").strip()

    return report_name, extra_args, webapp_record_id


def main():
    _report_name, _extra_args, _webapp_record_id = _parse_runbook_args()
    log.info("Raw sys.argv: %s", sys.argv)
    log.info("Resolved parameters: report_name=%r, extra_args=%r, webapp_record_id=%r",
             _report_name, _extra_args, _webapp_record_id)

    report_name = _report_name
    extra_args = _extra_args
    webapp_record_id = _webapp_record_id

    if not report_name:
        log.error("No report_name parameter provided. Set the 'report_name' Azure Automation parameter or pass as first CLI arg.")
        log.error("Available: ordered, invoiced, salesman, number_4, amazon_weekly, customer_activity, all")
        return 1

    report_name = report_name.strip().lower().replace("-", "_")
    is_test_mode = "--test" in (extra_args or "").split()
    is_force = "--force" in (extra_args or "").split()

    # ---- Simulation mode for testing Shabbos/YT guard ----
    global _SIMULATED_NOW
    _ea_parts = (extra_args or "").split()
    if "--simulate-date" in _ea_parts:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo
        _sim_idx = _ea_parts.index("--simulate-date")
        try:
            _sim_str = _ea_parts[_sim_idx + 1]
            _SIMULATED_NOW = _dt.fromisoformat(_sim_str).replace(
                tzinfo=ZoneInfo("America/New_York"))
            log.info("*** SIMULATION MODE: now = %s ***", _SIMULATED_NOW.isoformat())
        except (IndexError, ValueError) as e:
            log.error("--simulate-date requires YYYY-MM-DDTHH:MM value: %s", e)
            return 1
        extra_args = " ".join(
            p for i, p in enumerate(_ea_parts)
            if i != _sim_idx and i != _sim_idx + 1
        )

    is_simulating = _SIMULATED_NOW is not None

    log.info("=== Universal Runbook: report_name=%s, extra_args=%s, test_mode=%s, webapp_record_id=%s ===",
             report_name, extra_args or "(none)", is_test_mode, webapp_record_id or "(none)")

    # ---- Shabbos / Yom Tov guard ----
    # Uses _classify_guard_action() to decide per-period whether to SKIP
    # (catch-up on next regular run) or RESCHEDULE (create a one-time Azure
    # schedule after havdalah).  See _classify_guard_action() docstring for
    # the full rules table.
    if not is_force:
        log.info("Checking Shabbos/Yom Tov date bypass...")
        is_assur, reason, havdalah_dt = _is_melacha_time()
        if is_assur:
            guard_action = _classify_guard_action(extra_args)
            log.info("Today IS assur b'melacha (%s). Guard action: %s", reason, guard_action)

            _tid = _get_config("GRAPH_TENANT_ID", ["GRAPH_TENANT_ID", "AZURE_TENANT_ID"])
            _cid = _get_config("GRAPH_CLIENT_ID", ["GRAPH_CLIENT_ID", "AZURE_CLIENT_ID"])
            _sec = _get_config("GRAPH_CLIENT_SECRET", ["GRAPH_CLIENT_SECRET", "AZURE_CLIENT_SECRET"])
            _site = _get_config("SP_SITE_URL", ["SP_SITE_URL"])

            rescheduled = False
            if guard_action == "reschedule":
                if is_simulating:
                    log.info("[SIM] Would reschedule after havdalah %s",
                             havdalah_dt.isoformat() if havdalah_dt else "(unknown)")
                elif havdalah_dt and all([_tid, _cid, _sec]):
                    rescheduled = _reschedule_after_havdalah(
                        havdalah_dt, report_name, extra_args or "",
                        _tid, _cid, _sec,
                    )

            status_tag = "RESCHEDULED" if rescheduled else "SKIPPED"
            if rescheduled:
                log.info("=== RESCHEDULED for %s ===", havdalah_dt.isoformat())
            else:
                log.info("=== SKIPPED: %s (action=%s). "
                         "Catch-up will apply on next regular run. ===",
                         reason, guard_action)

            if is_simulating:
                log.info("[SIM] Result: %s | reason=%s | havdalah=%s",
                         status_tag, reason,
                         havdalah_dt.isoformat() if havdalah_dt else "(none)")
                return 0

            try:
                if all([_tid, _cid, _sec, _site]):
                    _tmgr = _TokenManager(_tid, _cid, _sec)
                    _, _did = _sp_resolve_drive(_site, _tmgr)
                    _tmp = tempfile.mkdtemp(prefix="runlog_skip_")
                    _lp = _log_download(_did, _tmgr, _tmp)
                    _log_append(_lp, {
                        "timestamp": _now_stamp(),
                        "report_name": report_name,
                        "status": status_tag,
                        "args": extra_args or "",
                        "error": reason,
                    })
                    _log_upload(_did, _tmgr, _lp)
                    shutil.rmtree(_tmp, ignore_errors=True)
                    log.info("Logged %s to run_log.csv", status_tag)
            except Exception:
                log.warning("Could not log %s to run_log.csv", status_tag, exc_info=True)
            return 0
        else:
            log.info("Today is NOT assur b'melacha. Proceeding with report run.")

    if is_force:
        log.info("--force flag present, bypassing Shabbos/Yom Tov check.")
        extra_args = (extra_args or "").replace("--force", "").strip()

    if is_simulating:
        log.info("[SIM] Melacha is NOT assur at simulated time. Report would RUN normally.")
        log.info("[SIM] Args: %s", extra_args or "(none)")
        return 0

    log.info("[Step 1/7] Loading configuration...")
    tenant_id = _get_config("GRAPH_TENANT_ID", ["GRAPH_TENANT_ID", "AZURE_TENANT_ID"])
    client_id = _get_config("GRAPH_CLIENT_ID", ["GRAPH_CLIENT_ID", "AZURE_CLIENT_ID"])
    client_secret = _get_config("GRAPH_CLIENT_SECRET", ["GRAPH_CLIENT_SECRET", "AZURE_CLIENT_SECRET"])
    site_url = _get_config("SP_SITE_URL", ["SP_SITE_URL"])
    root_path = (_get_config("DriveRootPath", ["DriveRootPath"]) or "D365 F&O").strip().strip("/").replace("\\", "/")
    scripts_cloud = _get_config("SCRIPTS_CLOUD_PATH", ["SCRIPTS_CLOUD_PATH"], default=DEFAULT_SCRIPTS_CLOUD).strip()
    alert_recipients = [r.strip() for r in _get_config("ALERT_RECIPIENTS", ["ALERT_RECIPIENTS"], default="").split(";") if r.strip()]
    alert_from = _get_config("ALERT_EMAIL_FROM", ["ALERT_EMAIL_FROM", "AMAZON_EMAIL_FROM"], default="")

    if not all([tenant_id, client_id, client_secret, site_url]):
        log.error("Missing required config: GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, SP_SITE_URL")
        return 1

    test_email = _get_config("TEST_EMAIL", ["TEST_EMAIL"]) if is_test_mode else ""
    if is_test_mode:
        if test_email:
            alert_recipients = [test_email]
            log.info("[TEST] Overriding alert recipients to TEST_EMAIL: %s", test_email)
        else:
            log.warning("[TEST] --test flag passed but TEST_EMAIL is not configured; "
                        "alerts will go to default recipients")

    alert_ctx = {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "from_addr": alert_from,
        "recipients": alert_recipients,
    }

    log.info("[Step 2/7] Acquiring Graph token and resolving SharePoint drive...")
    try:
        token_mgr = _TokenManager(tenant_id, client_id, client_secret)
        _, drive_id = _sp_resolve_drive(site_url, token_mgr)
    except Exception:
        log.exception("Failed to connect to SharePoint")
        return 1

    # ---- Download registry ----
    temp_root = tempfile.mkdtemp(prefix="universal_rb_")
    scripts_local = os.path.join(temp_root, "scripts")
    os.makedirs(scripts_local, exist_ok=True)

    registry_cloud = f"{scripts_cloud}/{REGISTRY_FILENAME}".replace("\\", "/")
    registry_local = os.path.join(scripts_local, REGISTRY_FILENAME)

    log.info("[Step 3/7] Downloading %s from SharePoint...", REGISTRY_FILENAME)
    if not _sp_download_file(drive_id, registry_cloud, registry_local, token_mgr):
        log.error("Could not download %s from %s. Make sure it exists on SharePoint.", REGISTRY_FILENAME, registry_cloud)
        shutil.rmtree(temp_root, ignore_errors=True)
        return 1

    with open(registry_local, "r", encoding="utf-8") as f:
        registry = json.load(f)

    # ---- Determine which reports to run ----
    if report_name == "all":
        reports_to_run = list(registry.keys())
    else:
        if report_name not in registry:
            log.error("Unknown report '%s'. Available: %s, all", report_name, ", ".join(registry.keys()))
            shutil.rmtree(temp_root, ignore_errors=True)
            return 1
        reports_to_run = [report_name]

    # ---- Collect all required paths across all reports ----
    all_required = set()
    for key in reports_to_run:
        for p in registry[key].get("required_paths", []):
            all_required.add(p)

    log.info("[Step 4/7] Downloading %d required paths for %d report(s)...", len(all_required), len(reports_to_run))
    try:
        _download_required(drive_id, scripts_cloud, scripts_local, sorted(all_required), token_mgr)
    except Exception:
        log.exception("Failed to download scripts from SharePoint")
        shutil.rmtree(temp_root, ignore_errors=True)
        return 1

    # ---- Set up Python path and env vars ----
    if scripts_local not in sys.path:
        sys.path.insert(0, scripts_local)

    d365_root = os.path.dirname(scripts_local)
    direct_reports = os.path.join(d365_root, "Direct Reports")
    os.makedirs(direct_reports, exist_ok=True)

    amazon_recipients = _get_config("AMAZON_EMAIL_RECIPIENTS", ["AMAZON_EMAIL_RECIPIENTS"])
    if is_test_mode and test_email:
        amazon_recipients = test_email
        log.info("[TEST] Overriding AMAZON_EMAIL_RECIPIENTS to TEST_EMAIL: %s", test_email)

    env_pairs = [
        ("D365_ENV_URL", _get_config("D365_ENV_URL", ["D365_ENV_URL"])),
        ("D365_COMPANY_ID", _get_config("D365_COMPANY_ID", ["D365_COMPANY_ID"])),
        ("GRAPH_TENANT_ID", tenant_id),
        ("GRAPH_CLIENT_ID", client_id),
        ("GRAPH_CLIENT_SECRET", client_secret),
        ("SP_SITE_URL", site_url),
        ("DriveRootPath", root_path),
        ("ALERT_RECIPIENTS", ";".join(alert_recipients)),
        ("ALERT_EMAIL_FROM", alert_from),
        ("AMAZON_EMAIL_RECIPIENTS", amazon_recipients),
        ("AMAZON_EMAIL_FROM", _get_config("AMAZON_EMAIL_FROM", ["AMAZON_EMAIL_FROM"])),
        ("SMTP_USER", _get_config("SMTP_USER", ["SMTP_USER"])),
        ("SMTP_PASSWORD", _get_config("SMTP_PASSWORD", ["SMTP_PASSWORD"])),
        ("TEST_EMAIL", _get_config("TEST_EMAIL", ["TEST_EMAIL"])),
    ]
    for key, val in env_pairs:
        if val and key not in os.environ:
            os.environ[key] = val

    if is_test_mode and test_email:
        os.environ["AMAZON_EMAIL_RECIPIENTS"] = test_email
        os.environ["TEST_EMAIL"] = test_email

    overall_start = time.monotonic()
    summary_lines = []
    overall_exit = 0
    total_reports = len(reports_to_run)

    runner_instances = []
    uploaded_urls: list[str] = []
    files_uploaded = 0

    for idx, key in enumerate(reports_to_run):
        entry = registry[key]
        display = entry["display_name"]
        if total_reports > 1:
            log.info("========== Report %d/%d: %s ==========", idx + 1, total_reports, display)
        log.info("[Step 5/7] Running report: %s (args: %s)...", display, extra_args or entry.get("default_args") or "(none)")
        code, elapsed, err, runner_inst, inc_urls = _run_one_report(
            key, entry, extra_args, scripts_local, drive_id, token_mgr, alert_ctx,
            direct_reports=direct_reports, root_path=root_path,
        )
        if runner_inst is not None:
            runner_instances.append(runner_inst)
        # Collect URLs from incremental uploads done within _run_one_report
        if inc_urls:
            uploaded_urls.extend(inc_urls)
            files_uploaded += len(inc_urls)
        status = "SUCCESS" if code == 0 else "FAILED"
        summary_lines.append(f"  {display}: {status} ({elapsed:.0f}s)")
        if code != 0:
            overall_exit = 1

        # Upload immediately after each report so files are safe on SharePoint
        # even if a later report or the YTD pass OOMs the sandbox.
        if os.path.isdir(direct_reports) and os.listdir(direct_reports):
            cloud_reports = f"{root_path}/Direct Reports" if root_path else "Direct Reports"
            log.info("[Step 6/7] Uploading Direct Reports to SharePoint (incremental after %s)...", display)
            log.info("  Target: %s", cloud_reports)
            try:
                count, urls = _sp_upload_tree(drive_id, cloud_reports, direct_reports, token_mgr)
                files_uploaded += count
                uploaded_urls.extend(urls)
                log.info("Uploaded %d files to SharePoint (total so far: %d)", count, files_uploaded)
            except Exception:
                log.exception("SharePoint upload failed after %s", display)
                _send_alert("FAILURE: SharePoint upload", traceback.format_exc(), **alert_ctx)
                summary_lines.append(f"  Upload after {display}: FAILED")
                overall_exit = 1

            # Flush this runner's pending salesman emails BEFORE deleting local
            # files. The deferred-email runners (e.g. Salesman Report) attach
            # by local file path, so the rmtree below would otherwise leave
            # every rep with an empty-attachment email.  Idempotent: if there
            # are no pending emails the call is a no-op.
            if runner_inst is not None and hasattr(runner_inst, "flush_pending_emails"):
                flush_url_map = {}
                for u in uploaded_urls:
                    basename = u.rsplit("/", 1)[-1] if "/" in u else u
                    flush_url_map[unquote(basename)] = u
                try:
                    runner_inst.flush_pending_emails(flush_url_map)
                except Exception:
                    log.exception("flush_pending_emails failed for %s", display)

            # Clear the local output dir so files aren't re-uploaded next iteration
            # and to free disk/memory.
            shutil.rmtree(direct_reports, ignore_errors=True)
            os.makedirs(direct_reports, exist_ok=True)

    if files_uploaded:
        summary_lines.append(f"  Upload: {files_uploaded} files")
    else:
        summary_lines.append("  Upload: no output files")

    # Upload to webapp pickup folder if triggered by the webapp
    if webapp_record_id and uploaded_urls:
        # Re-download the first xlsx from SharePoint for webapp pickup
        # (since we cleared local dir above). Upload the first URL directly.
        _upload_webapp_pickup_from_url(drive_id, token_mgr, uploaded_urls, webapp_record_id, root_path)

    # Flush deferred salesman emails with SharePoint links
    if runner_instances and uploaded_urls:
        url_map = {}
        for u in uploaded_urls:
            basename = u.rsplit("/", 1)[-1] if "/" in u else u
            url_map[unquote(basename)] = u
        for ri in runner_instances:
            if hasattr(ri, "flush_pending_emails"):
                ri.flush_pending_emails(url_map)
    elif runner_instances:
        for ri in runner_instances:
            if hasattr(ri, "flush_pending_emails"):
                ri.flush_pending_emails()

    log.info("[Step 7/7] Sending heartbeat summary...")
    overall_elapsed = time.monotonic() - overall_start

    # Build plain-text log summary
    summary_lines.insert(0, f"Universal Runbook Summary (report_name={report_name})")
    summary_lines.append(f"  Total duration: {overall_elapsed:.0f}s")
    if uploaded_urls:
        summary_lines.append("")
        summary_lines.append("  SharePoint links:")
        for link in uploaded_urls:
            summary_lines.append(f"    {link}")
    summary_text = "\n".join(summary_lines)
    log.info("\n%s", summary_text)

    # Build HTML heartbeat email
    html_body = _build_heartbeat_html(
        report_name=report_name,
        extra_args=extra_args,
        report_results=summary_lines[1:],
        uploaded_urls=uploaded_urls,
        overall_elapsed=overall_elapsed,
        overall_exit=overall_exit,
    )
    heartbeat_prefix = "FAILURE" if overall_exit != 0 else "Runbook Heartbeat"
    _send_alert(
        f"{heartbeat_prefix}: {report_name}",
        html_body,
        **alert_ctx,
        content_type="HTML",
    )

    # ---- Cleanup ----
    shutil.rmtree(temp_root, ignore_errors=True)

    log.info("=== Universal Runbook finished (exit=%d) ===", overall_exit)
    return overall_exit


if __name__ == "__main__":
    sys.exit(main())
