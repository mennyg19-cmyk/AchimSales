## 2026-09-16 Roll production back to Flask; FastAPI parked
**What I had to decide:** Azure Deployment Center redeploy vs put the last Flask tree on `main`.
**Options I considered:** Redeploy only (next `main` push would ship FastAPI again); `reset --hard` + force-push; new commit whose tree is Flask `4f94afc`.
**What I chose:** FastAPI stays on `cursor/fastapi-rebuild-parked-0a24` (tag `fastapi-rebuild-parked-2026-09-16`). `main` gets Flask `4f94afc` plus vendored `webapp` deps and `python3 -m gunicorn` so Azure can boot without pip. Home sqlite is still `BETA_PRECIOUS_DB_PATH` (`/tmp/betadata/precious.db`). If restore is empty, copy `/home/LogFiles/home-precious.db` onto that path.
**Why:** Menny: rebuild did not finish on time; reset to Flask; save FastAPI for later.
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
