import zipfile
import re
from pathlib import Path

zip_path = Path(r"D:\Projects\Achim\AchimSales\.scratch\azure-logs.zip")
with zipfile.ZipFile(zip_path) as z:
    text = z.read("LogFiles/2026_08_06_lw1mdlwk0001CY_default_docker.log").decode("utf-8", errors="replace")

# After schedule fix deploy (~14:20+), any 500 or BuildError?
for ln in text.splitlines():
    if not re.search(r"T14:(2[0-9]|3[0-9]|4[0-9]|5[0-9])", ln):
        continue
    if re.search(r" 500 |BuildError|Exception on|Traceback|Error on request", ln):
        print(ln[:400])

print("--- beta page/report status after 14:20 ---")
for ln in text.splitlines():
    if not re.search(r"T14:(2[0-9]|3[0-9]|4[0-9]|5[0-9])", ln):
        continue
    if re.search(r'"GET /beta/reports/|"POST /beta/api/reports/.*/run|"GET /beta/ HTTP', ln):
        print(ln[:350])
