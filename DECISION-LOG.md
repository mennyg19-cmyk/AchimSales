## 2026-09-16 Restore old-site report cell formats
**What I had to decide:** Port v3 report_engine vs stamp a static field→type map and infer the rest.
**Options I considered:** Heuristic-only money in report-grid.js; full engine port; typed `tabs[].columns` plus JS/Excel formatters.
**What I chose:** Hotfix deviation (no Sol/Fable). Keep assemble rows as-is. Add `column_types.py` from the old Column specs (folded aliases like `Fulfillment%` / `Open$`). Grid uses Tabulator money/int/percent/date formatters, salesman color bands, Fulfillment fill, bottomCalc money. Excel uses `$#,##0.00` / `#,##0` / `0.0%` / `YYYY-MM-DD`. Percent values > 1 are already scaled (mock 80 → 80.0%).
**Why:** Menny: previous-site formatting is not applied to the reports. Assemble had been dropping `columns`.
**Status:** DECIDED


## 2026-09-16 Drop master-schedule pages; exclusion dropdown; report pills beside Run report
**What I had to decide:** Hide master pages vs keep a duplicate admin list of user schedules; auto-save exclusions vs keep Save; pills wrap inside the customers column vs sit in the filter row.
**Options I considered:** Leave `/master-schedules` as a privileged alias of `/schedules`; always-visible checkbox wall; keep pills under the selector.
**What I chose:** Hotfix deviation (no Sol/Fable). `/master-schedules` and `/master-schedules/{id}/history` 302 `/schedules` with flash “Master schedules are retired. Use user schedules.” Settings exclusions match the old site: search + scrolling checkbox dropdown, pills for the hidden set, Save still POSTs. Report `#customerPills` is a sibling between `.filter-fields` and `.filter-run-group` so chips fill to Run report then wrap beside the buttons.
**Why:** Menny: master schedules still there; exclusions should be a scrolling dropdown with a filter; selected customer pills under the selector look bad.
**Status:** DECIDED


## 2026-09-16 Test mode drops CC/BCC; old API JSON converted; exclusions from customer_master
**What I had to decide:** Pad missing fields from mock tab schemas vs only intra-row union; keep dummy catalog on Settings when the API is unset.
**Options I considered:** Blank only sibling keys in the same payload; always include mock tab keys as empty; fail test-mode sends that still have CC.
**What I chose:** Hotfix deviation (no Sol/Fable). Test mode To = test emails, CC/BCC empty. Doorway `rows_from_body` accepts `{rows}`, columns+values, OData `value`, and `Table`. Assemble converts that to `data.tabs` and fills unsent fields with `""` from mock keys plus keys seen on other rows. Settings exclusions use `lookups.customers()`. Customer filter card `overflow:visible`.
**Why:** Menny: test mail must not leak CC/BCC; office API still returns old JSON; exclusion list was dummy `catalog.CUSTOMERS`; picker menu was clipped by `.report-controls{overflow:hidden}`.
**Status:** DECIDED


**What I had to decide:** Hide company schedules vs keep them running with the UI off (P9.1).
**Options I considered:** Hide UI but keep clock (old P9.1); convert company rows to personal; drop company-kind from UI, clock, and import.
**What I chose:** `schedules.kind = company` does not show, tick, import, or Run now. Company **views** stay. Existing imported company rows are paused on boot. Settings flag and Company schedules page are gone.
**Why:** Menny: everything is handled through user schedules.
**Status:** DECIDED


## 2026-09-16 Import dest on Azure is /tmp/homedata/home.sqlite
**What I had to decide:** Upsert Menny on Entra callback vs keep People-required and fix the empty sqlite.
**Options I considered:** Upsert on callback; auto-import LogFiles on boot (rejected at go-live); default Kudu import dest to the gunicorn path.
**What I chose:** Hotfix deviation (no Sol/Fable). No upsert. `get_user` matches `lower(email)`. Import without `--dest` on Azure writes `/tmp/homedata/home.sqlite`. Empty-db 403 tells you to import that file. Being in Flask/source precious.db is not the website sqlite.
**Why:** 403 named `mennyg@achimonline.com` — Entra identity is right. Production does not seed People. Kudu has no `APP_DB_PATH`, so import defaulted to `app/data/home.sqlite` while gunicorn reads `/tmp`.
**Status:** DECIDED


## 2026-09-16 Re-enable Litestream so Azure Restart keeps People
**What I had to decide:** Put sqlite on /home vs keep /tmp + restore/replicate; stay on direct gunicorn after the 503.
**Options I considered:** Write sqlite on /home (persists, WAL-unsafe on Azure SMB); leave /tmp with no replica (Restart wipes People); wrap `python -m gunicorn` in Litestream again.
**What I chose:** Hotfix deviation (no Sol/Fable). Keep `/tmp/homedata/home.sqlite`. Restore `-if-replica-exists -if-db-not-exists`, then `litestream replicate -exec` of `python -m gunicorn` with `PYTHONPATH=app/deps`. Blob path stays `home.sqlite`, not Flask `precious.db`. First boot after this deploy is empty until one import; later recycles restore.
**Why:** Azure `/tmp` is the recycle wipe. The 503 was Flask `precious.db` restore + missing `schedule_runs.message`, not replicate wrapping `python -m gunicorn`. Leaving Litestream off made every Restart a re-import.
**Status:** DECIDED


## 2026-09-16 Entra AD UPN maps to @achimonline.com People row
**What I had to decide:** Upsert on Entra callback vs match `user@ad.achimonline.com` to `user@achimonline.com`.
**What I chose:** No upsert. Login aliases AD UPN ↔ mailbox. Session uses the People email. 403 names the Microsoft email.
**Why:** Flask seeded both addresses and upserted on callback. Menny's Achim User Login is the AD account; People has the mailbox. Exact match 403'd.
**Status:** DECIDED



**What I had to decide:** Crash on missing column vs migrate; keep replicating to Flask `precious.db` blob path.
**What I chose:** `init_db` ADD COLUMN `schedule_runs.message`. Replica blob path is `home.sqlite`, not `${LITESTREAM_AZURE_PATH}` (still `precious.db` on live). Log at 12:07: gunicorn bound :8000 then lifespan died. BOOT_B64 still launched Oryx. Re-import after boot; that restore overwrote the Kudu import with an 86KB Flask snapshot.
**Why:** `CREATE TABLE IF NOT EXISTS` does not add columns. Worker exit → 503.
**Status:** DECIDED



**What I had to decide:** Keep `litestream replicate -exec gunicorn` vs boot gunicorn directly.
**What I chose:** Direct `python -m gunicorn`. Leftover `/home/bin/litestream` (Oct 2023) wraps a system python with no packages and exits. CI vendors `app/deps` with Python 3.11 (matches Azure 3.11.2). Re-enable Litestream after the site answers `/healthz`.
**Why:** Portal Running + 503. No pip, no ensurepip, PEP 668, no /opt/python.
**Status:** DECIDED



**What I had to decide:** Push another `main` deploy vs patch startup to `python3 -m gunicorn` / `python3 -m pip`.
**What I chose:** Hotfix deviation (no Sol/Fable). Boot-diag: python `boot ok`, no `gunicorn` binary, leftover `/home/bin/litestream`. `startup.sh` now uses the same interpreter as `python3 -c import main`. Kudu can apply the same two-line change without waiting for git.
**Why:** Portal Running ≠ gunicorn bound. `pip`/`gunicorn` were not on PATH; `|| echo warning` then `exec gunicorn` exited.
**Status:** DECIDED


## 2026-09-16 Cut over FastAPI home to production
**What I had to decide:** Run Sol/Fable production-merge loops first vs merge now; port Flask companion-xlsx OOM spill into FastAPI first.
**Options I considered:** Block merge for premier review; port companion spill; merge immediately as Menny ordered.
**What I chose:** Merge PR #68 to `main` now. Skip Sol/Fable loops (Menny ordered cutover after dummy verify + rollback plan). FastAPI `export_xlsx.py` still builds one in-memory workbook — Flask companion spill from 2026-09-15 is not in this tree; huge B1 Full Data can OOM until that is ported. `v3/` stays deleted; those hotfixes remain in Git history on pre-cutover `main`.
**Why:** Menny said cut over. Rollback is revert `main` + restore `/home/LogFiles/home-precious.db` into `/tmp/betadata/precious.db`. Login stays dead until Kudu import into `/tmp/homedata/home.sqlite`.
**Status:** DECIDED


## 2026-09-16 Strip dummy People before cutover; chrome tables are Tabulator
**What I had to decide:** Delete preview/loop users from the dummy sqlite vs keep preview@ for Cloudflare login; whether Schedule N views are junk.
**Options I considered:** Keep preview@ forever; delete dummy People and fall Achim User Login back to the first live admin; rename Schedule N views.
**What I chose:** Dummy emails (preview@, manager@/salesman@ seeds, @example.com, @local.test, @test.local, loopa-/loopb-) are purged on import and never re-seeded once live People exist. Production never seeds them. Achim User Login uses preview@ if present, else the first active admin. Schedule N views stay — they are live auto-named views from the old site, not dummy rows. Chrome tables (schedules, users, run logs, Last Order, …) use Tabulator with ⋮ sort/filter/hide/freeze/group and nowrap cells. Last run shows Eastern `YYYY-MM-DD HH:MM`. `EMAIL_FROM_ADDRESS` already aliases `EMAIL_FROM`.
**Why:** Menny asked to drop dummy db rows before cutover, asked what Schedule N is, and circled wrapping Actions on the schedules table plus sortable/filterable.
**Status:** DECIDED


## 2026-09-15 Companion OOM: spill + chunk + ungroup
**What you asked for:** Companion build still dying; why rebuild for Excel after screen shape; brother's site works.
**What I had to decide:** One-shot API→Excel rewrite vs keep shared tab builder and harden companion writes.
**What I chose:** Keep shared builder (schedules reuse the same tabs as the viewer). Harden companions: spill huge tabs to temp JSON (largest first), write smallest spill first in ≤100k chunks, force `group=[]` on companions. Failures retrying the whole job is why logs look "twice."
**Why:** B1 dies holding Full Data + By Order + group-key set. Brother's export likely had more free RAM or a smaller period/view. True stream-to-Excel is a separate delivery builder — not this hotfix. (Pickle spill rejected by Semgrep; JSON spill instead.)
**Status:** DECIDED


## 2026-09-15 Oversized tabs → companion xlsx (no merge)
**What you asked for:** Separate file when Full Data is too big, then merge as a new sheet?
**What I had to decide:** Merge companions back into one workbook on the B1 worker vs leave them as sibling files in the same folder.
**What I chose:** Companion `.xlsx` per sheet over 100k rows (largest first, clear rows after each). Main workbook keeps a one-row stub pointing at `…__Full_Data.xlsx`. Uploaded next to the main file; email body lists companions. Do **not** merge on this box — reloading 330k rows into an open multi-sheet book OOMs after By Order.
**Why:** Log died at `sheet Full Data: 331495 rows` after By Order already finished (~4 min). Merge would re-open that memory wall.
**Craft deferral:** Loop C Finding 5 — extract companion block from `export.py` into `export_bundle.py` after go-live (god-file tidy, not a behavior change).
**Status:** DECIDED


## 2026-09-16 precious.db upload lives in Settings → Developer
**What I had to decide:** Keep Copy from live on Settings → People vs move it into Developer.
**Options I considered:** People (next to Users & access); Developer accordion; developer-role-only POST.
**What I chose:** Cut the form from People. Paste it at the top of Developer. POST `/settings/import-precious` stays `_guard_admin` (privileged), so Preview Admin can still import.
**Why:** Menny asked to move the upload to the developer section. Dummy preview login is admin, not a seeded developer.
**Status:** DECIDED


## 2026-09-16 Column filters live in the header ⋮ menu, not search bars
**What I had to decide:** Keep the toolbar Group by dropdown + Tabulator header search inputs vs the old header ⋮ menu (group + Excel-style filter).
**Options I considered:** Leave both; funnel button in the header (old v3); filter form inside the ⋮ menu.
**What I chose:** Drop the Group by `<select>` (grouping stays on Hide / Freeze / Group in the column ⋮). Drop `headerFilter` inputs. ⋮ → Filter this column opens the existing `col-filter-popover` (operator + value). Pills still show active groups.
**Why:** Menny said grouping is already in the column headers and header search bars have to go in favor of filters in the three-dot dropdown. That reverses the dummy shortcut that saved headerFilter as `contains`.
**Status:** DECIDED


## 2026-09-16 Home site reads BETA_PRECIOUS_DB_PATH, not /tmp/v3data
**What I had to decide:** Keep telling Menny to copy `/tmp/v3data/precious.db` vs the home-site env var.
**Options I considered:** Same path as /test; `BETA_PRECIOUS_DB_PATH` (`/tmp/betadata`).
**What I chose:** Home (`is_beta`) uses `BETA_PRECIOUS_DB_PATH`. `/tmp/v3data` is `/test` (`PRECIOUS_DB_PATH`), 620K / 9 views. His SSH screenshot is that file. The 8KB `/home/LogFiles/precious.db` is an empty leftover (wrong case `Logfiles`, or sqlite create). Copy `/tmp/betadata` to `home-precious.db`.
**Why:** Explorer 97 views vs dummy 9 is two different sqlite files on the same box, not a failed importer.
**Status:** DECIDED


## 2026-09-16 Live precious.db is 97 views / 58 schedules, not the 9/13 seed
**What I had to decide:** Treat Menny's explorer list as a request to import JSON `schedules`/`saved_reports` too vs still assemble-only from a fresh live copy.
**Options I considered:** Import every table including JSON and jobs/outbox; assemble-only from the live file; keep using the seed he already uploaded.
**What I chose:** Assemble-only still. Live `/tmp/v3data` is ~97 views, 58 `report_schedules`, 592 layout tabs. JSON `schedules` 44 + `master_schedules` 14 already equal those 58. Flash warns when the upload looks like the 9/13 Azure seed.
**Why:** He pasted the live explorer counts. Dummy 9→9 is the wrong file, not a missed table. Dest cannot keep a JSON `schedules` table — that name is the column table here.
**Status:** DECIDED


## 2026-09-16 Import reads assemble tables only; drop leftover JSON tables
**What I had to decide:** Keep filling dest columns from leftover JSON (`saved_reports` / `company_views` / `master_schedules`) vs follow the old GUI/clock read path and delete those tables here.
**Options I considered:** JSON fill (previous); assemble-only copy; also smash `window_period` onto the shared view.
**What I chose:** Copy `views` + `view_*` + `layout_*` + `report_schedules` + the four schedule children — the tables `assemble_params` / `assemble_layout` and the clock actually read. Keep `window_*` on dest `schedules` and overlay at send time (Daily and Monthly Invoiced share `df-invoiced` with different windows). Drop `saved_reports`, `company_views`, `report_defaults`, `master_schedules`, `view_workbook_parity` on dest. Do not DROP dest `schedules` (that name is JSON on the old file and columns here).
**Why:** Menny said the importer was reading the db wrong and to delete the JSON garbage. Live `live_view_payload` never returns JSON. Two schedules on one view would lose a period if the window were written onto the view.
**Status:** DECIDED


## 2026-09-16 This precious.db is the 13 Azure company seeds, not 45 live rows
**What I had to decide:** Keep hunting in JSON vs tell Menny the file is the seed/freeze; whether paused SharePoint jobs with empty email should show.
**Options I considered:** Treat 13 as success; invent 45; require a new `/tmp/v3data` copy; hide paused rows.
**What I chose:** Flash lists every source table. Personal `schedules` 0 + `master_schedules` 13 means seed/freeze. Overlay JSON onto projected column rows (recipients/owner). Skip dummy `preview@` as schedule owner. Where shows folder when email is empty. Show paused rows.
**Why:** His second upload had 9 column views, 13 column schedules, 2 JSON views, 13 JSON schedules (all already projected). Dummy sqlite after import is the 12 `_AZURE_SCHEDULES` names plus `Ordered Report - amazon`, mostly `is_active=0`, owner `preview@`. The ~45 are not in this file.
**Status:** DECIDED



**What I had to decide:** Trust only `views`/`report_schedules` (9 and 13 in Menny's file) vs also read JSON backups and write them into columns.
**Options I considered:** Tell him to recopy Azure; import JSON blobs onto the new site; read JSON only to fill column/child tables, skip rows already projected (`legacy_id`).
**What I chose:** Column tables first. Then `saved_reports` / `company_views` / `report_defaults` / `schedules` / `master_schedules` become extra column rows. Dest still has no layout_json/params_json. Flash shows both counts.
**Why:** Live GUI still used the JSON tables. The 45 schedules and extra views were never all copied into `report_schedules`/`views` in his download. He does not want blobs stored on the new site.
**Status:** DECIDED


## 2026-09-16 Import every normalized view row and its child tables
**What I had to decide:** Keep assembling view children through the layout dict vs copy `views` / `view_*` / `layout_*` row by row like schedules.
**Options I considered:** Leave the dict round-trip; copy children 1:1; also import JSON `saved_reports`.
**What I chose:** Insert every live `views` row, then copy salesmen/statuses/customers and each layout tab + groups/sorters/columns/filters. Still skip JSON view backups.
**Why:** Menny had a bunch of views on the column tables. The dict path dropped empty tabs and extra statuses.
**Status:** DECIDED


## 2026-09-16 Import normalized schedule children only; skip JSON blobs
**What I had to decide:** Import old JSON `schedules` / `master_schedules` / `saved_reports` as a fallback vs only the later child-table schema; collapse schedules that share view+time vs keep every `report_schedules` row.
**Options I considered:** Dual-path JSON then normalized; JSON only; normalized parent+children one row at a time; keep parent CSV-only on the new site.
**What I chose:** New site has `schedules` plus `schedule_weekdays` / `schedule_monthdays` / `schedule_recipients` / `schedule_email_salesmen` like live 0021 (integer PKs, no `email_html` blob). Import each `report_schedules` row, then copy those four children by source id. Skip `saved_reports`, `company_views`, `schedules`, `master_schedules`. Admins/devs see every row (Owner + Name). Weekdays stay 0=Mon.
**Why:** Menny had ~45 named schedules on the child tables. The JSON tables are leftover backups. Upsert-by-view-and-time dropped extras and left Where empty because recipients live on `schedule_recipients`.
**Status:** DECIDED


## 2026-09-16 Import wipes dummy views/schedules and copies JSON plus normalized
**What I had to decide:** Keep matching-name upsert (dummy leftovers stay) vs wipe then copy everything; skip personal views when owner_handle does not map vs assign a fallback owner.
**Options I considered:** Upsert-only; wipe views/schedules then import normalized only; wipe then import normalized and old JSON blobs; skip unknown report keys.
**What I chose:** Wipe dummy views and schedules first. Copy normalized tables and leftover JSON `saved_reports` / `company_views` / `schedules`. Map owner handles case-insensitively; if a handle is missing, put the view on a fallback admin instead of dropping it. People rows still stay (existing emails are not deleted).
**Why:** Menny imported on the dummy and still saw seed LoopA/Daily views; live personal views and schedules did not come over.
**Status:** DECIDED


## 2026-09-16 Drop Azure Automation; import views and schedules from precious.db
**What I had to decide:** Delete the OData Automation CLI now vs leave it until Azure jobs are turned off in the portal; whether precious.db import stays People-only.
**Options I considered:** Keep run.py until Menny disables the Automation account; delete the tree and tell him to stop the Azure jobs; import JSON blobs vs normalized views tables.
**What I chose:** Remove `run.py`, `runbooks/`, `reports/`, and the OData CLI. Nightly work is the in-app schedules. Import copies People, views (normalized columns or old JSON), and schedules. Settings upload plus CLI. Existing emails stay. Matching company view names get the live layout.
**Why:** Menny said get rid of the Azure Automation job and needs a way to move precious.db into the new site.
**Status:** DECIDED


## 2026-09-16 Strip Flask home from this PR
**What I had to decide:** Delete `v3/` / `webapp/` / `rebuild/` now so merge cannot boot Flask, vs leave them until after live FastAPI works; whether Azure Automation OData (`run.py`, `reports/`, `runbooks/`) counts as “old site.”
**Options I considered:** Dual-stack until cutover; FastAPI-only home, keep Automation; delete Automation too.
**What I chose:** Remove the Flask websites and point repo-root `startup.sh` at FastAPI. Keep Azure Automation CLI. GitHub history on `main` is the backup. Still do not merge until Menny says cut over.
**Why:** Menny expected this PR to be the new site with no old-site remnant. Azure already runs `bash startup.sh`; leaving Flask there is why merge would have opened the old site.
**Status:** DECIDED


## 2026-09-16 Go-live slice: chips, Graph drive, catch-up, Litestream, People import
**What I had to decide:** Which remaining cutover gaps to build in-app vs leave for Menny (Azure create, DNS, P4.I8, secrets); whether production Litestream is fail-open like live startup.sh or fail-closed at boot; whether People import copies views/schedules.
**Options I considered:** Port every v3 overlay window and email HTML sanitizer; skip drive until Azure; require Graph at production boot; auto-import precious.db on startup.
**What I chose:** Build chips, Graph SharePoint/OneDrive upload (stdlib, chunked >4MB, mock in preview, fail-closed in production), Shabbos catch-up (skip vs reschedule, Monday makeup, one overlay window), fcntl clock lock, Keep cap 5 / 30 days, theme on `users`, `FLASK_SECRET` alias, Litestream wrap in `app/startup.sh` plus production boot refuse without the Azure key (download/restore still fail-open), opt-in `import_precious.py` for People only. Skip Customer Aging, salesman map, Azure create, DNS, Fable/Sol.
**Why:** Menny said finish everything that can be built in-app. Secrets, DNS, and P4.I8 still need him. Views/schedules stay behind on import because the schema is columns, not v3 JSON.
**Status:** DECIDED


## 2026-09-16 Views as columns; grid layout saved with the view
**What I had to decide:** Persist Tabulator hide/freeze/order/sort/group/header filters as JSON on views vs the rebuilt column tables; keep explorer JSON editor; port tab clones / TEXT handles / dual-write Excel parity.
**Options I considered:** Dual-write `params_json` plus columns; columns only; skip grid persist and only keep filter scalars.
**What I chose:** Columns only (`views` scalars + `view_*` + `layout_*`). Save this view writes filters and layout. Schedules keep pointing at `view_id` and Excel/email apply that layout (hide/order/sort/header filters). Group/freeze stay viewer-side for the grid; Excel stays a flat sheet. Integer PKs (skip TEXT handles). Skip tab clones, dual-write JSON workbooks, and the Excel funnel popover (headerFilter input is saved as `contains`). Explorer JSON blob editor is gone.
**Why:** Menny asked for the excel-feel tables saved on views the way they are today, without JSON blobs, and without every bolted-on extra that made the old app clunky.
**Status:** DECIDED



**What I had to decide:** Ship Graph/clock/Hebcal/Entra now vs keep honest stubs until secrets exist; Hebcal-down fail-open (live v3) vs hold (rebuild Q5); Entra upsert (live v3) vs People-row required (Q8).
**Options I considered:** Stubs until cutover; code paths on, secrets optional; refuse to boot production without Graph/Entra.
**What I chose:** Wire the real paths. No secrets → sqlite outbox, preview Achim login, External shortcut. Secrets set → Graph sendMail (stdlib urllib), Entra auth-code, magic-link email. Clock is a 60s daemon thread (off under pytest / `DISABLE_SCHEDULE_CLOCK`). Hebcal missing → hold, do not send, retry next minute (Q5). Shabbos/Yom Tov → skipped + last_run so due_now will not retry every minute. Entra callback never upserts. SharePoint/OneDrive upload stays unwired. Same PR, no cutover.
**Why:** Menny asked why those were missing and to add them. Secrets cannot be invented; fail-closed means no fake success.
**Status:** DECIDED


## 2026-09-15 Loop C craft: shared cell, dev routes, salesman tabs, sidecar errors
**What I had to decide:** Fix all five quality findings vs DECIDED-defer any; put the doorway proxy in `routes_reports.py` vs a new `routes_dev.py`.
**Options I considered:** Move only `/api/dev/reporting/{id}/run` (admin would stay over 500); new `routes_dev.py` for explorer + diagnostics + proxy; leave `_cell` duplicated with a comment.
**What I chose:** One `catalog.cell` (lookups pass `strip=True`). Developer tools (explorer, diagnostics, doorway proxy) live in `routes_dev.py`. Mock salesman tabs use `yoy`/`ytd` like the thin assembler. Last Order invoiced sidecar stores `recent_error` and the view shows it; the page still 200s. Invalid JSON on the proxy is 400. `test_home.py` split stays deferred.
**Why:** Loop C F1–F5. Admin was 563 lines with mixed concerns; moving the proxy alone would not get under 500.
**Status:** DECIDED


## 2026-09-15 Live office Reporting API behind the dummy site
**What I had to decide:** Call the office doorway for every report now vs keep catalog JSON until Menny pastes the key; fallback vs fail when the SP errors.
**Options I considered:** Always mock; live when KEY is set else mock; silent mock fallback after a live 502.
**What I chose:** Default BASE is the West US 3 test doorway. No KEY → catalog mock + banner (Cloudflare stays clickable). KEY set → live `POST /api/reports/{id}/run`. Thin tabs from `{rows}` (or pass through `data.tabs`). Number 4 = two SPs; Sales by State = three. Last Order uses `customer_last_orders`. Doorway errors are 502 (schedules mark failure), not silent mock. Tests mock `doorway.run_report` / urllib. Entra/Graph still stubs. No production cutover.
**Why:** Menny asked for the API hooked up on a full-featured site. The key is still not in this VM.
**Status:** DECIDED


## 2026-09-15 Loop C leftover file splits deferred
**What I had to decide:** Split `test_home.py` (752 lines) and `routes_admin.py` (467, mixed settings/People/dev) now vs after dummy click-through.
**Options I considered:** Split both this commit; split tests only; leave until a refactor command.
**What I chose:** Leave both. `routes_admin.py` is under 500 lines. Dummy tests stay one file. Report-card and SalesGroup markup are already de-duped with Jinja macros.
**Why:** Ponytail vs Loop C finding 7. Protocol-safe for ACL already landed; splitting files now risks a dummy-preview regression without a new behavior.
**Status:** DECIDED


**What I had to decide:** Build remaining inventory on mock JSON vs wait for the office API key; where testers try it.
**Options I considered:** Slice 2 doorway first; dummy full site on the existing Cloudflare tunnel; stand up a new Azure Web App now.
**What I chose:** Finish the dummy home (all report cards, Last Order, Settings/People, views, Keep/Recent, schedules, xlsx, mock outbox) on the Cloudflare preview. Keep Azure zip/startup as-is for a *new* Web App. Do not create or bind Azure until Menny says cut over.
**Why:** Menny wants to click the dummy site first, then switch.
**Status:** DECIDED

## 2026-09-15 Review models during dummy rebuild
**What I had to decide:** `review-protocol.mdc` routine loops are Terra+Sonnet; go-live is Sol+Fable. Menny asked for cheaper models (Grok/Composer) and no Fable/Sol until the whole app is done.
**Options I considered:** Follow protocol slugs; follow Menny’s override; mix Terra with Grok.
**What I chose:** Dummy/phase reviews = Grok + Composer (cheap, two families). Fable/Sol only for the final whole-app loops after the dummy site is clickable. Logged in README Rule Preferences.
**Why:** User override. Cutover still gets premier loops.
**Status:** DECIDED

## 2026-09-15 Hebcal / Graph / Entra stay stubs on dummy
**What I had to decide:** Fake Shabbos skip and fake Entra vs honest stubs.
**What I chose:** Clock does not skip (no Hebcal file). Mail writes sqlite outbox, not Graph. Achim User Login is preview admin. Magic link signs in an active External People row in preview only. Live doorway still off until REPORTING_API_KEY.
**Why:** Secrets are not in this VM. Dummy must be clickable without them.
**Status:** DECIDED

## 2026-09-15 Brother-stack rebuild started (this prompt wins)
**What I had to decide:** New FastAPI home vs continue leftover Flask PR #35; grill/architecture debate vs locked handoff.
**Options I considered:** Stack on `cursor/pr1-on-main-551b`; new `app/` folder on a new branch; new GitHub repo.
**What I chose:** New branch `cursor/brother-stack-rebuild-0a24`, new `app/` FastAPI app. PR #35 stays parked. Grill skipped. Architecture already locked (FastAPI + JSON + v3 look + Tabulator). Q1–Q11 copied from `app/BROTHER-STACK-REBUILD.md` (fraction commission; per-invoice rate zero stays zero; display master percent; Ordered Summary by CustomerAccount; Hebcal hold; legacy distributions retired; `/beta` 302; no self-register; view-only managers Send now on shared only; 90-day prune; 45 min kill, Graph unknown not auto-retry).
**Why:** Job prompt + handoff. Visual = live v3. Do not deploy over reports.achimonline.com until sign-off.
**Status:** DECIDED

Older entries: DECISION-LOG-ARCHIVE.md
