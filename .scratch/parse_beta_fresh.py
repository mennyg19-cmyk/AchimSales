import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")
with zipfile.ZipFile(zip_path) as z:
    names = sorted(
        n for n in z.namelist()
        if "default_docker" in n and n.endswith(".log") and "2026_08_06" in n
    )
    print("files:", names)
    # Prefer the main (non-.N) log + newest rotated
    for n in names:
        text = z.read(n).decode("utf-8", errors="replace")
        lines = text.splitlines()
        print(f"\n=== {n} ({len(lines)} lines) ===")
        hits = []
        for ln in lines:
            if re.search(
                r"BuildError|Traceback|Error on request|/beta/|"
                r"Exception|500 |Internal Server|ordered|schedules\.|"
                r"dashboard\.notifications",
                ln,
                re.I,
            ):
                if "Daily_Invoiced_Report" in ln or "http_logging_policy" in ln:
                    continue
                if "heartbeat" in ln:
                    continue
                hits.append(ln)
        # Only show last 80 hits (most recent activity)
        for ln in hits[-80:]:
            print(ln[:450])
