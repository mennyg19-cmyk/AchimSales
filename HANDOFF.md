# Session Handoff

Last updated: 2026-06-18 ~18:20 UTC, by the autonomous session you left running.

## What you asked for

"Run autonomously, I'm going home. Use review agents." The job: do the proper fix
for the stalled v3 job queue -- move `precious.db` off the `/home` SMB share onto
local disk, back up first, cut over, and verify the worker drains the queue.

## What got done (all verified in the running app, not just code)

1. **Root cause (recap):** `precious.db` (v3's users/roles/schedules/jobs) lived on
   `/home`, which is an Azure Files SMB share. SQLite's WAL mode can't share its
   index across processes over SMB, so the background job worker couldn't even
   open the DB -- it failed on every poll with "unable to open database file", so
   no report job ever ran and no call ever reached the Reporting API.

2. **The fix (shipped + live):** the DB now lives on local disk at
   `/tmp/v3data/precious.db` (and `cache.db` likewise). On the first boot after the
   move, `startup.sh` seeded the local DB once from the old `/home` copy using
   SQLite's online-backup, guarded by a one-time marker on `/home`. After that,
   normal cold starts restore the current data from the Litestream Blob replica.

3. **Proof it worked (from the container logs):**
   - `startup: seeded precious.db users=12 jobs=232` -> data came across intact.
   - Litestream snapshotted `/tmp/v3data/precious.db` and is replicating to Blob.
   - The worker poller went from erroring every second to **zero** errors.
   - A later restart (with `/tmp` wiped) correctly **skipped** the seed and
     **restored** the DB from Blob -- the cold-start durability path works, and the
     restored snapshot was the same size, so nothing was lost.
   - Live app (`/`) and v3 (`/test`) both serving; scheduler ticking every minute.

4. **Hardening:** `config.validate()` now refuses to boot in prod if precious/cache
   is ever set back to a `/home` path (the exact gap that let this happen). Tests
   added. Reverted the dead `SQLITE_JOURNAL_MODE` knob (failed interim attempt) and
   removed its app setting.

5. **Commits on branch `cleanup-codebase-sweep` (pushed):**
   - `8dd44ca` Move v3 precious.db off /home SMB to local disk
   - `da69e7c` Refuse to boot v3 in prod with precious/cache on the /home share
   - All 328 v3 tests pass. A `gpt-5.5-extra-high` review of the migration found 3
     issues (partial-seed file, marker durability, an unbound-var fail-open gap) --
     all fixed before deploy.

## Rollback (if anything looks wrong)

The old DB is untouched. To revert: set `PRECIOUS_DB_PATH=/home/site/v3data/precious.db`
and `CACHE_DB_PATH=/home/site/v3data/cache.db` (the app restarts and uses the frozen
`/home` copy). There's also a dated `precious.premigrate.*.db` on `/home`.

## What's next / for you to confirm

- **Run a report through the UI** to watch a job go queued -> running -> done end to
  end. The worker can now open the DB and poll cleanly; this is the final
  human-eyes confirmation that a real job drains. (I can't log in to do this.)
- The Feb/Mar missing data is the DBA's upstream stored procedure, not this app --
  confirmed by you on the phone. Nothing to fix on our side.

## Gotchas for the next session

- On Azure App Service Linux, `/home` is SMB (Azure Files) and `/tmp` is local
  container disk. SQLite must stay on `/tmp` (local); Litestream gives it durability.
- `litestream.yml` reads `${PRECIOUS_DB_PATH}`, so the DB path and its Blob replica
  move together via that one app setting.
- From this machine, direct calls to `*.azurewebsites.net` (Kudu/SCM, the site URL)
  fail DNS, but the `az` CLI works fine (deploy, settings, logs, restart). Use `az`.
- `deploy.ps1` zips the working directory; keep scratch files (tail*.txt, app.zip,
  applogs*) out of the folder or they get bundled (and can lock the zip step).
