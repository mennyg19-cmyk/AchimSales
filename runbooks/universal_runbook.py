"""
Universal Azure Automation Runbook.

This single file handles ALL reports. Paste it into Azure Automation once.
Control which report runs via the ``report_name`` and ``extra_args`` parameters.

Flow:
  1. Read Azure Automation Variables (or env vars for local testing)
  2. Acquire Graph token, resolve SharePoint drive
  3. Download report_registry.json from SharePoint
  4. Look up the requested report -> get its required_paths
  5. Download only the required scripts from SharePoint
  6. Log STARTED to run_log.csv on SharePoint
  7. Import and run the report
  8. Log SUCCESS/FAILED to run_log.csv
  9. Upload Direct Reports/ output to SharePoint
 10. Send alert email on failure; heartbeat on success

Azure Automation Parameters:
  report_name (str, required): Key from report_registry.json, e.g. "ordered",
                               "invoiced", "amazon_weekly", or "all" to run every report.
  extra_args  (str, optional): Additional CLI args, e.g. "--period daily".
                               Merged with default_args from the registry.
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
        if not name or name.startswith("."):
            continue
        child_cloud = f"{p}/{name}" if p else name
        child_local = os.path.join(local_path, name)
        if "folder" in item:
            _sp_download_folder(drive_id, child_cloud, child_local, token)
        elif "file" in item:
            content = _sp_download_content(drive_id, item["id"], token)
            with open(child_local, "wb") as f:
                f.write(content)
            log.info("  Downloaded: %s", child_cloud)


def _sp_upload_file(drive_id, cloud_folder, local_path, token):
    """Upload a single file to a SharePoint folder.

    Returns the SharePoint webUrl of the uploaded file, or None on failure.
    """
    import requests
    t = _resolve_token(token)
    folder_clean = cloud_folder.replace("\\", "/").strip("/")
    filename = os.path.basename(local_path)
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{folder_clean}/{filename}:/content"
    with open(local_path, "rb") as f:
        data = f.read()
    r = requests.put(url, headers={"Authorization": f"Bearer {t}", "Content-Type": "application/octet-stream"}, data=data, timeout=UPLOAD_TIMEOUT)
    if r.status_code not in (200, 201):
        log.warning("Upload %s/%s returned %d", folder_clean, filename, r.status_code)
        return None
    try:
        return r.json().get("webUrl")
    except Exception:
        return None


def _sp_ensure_folder(drive_id, folder_path, token):
    """Ensure a folder exists in the drive."""
    import requests
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
        requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
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
    from datetime import datetime, timezone, timedelta
    eastern = timezone(timedelta(hours=-5))
    return datetime.now(tz=eastern).strftime("%Y-%m-%d %H:%M:%S")


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
def _run_one_report(report_key, entry, extra_args, scripts_local, drive_id, token, alert_ctx):
    """Run a single report. Returns (exit_code, duration, error_msg, runner_instance_or_None)."""
    display = entry["display_name"]
    runner_module = entry["runner_module"]
    runner_class = entry.get("runner_class")
    runner_type = entry.get("runner_type", "class")

    default_args = entry.get("default_args", "") or ""
    merged_args = f"{default_args} {extra_args}".strip()
    argv = merged_args.split() if merged_args else []

    log.info("--- Running: %s (key=%s, args=%s) ---", display, report_key, argv or "(none)")

    log.info("[%s] Logging STARTED to run_log.csv...", display)
    log_tmp = tempfile.mkdtemp(prefix="runlog_")
    log_path = _log_download(drive_id, token, log_tmp)
    _log_append(log_path, {"timestamp": _now_stamp(), "report_name": display, "status": "STARTED", "args": merged_args})
    _log_upload(drive_id, token, log_path)

    start = time.monotonic()
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
        "args": merged_args,
        "error": error_msg[:500] if error_msg else "",
    })
    _log_upload(drive_id, token, log_path)

    shutil.rmtree(log_tmp, ignore_errors=True)

    if exit_code != 0:
        _send_alert(
            f"{display} FAILED",
            f"{display} failed after {elapsed:.0f}s.\n\nArgs: {merged_args}\n\nError:\n{error_msg}",
            **alert_ctx,
        )
    elif elapsed > 1800:
        _send_alert(
            f"{display} slow execution",
            f"{display} took {elapsed:.0f}s (threshold 1800s). Check D365 API or data volume.",
            **alert_ctx,
        )

    log.info("--- %s: %s in %.0fs ---", display, status, elapsed)
    return exit_code, elapsed, error_msg, runner_instance


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
        if not line or line.startswith("Upload:") or line.startswith("Total duration:"):
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
def main():
    # ---- Read runbook parameters ----
    # Azure Automation injects runbook parameters as module-level globals.
    # We read them directly to avoid the slow automationassets probe.
    # For local testing, fall back to CLI args or env vars.
    _report_name = ""
    _extra_args = ""

    # 1) Azure Automation injected globals
    g = globals()
    if "report_name" in g and g["report_name"]:
        _report_name = str(g["report_name"]).strip()
    if "extra_args" in g and g["extra_args"]:
        _extra_args = str(g["extra_args"]).strip()

    # 2) CLI override for local testing
    if len(sys.argv) >= 2 and sys.argv[1] not in ("-h", "--help"):
        _report_name = sys.argv[1]
    if len(sys.argv) >= 3:
        _extra_args = " ".join(sys.argv[2:])

    # 3) Env var fallback
    if not _report_name:
        _report_name = os.environ.get("REPORT_NAME", "").strip()
    if not _extra_args:
        _extra_args = os.environ.get("EXTRA_ARGS", "").strip()

    report_name = _report_name
    extra_args = _extra_args

    if not report_name:
        log.error("No report_name parameter provided. Set the 'report_name' Azure Automation parameter or pass as first CLI arg.")
        log.error("Available: ordered, invoiced, salesman, number_4, amazon_weekly, customer_activity, all")
        return 1

    report_name = report_name.strip().lower().replace("-", "_")
    is_test_mode = "--test" in (extra_args or "").split()
    log.info("=== Universal Runbook: report_name=%s, extra_args=%s, test_mode=%s ===",
             report_name, extra_args or "(none)", is_test_mode)

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
    for idx, key in enumerate(reports_to_run):
        entry = registry[key]
        display = entry["display_name"]
        if total_reports > 1:
            log.info("========== Report %d/%d: %s ==========", idx + 1, total_reports, display)
        log.info("[Step 5/7] Running report: %s (args: %s)...", display, extra_args or entry.get("default_args") or "(none)")
        code, elapsed, err, runner_inst = _run_one_report(
            key, entry, extra_args, scripts_local, drive_id, token_mgr, alert_ctx,
        )
        if runner_inst is not None:
            runner_instances.append(runner_inst)
        status = "SUCCESS" if code == 0 else "FAILED"
        summary_lines.append(f"  {display}: {status} ({elapsed:.0f}s)")
        if code != 0:
            overall_exit = 1
    log.info("[Step 6/7] Uploading Direct Reports to SharePoint...")
    files_uploaded = 0
    uploaded_urls: list[str] = []
    if os.path.isdir(direct_reports) and os.listdir(direct_reports):
        cloud_reports = f"{root_path}/Direct Reports" if root_path else "Direct Reports"
        log.info("  Target: %s", cloud_reports)
        try:
            files_uploaded, uploaded_urls = _sp_upload_tree(drive_id, cloud_reports, direct_reports, token_mgr)
            log.info("Uploaded %d files to SharePoint", files_uploaded)
            summary_lines.append(f"  Upload: {files_uploaded} files")
        except Exception:
            log.exception("SharePoint upload failed")
            _send_alert("SharePoint upload FAILED", traceback.format_exc(), **alert_ctx)
            summary_lines.append("  Upload: FAILED")
            overall_exit = 1
    else:
        summary_lines.append("  Upload: no output files")

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
    _send_alert(
        f"Runbook Heartbeat: {report_name}",
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
