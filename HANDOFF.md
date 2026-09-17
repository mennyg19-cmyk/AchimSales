# Session Handoff

Last updated: 2026-09-17 (FastAPI parked; Flask live; CUTOVER.md)

**Status:** FastAPI rebuild is **paused**, not discarded. Production should run the last Flask site. Resume rebuild from this branch.

**Switch Flask ↔ FastAPI:** double-click `switch-site.bat` (type `SWITCH`) or
follow [CUTOVER.md](CUTOVER.md). Do not merge this history into Flask `main`.
Azure App Settings stay as they are.

## Working tree (resume here)

- **Parked branch:** `cursor/fastapi-rebuild-parked-0a24` (this file)
- **Also at this commit:** `cursor/hotfix-tab-freeze-0a24`
- **Repo:** AchimSales
- **Prod URL while rolled back:** https://reports.achimonline.com (Flask)
- **Do not merge this branch to `main`.** To put FastAPI on the public URL, follow CUTOVER.md checklist A (`git read-tree` this tagged tree onto `main`).

## What's done (FastAPI)

- FastAPI home on `app/` (`main:app`, gunicorn + UvicornWorker)
- Cutover to `main` happened; then hotfixes through `ec0bdba` / later park commit
- Company and master schedule **pages** retired (302 `/schedules`); company **views** stay
- Report column types (money/int/percent/date) + Excel formats
- Customer pills beside the picker (not under the dropdown)
- Tab switch freeze: `fitDataTable` + viewport `height` + `defaultColWidth` + `nestedFieldSeparator: false` (`?v=home13`)
- Import dest `/tmp/homedata/home.sqlite`; Litestream replica blob `home.sqlite` (not Flask `precious.db`)
- Entra AD UPN aliases to `@achimonline.com`; no upsert
- Test mode drops CC/BCC; doorway accepts old API JSON
- P4.I8 salesman vs SalesGroup still **BLOCKED** (testers = admin)

## What's next when you resume

1. Branch from **this** parked branch, not from Flask `main`.
2. Do not treat leftover Flask PR #35 as the rebuild.
3. REPORTING_API must never be reports.achimonline.com.
4. Still not built: P4.I8 salesman map, Customer Aging, Flask companion-xlsx spill for huge B1 sheets.
5. Cutover again: CUTOVER.md checklist A (`read-tree` the newest `fastapi-rebuild-parked-*` tag onto `main`). Then if People is empty:
   `python3 import-precious.py /home/LogFiles/home-precious.db --dest /tmp/homedata/home.sqlite`
   Last line must say `into /tmp/homedata/home.sqlite`. Wait, then Achim User Login.

## Open decisions

- P4.I8 salesman vs SalesGroup
- Semgrep `app/entra.py` Flask XSS on format-string redirect is a known false positive; do not block on it

## Gotchas

- Azure `/tmp` is wiped on Restart. FastAPI sqlite is `/tmp/homedata/home.sqlite`. Flask home sqlite is `BETA_PRECIOUS_DB_PATH` usually `/tmp/betadata/precious.db`.
- FastAPI Litestream path is hardcoded `home.sqlite`. App setting `LITESTREAM_AZURE_PATH` is still Flask `precious.db`. Do not mix the two files.
- Dummy emails are stripped on import. Entra needs an existing People row.
- Cloud Agent `cursor/**` branches do not auto-deploy.
- Last live FastAPI asset bust was `home13`.
