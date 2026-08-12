import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")

with zipfile.ZipFile(zip_path, "r") as z:
    for n in sorted(z.namelist()):
        if "2026_08_06" not in n or "default_docker" not in n or not n.endswith(".log"):
            continue
        text = z.read(n).decode("utf-8", errors="replace")
        # Job outcomes / odata / beta sources
        keys = re.compile(
            r"report\.run|job .*fail|job .*error|odata|beta_sources|beta adopted|"
            r"Exception|ERROR web\.|handler|builder|OperationalError|no such|"
            r"/jobs/|result_ref|status.: .fail|ordered",
            re.I,
        )
        print(f"\n######## {n}")
        hits = [ln for ln in text.splitlines() if keys.search(ln)]
        # Prefer afternoon (after 12:07 UTC = after schedule fix)
        afternoon = [ln for ln in hits if re.search(r"T1[2-9]:|T2[0-3]:", ln)]
        for ln in (afternoon or hits)[-80:]:
            print(ln[:420])
