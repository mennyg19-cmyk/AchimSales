# Session Handoff

Last updated: 2026-09-17 (Flask live; two-way switch checklist)

**Status:** reports.achimonline.com should be the **old Flask** site. FastAPI rebuild is parked, not deleted.

**Switch Flask ↔ FastAPI:** double-click `switch-site.bat` (type `SWITCH` to
confirm) or follow [CUTOVER.md](CUTOVER.md). App Settings are already in Azure.
Do not switch until asked.

## Working tree

- **Production branch:** `main` (this Flask tree, last good Flask commit `4f94afc` plus Azure boot patches)
- **FastAPI saved at:** `cursor/fastapi-rebuild-parked-0a24` / tag `fastapi-rebuild-parked-2026-09-16`
- **Repo:** AchimSales
- **Prod URL:** https://reports.achimonline.com

## What's next (Flask live)

1. After this deploy is green, open https://reports.achimonline.com — should be Flask login, not FastAPI `home13`.
2. If login/People/views look empty: Azure SSH (not Kudu Bash) and restore the Flask home sqlite:

```
printenv BETA_PRECIOUS_DB_PATH
ls -lh "${BETA_PRECIOUS_DB_PATH:-/tmp/betadata/precious.db}" /home/LogFiles/home-precious.db
python3 -c "import os,sqlite3; p=os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db'; os.makedirs(os.path.dirname(p), exist_ok=True); s=sqlite3.connect('file:/home/LogFiles/home-precious.db?mode=ro', uri=True); d=sqlite3.connect(p); s.backup(d); s.close(); d.close(); print('restored', p)"
```

Use `/home/LogFiles/home-precious.db` only if it is much larger than 620K. The 620K `/tmp/v3data` file is `/test`, not home.

3. Do not Restart until that copy exists if Litestream beta replica did not restore.

## Resume FastAPI later

```
git fetch origin
git checkout cursor/fastapi-rebuild-parked-0a24
```

Read that branch's `HANDOFF.md`. To put FastAPI on the public URL, run
CUTOVER.md checklist A (`read-tree` the parked tag onto `main`) — do not
merge the two histories.

## Locked

- REPORTING_API must never be reports.achimonline.com
- P4.I8 salesman vs SalesGroup still BLOCKED on the FastAPI branch
- Leftover Flask PR #35 stays parked (this `main` is Flask from `4f94afc`, not #35)
