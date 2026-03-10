"""
Azure Runbook: Amazon Weekly Report (customer 9300, this week, email + upload).

Azure only has this one file. This runbook downloads only what the Amazon Weekly
report needs from SharePoint (config, core, data, reports/ordered, reports/amazon_weekly,
runbooks/base_runbook), runs the report, then uploads Direct Reports. Other reports
and scripts are not downloaded.

The runbook .py lives under scripts/ in the repo so local runs find reports/, config/, core/.
SharePoint should have D365 F&O/scripts/ with the same structure.
"""

import logging
import os
import shutil
import sys
import tempfile

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
DEFAULT_SCRIPTS_PATH = "D365 F&O/scripts"

# Only what Amazon Weekly needs: config, core, data; reports (ordered + amazon_weekly); runbooks (base_runbook)
REQUIRED_PATHS = [
    "config",                  # config/ folder (paths, settings)
    "core",                    # core/ folder (auth, dates, logging, columns, odata, graph, excel_*, email_report)
    "data",                    # data/ folder (d365_entities, field_maps)
    "reports/__init__.py",
    "reports/ordered",         # reports/ordered/ (builder, writer)
    "reports/amazon_weekly",   # reports/amazon_weekly/ (runner)
    "runbooks/__init__.py",
    "runbooks/base_runbook.py",
]


def _get_config(name, env_keys, default=""):
    try:
        from automationassets import get_automation_variable
        v = get_automation_variable(name)
        if v is not None and str(v).strip():
            return str(v).strip()
    except ImportError:
        pass
    except Exception:
        print(f"[WARN] Failed to read automation variable '{name}'")  # noqa: T201
    for key in env_keys:
        v = os.environ.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def get_graph_token(tenant_id, client_id, client_secret):
    import msal
    authority = "https://login.microsoftonline.com/{}".format(tenant_id)
    app = msal.ConfidentialClientApplication(
        client_id, authority=authority, client_credential=client_secret
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if not result or "access_token" not in result:
        raise RuntimeError("Failed to acquire Graph token: " + str(result.get("error_description", result)))
    return result["access_token"]


def resolve_site_and_drive(site_url, access_token):
    import requests
    from urllib.parse import urlparse
    path = site_url.strip().rstrip("/")
    parsed = urlparse(path)
    hostname = parsed.netloc
    path_part = (parsed.path or "").strip("/")
    if not path_part or path_part.lower() in ("", "sites", "sites/"):
        req_url = GRAPH_BASE + "/sites/root"
    else:
        site_path = "/" + path_part if not path_part.startswith("/") else path_part
        req_url = "{}/sites/{}:{}".format(GRAPH_BASE, hostname, site_path)
    r = requests.get(req_url, headers={"Authorization": "Bearer " + access_token}, timeout=TIMEOUT)
    r.raise_for_status()
    site_id = r.json()["id"]
    dr = requests.get(GRAPH_BASE + "/sites/{}/drive".format(site_id), headers={"Authorization": "Bearer " + access_token}, timeout=TIMEOUT)
    dr.raise_for_status()
    return site_id, dr.json()["id"]


def list_children(drive_id, cloud_path, access_token):
    import requests
    path_clean = cloud_path.replace("\\", "/").strip("/")
    if path_clean:
        url = "{}/drives/{}/root:/{}:/children".format(GRAPH_BASE, drive_id, path_clean)
    else:
        url = "{}/drives/{}/root/children".format(GRAPH_BASE, drive_id)
    r = requests.get(url, headers={"Authorization": "Bearer " + access_token}, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("value", [])


def download_item_content(drive_id, item_id, access_token):
    import requests
    url = "{}/drives/{}/items/{}/content".format(GRAPH_BASE, drive_id, item_id)
    r = requests.get(url, headers={"Authorization": "Bearer " + access_token}, timeout=UPLOAD_TIMEOUT)
    r.raise_for_status()
    return r.content


def download_folder_recursive(drive_id, cloud_path, local_path, access_token):
    """Download a SharePoint folder and all its contents (files and subfolders) to local_path."""
    path_clean = cloud_path.replace("\\", "/").strip("/")
    children = list_children(drive_id, path_clean, access_token)
    if not children:
        log.info("  (empty folder) %s", path_clean)
        return
    os.makedirs(local_path, exist_ok=True)
    for item in children:
        name = item.get("name", "")
        if not name or name.startswith("."):
            continue
        cloud_child = path_clean + "/" + name if path_clean else name
        local_child = os.path.join(local_path, name)
        if "folder" in item:
            download_folder_recursive(drive_id, cloud_child, local_child, access_token)
        elif "file" in item:
            content = download_item_content(drive_id, item["id"], access_token)
            with open(local_child, "wb") as f:
                f.write(content)
            log.info("  Downloaded: %s", cloud_child)


def download_file_by_path(drive_id, cloud_path, local_path, access_token):
    """Download a single file from SharePoint to local_path."""
    import requests
    path_clean = cloud_path.replace("\\", "/").strip("/")
    url = "{}/drives/{}/root:/{}".format(GRAPH_BASE, drive_id, path_clean)
    r = requests.get(url, headers={"Authorization": "Bearer " + access_token}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError("Download failed ({}): {}".format(r.status_code, cloud_path))
    data = r.json()
    if "folder" in data:
        raise RuntimeError("Path is a folder, not a file: {}".format(cloud_path))
    content = download_item_content(drive_id, data["id"], access_token)
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(content)
    log.info("  Downloaded: %s", path_clean)


def download_required_paths(drive_id, scripts_cloud_path, scripts_local, access_token):
    """Download only REQUIRED_PATHS (folders and files) from scripts_cloud_path into scripts_local."""
    base_cloud = scripts_cloud_path.replace("\\", "/").strip("/")
    for rel in REQUIRED_PATHS:
        rel_norm = rel.replace("\\", "/").strip("/")
        cloud_full = base_cloud + "/" + rel_norm if base_cloud else rel_norm
        local_full = os.path.join(scripts_local, rel_norm)
        # .py or other extension = single file; else = folder
        is_file = "." in os.path.basename(rel_norm) and not rel_norm.endswith("/")
        if is_file:
            download_file_by_path(drive_id, cloud_full, local_full, access_token)
        else:
            download_folder_recursive(drive_id, cloud_full, local_full, access_token)


def main():
    log.info("=== Amazon Weekly Runbook: download scripts from SharePoint, run report, upload ===")
    try:
        import requests
    except ImportError:
        log.error("Install required: pip install msal requests")
        return 1

    tenant_id = _get_config("GRAPH_TENANT_ID", ["GRAPH_TENANT_ID", "AZURE_TENANT_ID"])
    client_id = _get_config("GRAPH_CLIENT_ID", ["GRAPH_CLIENT_ID", "AZURE_CLIENT_ID"])
    client_secret = _get_config("GRAPH_CLIENT_SECRET", ["GRAPH_CLIENT_SECRET", "AZURE_CLIENT_SECRET"])
    site_url = _get_config("SP_SITE_URL", ["SP_SITE_URL"])
    root_path = (_get_config("DriveRootPath", ["DriveRootPath"]) or "D365 F&O").strip().strip("/").replace("\\", "/")
    scripts_cloud_path = _get_config("AMAZON_WEEKLY_SCRIPTS_PATH", ["AMAZON_WEEKLY_SCRIPTS_PATH"], default=DEFAULT_SCRIPTS_PATH).strip()

    if not all([tenant_id, client_id, client_secret, site_url]):
        log.error("Missing config: GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, SP_SITE_URL")
        return 1

    temp_root = tempfile.mkdtemp(prefix="amazon_weekly_")
    scripts_local = os.path.join(temp_root, "scripts")

    try:
        log.info("Getting Graph token...")
        token = get_graph_token(tenant_id, client_id, client_secret)
        log.info("Resolving SharePoint drive...")
        _, drive_id = resolve_site_and_drive(site_url, token)

        log.info("Downloading only what Amazon Weekly needs: %s", REQUIRED_PATHS)
        os.makedirs(scripts_local, exist_ok=True)
        download_required_paths(drive_id, scripts_cloud_path, scripts_local, token)
        if not os.path.isdir(os.path.join(scripts_local, "config")) or not os.path.isdir(os.path.join(scripts_local, "reports", "amazon_weekly")):
            log.error("Download failed. Check that %s exists in SharePoint with config/, reports/ordered/, reports/amazon_weekly/, etc.", scripts_cloud_path)
            return 1

        # config.paths expects parent(scripts_dir) = "D365 root", and Direct Reports next to it
        d365_root = os.path.dirname(scripts_local)
        direct_reports = os.path.join(d365_root, "Direct Reports")
        os.makedirs(direct_reports, exist_ok=True)

        if scripts_local not in sys.path:
            sys.path.insert(0, scripts_local)

        for key, val in [
            ("D365_ENV_URL", _get_config("D365_ENV_URL", ["D365_ENV_URL"])),
            ("D365_COMPANY_ID", _get_config("D365_COMPANY_ID", ["D365_COMPANY_ID"])),
            ("GRAPH_TENANT_ID", tenant_id),
            ("GRAPH_CLIENT_ID", client_id),
            ("GRAPH_CLIENT_SECRET", client_secret),
            ("SP_SITE_URL", site_url),
            ("DriveRootPath", root_path),
            ("AMAZON_EMAIL_RECIPIENTS", _get_config("AMAZON_EMAIL_RECIPIENTS", ["AMAZON_EMAIL_RECIPIENTS"])),
            ("AMAZON_EMAIL_FROM", _get_config("AMAZON_EMAIL_FROM", ["AMAZON_EMAIL_FROM"])),
            ("SMTP_USER", _get_config("SMTP_USER", ["SMTP_USER"])),
            ("SMTP_PASSWORD", _get_config("SMTP_PASSWORD", ["SMTP_PASSWORD"])),
        ]:
            if val and key not in os.environ:
                os.environ[key] = val

        log.info("Running Amazon Weekly report (with email)...")
        from reports.amazon_weekly.runner import run
        run(send_email=True)

        log.info("Uploading Direct Reports to SharePoint...")
        from runbooks.base_runbook import _upload_results
        _upload_results()

        log.info("=== Amazon Weekly Runbook completed successfully ===")
        return 0
    except Exception:
        log.exception("Amazon Weekly runbook failed")
        return 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
