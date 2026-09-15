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
