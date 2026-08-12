import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")
out = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs-py")
out.mkdir(parents=True, exist_ok=True)

interesting = []
with zipfile.ZipFile(zip_path, "r") as z:
    names = z.namelist()
    print(f"entries: {len(names)}")
    # Prefer LogFiles docker / http
    candidates = [
        n for n in names
        if "LogFiles" in n.replace("\\", "/")
        and n.endswith((".log", ".txt"))
        and ("docker" in n.lower() or "http" in n.lower() or "application" in n.lower() or "default" in n.lower())
    ]
    print(f"candidate logs: {len(candidates)}")
    for n in sorted(candidates)[-15:]:
        print(" ", n)

    pat = re.compile(
        r"Traceback|beta_live|adopt_live|no such table|Error on request|/beta|Internal Server|Exception|Werkzeug",
        re.I,
    )
    # Read the newest-looking docker logs (by name date if present)
    for n in sorted(candidates)[-8:]:
        try:
            raw = z.read(n)
        except Exception as e:
            print("read fail", n, e)
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
        hits = [ln for ln in text.splitlines() if pat.search(ln)]
        if not hits:
            continue
        print(f"\n==== {n} hits={len(hits)} ====")
        for ln in hits[-60:]:
            print(ln[:400])
            interesting.append(ln)

# Also dump last 80 lines of the most recent *docker*.log
dockerish = [n for n in names if "docker" in n.lower() and n.endswith(".log")]
if dockerish:
    newest = sorted(dockerish)[-1]
    print(f"\n==== TAIL {newest} ====")
    text = z.read(newest).decode("utf-8", errors="replace").splitlines()
    for ln in text[-80:]:
        print(ln[:400])
