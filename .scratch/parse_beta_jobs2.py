import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")
n = "LogFiles/2026_08_06_lw1mdlwk0001CY_default_docker.log"
with zipfile.ZipFile(zip_path) as z:
    lines = z.read(n).decode("utf-8", errors="replace").splitlines()

# Around ordered/invoiced runs after 14:00
for ln in lines:
    if not re.search(r"T14:", ln):
        continue
    if re.search(
        r"ordered|invoiced|report\.run|job poller claimed|job .*fail|ERROR|Exception|"
        r"result|/api/jobs/|odata_bridge|beta_sources|finished|success|failed",
        ln,
        re.I,
    ):
        # skip azure automation noise
        if "Daily_Invoiced_Report" in ln or "http_logging_policy" in ln:
            continue
        if "heartbeat" in ln:
            continue
        print(ln[:420])
