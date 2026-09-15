# Session Handoff

Last updated: 2026-09-15 (dummy home site)

**Status:** Dummy FastAPI home is on branch `cursor/brother-stack-rebuild-0a24`. Cloudflare preview for clicking. No production cutover. No office API.

## Working tree

- **Branch:** `cursor/brother-stack-rebuild-0a24`
- **Repo:** AchimSales
- **Prod URL:** https://reports.achimonline.com (old Flask `v3/` — do not point this rebuild at it)
- **Preview:** Cloudflare tunnel in front of uvicorn `:8080` (dies when the agent VM sleeps)

## What's in the dummy site

Login, all home report cards on mock `data.tabs`, Last Order picker, Settings hub, Users & access, visibility, saved views, Keep/Recent, schedules + Run now → sqlite outbox, xlsx export. Azure `startup.sh` is gunicorn + UvicornWorker `main:app`.

## Locked (do not reopen)

- Stay off AchimSales `main` until Menny says cut over
- PR #35 parked
- Testers = admin until salesman vs SalesGroup map (P4.I8)
- REPORTING_API must never be reports.achimonline.com
- Reviews: Grok/Composer until go-live; Fable/Sol for final whole-app loops only

## What's next

1. Menny clicks the dummy Cloudflare URL
2. If it looks right: new Azure Web App, then DNS
3. Office API key → replace catalog mocks
4. Entra + Graph when secrets exist
