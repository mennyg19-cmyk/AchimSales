"""Call Kudu after deploy to enqueue Daily Ordered + Heshy Open Orders."""

from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

APP = "achim-sales-reports"
REMOTE = "python3 tools/enqueue_named_master_schedules.py"


def _profile() -> tuple[str, str]:
    raw = os.environ.get("PUBLISH_PROFILE") or ""
    if not raw.strip():
        raise SystemExit("PUBLISH_PROFILE is empty")
    root = ET.fromstring(raw)
    user = password = ""
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag != "publishProfile":
            continue
        method = (node.get("publishMethod") or "").lower()
        if method not in {"msdeploy", "zipdeploy"}:
            continue
        user = node.get("userName") or user
        password = node.get("userPWD") or password
        if user and password:
            break
    if not user or not password:
        raise SystemExit("publish profile has no SCM user/password")
    return user, password


def main() -> None:
    user, password = _profile()
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    body = json.dumps({"command": REMOTE, "dir": "site/wwwroot"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://{APP}.scm.azurewebsites.net/api/command",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:2000]
        raise SystemExit(f"Kudu {err.code}: {detail}") from err
    stdout = (payload.get("Output") or payload.get("output") or "").strip()
    stderr = (payload.get("Error") or payload.get("error") or "").strip()
    exit_code = payload.get("ExitCode", payload.get("exitCode"))
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    if exit_code not in (0, "0", None):
        raise SystemExit(f"remote exit {exit_code}")


if __name__ == "__main__":
    main()
