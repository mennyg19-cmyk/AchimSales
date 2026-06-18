# Decision Log

## 2026-06-18 Move v3's precious.db off the /home SMB share onto local disk (fix the stalled job queue)
**What I had to decide:** v3 report jobs were getting stuck "queued" forever -- the background worker never picked them up, so no call ever reached the Reporting API (the DBA confirmed he saw zero calls). Root cause: `precious.db` (users, roles, schedules, jobs) lives at `/home/site/v3data/precious.db`, and on Azure App Service `/home` is an Azure Files **SMB share**. SQLite's WAL mode coordinates processes through a shared-memory index (the `-shm` file) that SMB can't share across processes, so the worker process literally couldn't see the rows the web process had written. I needed to get the DB onto local disk (where WAL works across processes) WITHOUT losing the users/roles/schedules already in it, and without taking down the LIVE app that shares the same process.
**Options I considered:** (a) Interim: switch SQLite to a rollback journal (TRUNCATE) so it works over SMB. **Tried it, it broke the app** -- you can't flip a live DB out of WAL without an exclusive lock, every query started failing with "database is locked", HTTP 500s everywhere; reverted immediately. It also would have disabled Litestream (which requires WAL). (b) Proper fix: move `precious.db` + `cache.db` to local disk (`/tmp/v3data/`), seed the local DB once from the current `/home` copy, and keep Litestream replicating it to Blob for durability. (c) Move to Postgres -- too big a change for tonight.
**What I chose:** Option (b). `startup.sh` now does a one-time seed: on the first boot after the move, it copies the current `/home` precious.db to the new local path using SQLite's online-backup (a consistent snapshot even mid-WAL), drops a marker on the persistent `/home` share so it only ever runs once, and also keeps a dated `precious.premigrate.*.db` safety copy on `/home`. After that, normal cold starts restore the CURRENT data from the Litestream Blob replica. `cache.db` is disposable so it just starts empty and rebuilds. App settings `PRECIOUS_DB_PATH`/`CACHE_DB_PATH` point at `/tmp/v3data/...`; the leftover `SQLITE_JOURNAL_MODE` knob (from the failed interim attempt) is removed from both the code and the app settings.
**Why:** Local disk is shared between the gunicorn web workers and the job worker (same container), so WAL's cross-process visibility works and the worker can finally see and run queued jobs. The `/home` file is never modified -- the app just stops pointing at it -- so it stays as a frozen, complete backup. If anything looks wrong after cutover I point `PRECIOUS_DB_PATH` back at `/home` and lose nothing. Litestream still runs in WAL (required) and now replicates the local file. This is the rule-5 design the project always intended; the DB was on `/home` by accident because the default path resolves under the working directory, which is itself on `/home`.
**Status:** DECIDED + VERIFIED. Cutover done at 18:01 UTC: logs show `startup: seeded precious.db users=12 jobs=232` (data intact), Litestream took a fresh snapshot of `/tmp/v3data/precious.db` and is replicating to Blob, and the job worker's poller went from failing on EVERY cycle ("unable to open database file") to zero errors. Confirmed the cold-restart path too: a later container with `/tmp` wiped correctly skipped the one-time seed (marker present) and Litestream RESTORED the DB from Blob (same snapshot size, so data is whole). Also hardened `config.validate()` to refuse to boot in prod if precious/cache ever points back at the `/home` SMB share (the latent gap `_is_unc` missed), with tests. Removed the obsolete `SQLITE_JOURNAL_MODE` app setting. The old `/home/site/v3data/precious.db` was left untouched as a frozen rollback; `startup.sh` also wrote a dated `precious.premigrate.*.db` copy. NOTE: separately, the owner/DBA confirmed the missing Feb/Mar data is an UPSTREAM stored-procedure problem, not this app.

## 2026-06-14 Fetch big v3 reports one month at a time (stop the API timeouts)
**What I had to decide:** How to stop large v3 reports (YTD Ordered, ~488K order lines) from failing. They ask the on-prem Reporting API for a whole year in one request; on a busy on-prem SQL box that single query runs past the 5-minute timeout and returns nothing (all-or-nothing). The owner: "why is this failing so badly? is there a way to chunk the request to make sure it goes through?"
**Options I considered:** (a) raise the timeout (same failure, longer wait, more load on the on-prem box), (b) split the request by date into month-sized pieces, (c) split by customer into batches, (d) bigger on-prem SQL box.
**What I chose:** Option (b). Big date-window pulls of the `salesline_release` stored procedure are now fetched one calendar month at a time and stitched back together. Applied to the three biggest pulls: Ordered (any bounded period), Customer Activity, and the dashboard all-orders refresh. Open-ended/all_time Ordered runs stay a single call (that path relies on the SP's own default window). New `month_chunks()` helper in `report_engine/dates.py`; new `_facts_chunked()` in `web/reporting/report_service.py`.
**Why:** The owner's own evidence ("yesterday returns fine, last month/YTD hangs") points at date/size as the bottleneck. Each month (~40K rows) returns well inside the timeout. No numbers change: each chunk uses the same day boundaries (00:00:00 -> 23:59:59) every daily report already uses, and contiguous months have no gap/overlap, so the stitched result is the same rows as one big call. Verified with a parity test (stitched == single full-window call) + month_chunks coverage tests; all 310 v3 tests pass. Cross-model review found no blockers. Caveat: if the on-prem API is *fully* wedged (every call hanging, the current state), it still needs a restart — chunking can't extract data from a server answering nothing. Raw "Full Data" row order is now grouped month-by-month; totals/numbers identical (logged for sign-off in v3/REVIEW-LOG.md).
**Status:** DECIDED

## 2026-06-11 Retired the legacy test app (test/)
**What I had to decide:** The owner ordered the old v2 sandbox app removed: "get rid of the legacy test app... cancel all jobs for it, wipe it."
**Options I considered:** (a) just unmount it but keep the code, (b) delete the code and its background jobs entirely.
**What I chose:** Full removal. Deleted `test/` (80 files), removed the `/test-legacy` and `/v2` mounts from `wsgi.py`, dropped its pip packages (SQLAlchemy, pyodbc) from requirements, and wiped its data files on the server (`/home/data/v2_app.db`, `/home/data/v2_critical_backup.json`). Its background "mirror refresh" jobs ran inside the web process, so removing the app removes the jobs -- nothing to cancel in Azure.
**Why:** Nobody uses it, and its mirror refresh was hammering the on-prem Reporting API with 13 back-to-back ~150-200K-row pulls (nightly + every 4 hours + after restarts) -- the prime suspect in this week's API hangs, and a contributor to tonight's out-of-memory crash. v3 replaced it. Note: this supersedes the earlier v3-rebuild directive to keep the old test app viewable at /test-legacy. If v3 now fails to boot, /test returns 404 instead of falling back to the old app (the boot error still gets dumped to /home/LogFiles/v3_boot_error.log).
**Status:** DECIDED (owner instruction)

Decisions made during autonomous operation or at ambiguous points during development. See `autonomous-mode.mdc` for the format.

---

<!-- Entries are added below as work progresses. Each entry follows this format:

## [Date] [Short description]
**What I had to decide:** ...
**Options I considered:** ...
**What I chose:** ...
**Why:** ...
**Status:** DECIDED / BLOCKED

-->

## [2026-06-10] CEO Daily Reports email distribution failing since June 3

**What I had to decide:** Why the "CEO Daily Reports" email distribution failed every day since June 3, and how to fix it.

**What I found:** The production database showed every attempt failing with "file not found" for the Ordered and Invoiced report files -- but the files were sitting right there on SharePoint. The app's logs revealed the real error: the Graph API call that looks up the SharePoint *site* was returning 404. The `SP_SITE_URL` setting on the Azure web app pointed to `https://achimonline.sharepoint.com/sites/AchimImportingCoIncTeamSite-D365FO`, a site that does not exist (confirmed by asking Graph directly). The reports actually live on the root site `https://achimonline.sharepoint.com`, under the "D365 F&O" folder in its Documents library. The code swallowed the site-lookup error and reported it as a missing file, which is why the log was misleading. The same wrong-site problem also broke the run_log.csv download the dashboard uses (it had its own hardcoded site name, also wrong) -- which is why Saturday "Shabbos skip" detection failed and the distribution retried in a loop on Saturdays too.

**Options I considered:** (1) Point SP_SITE_URL at the root SharePoint site, matching the local .env that works. (2) Hunt down the "correct" team site URL -- but the file paths all assume the root site's library, so this would need path changes everywhere.

**What I chose:** Option 1: set `SP_SITE_URL=https://achimonline.sharepoint.com` on the Azure web app. Also made two small code fixes: the run_log.csv download now goes through the same shared SharePoint service (instead of its own hardcoded site name), and a dead SP_SITE_URL now raises a clear error naming the setting instead of pretending the file is missing. Added a regression test for that error.

**Why:** Smallest change that restores the working configuration. The local .env already proved the root-site URL resolves every report path correctly.

**Status:** DECIDED
