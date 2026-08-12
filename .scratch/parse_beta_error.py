import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")

with zipfile.ZipFile(zip_path, "r") as z:
    names = sorted(
        n for n in z.namelist()
        if "2026_08_06" in n and "default_docker" in n and n.endswith(".log")
    )
    print("files:", names)
    for n in names[-2:]:
        text = z.read(n).decode("utf-8", errors="replace")
        lines = text.splitlines()
        print(f"\n==== {n} ({len(lines)} lines) ====")
        # Focus after schedule fix deploy ~12:07 UTC
        hits = []
        for i, ln in enumerate(lines):
            if re.search(
                r"Exception on|/beta/reports|BuildError|Traceback|ERROR Exception|ordered|500 ",
                ln,
                re.I,
            ):
                hits.append((i, ln))
        for i, ln in hits[-80:]:
            print(ln[:450])

        # Last full traceback
        start = None
        for i, ln in enumerate(lines):
            if "Traceback (most recent call last)" in ln:
                start = i
        if start is not None:
            print("\n--- last traceback ---")
            for ln in lines[start : start + 55]:
                print(ln[:450])
