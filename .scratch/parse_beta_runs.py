import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")

with zipfile.ZipFile(zip_path, "r") as z:
    n = "LogFiles/2026_08_06_lw1mdlwk0001CY_default_docker.log"
    text = z.read(n).decode("utf-8", errors="replace")
    lines = text.splitlines()
    # Only after schedule-fix deploy (~12:08)
    start_i = 0
    for i, ln in enumerate(lines):
        if "12:08:" in ln or "beta mounted" in ln and "12:0" in ln:
            start_i = i
    chunk = lines[start_i:]
    print(f"scanning {len(chunk)} lines from idx {start_i}")

    pat = re.compile(
        r"Exception|ERROR |Traceback|BuildError| 500 |POST /beta|run |job |odata|failed|Failed",
        re.I,
    )
    hits = [(i, ln) for i, ln in enumerate(chunk) if pat.search(ln)]
    print(f"hits={len(hits)}")
    for i, ln in hits[-120:]:
        print(ln[:450])

    # last traceback after 12:08
    start = None
    for i, ln in enumerate(chunk):
        if "Traceback (most recent call last)" in ln:
            start = i
    if start is not None:
        print("\n--- last traceback after deploy ---")
        for ln in chunk[start : start + 70]:
            print(ln[:450])
    else:
        print("\n(no traceback after deploy window)")

    # Recent POST /api/reports/*/run
    print("\n--- recent run POSTs ---")
    for ln in chunk:
        if "POST /beta/api/reports" in ln or "POST /api/reports" in ln:
            print(ln[:400])
