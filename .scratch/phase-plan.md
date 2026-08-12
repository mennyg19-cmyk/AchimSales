# Phase plan — Beta additions

protocol: feature
grill: .scratch/grill-notes-beta-additions.md
branch: cursor/beta-live-page-694b

## Todos
1. Ordered default_group on OData bridge (map sheet → default_group)
2. Resume TTL 48h + Keep 30d (cap 5) — API + UI + cache prune
3. Salesman color bands — Tabulator formatters + streaming Excel fonts
4. Filename template tokens + schedules GUI + resolve at delivery
5. Last Order Export popup → Excel + PDF
6. Tests for token resolve, Keep cap, Ordered OData defaults
7. Commit + push (user asked)

## EXPECTED (observable)
- [x] Ordered Summary/By Customer/By Order grouped by Salesman on load — OData bridge + existing SQL default_group; viewer already applies
- [x] Active/resume lists finished runs for 48h — `_RECENT_DONE_SECONDS = 48h`
- [x] Keep extends a run to 30d; max 5 kept — `POST .../keep` + `jobs.kept_until`
- [x] Salesman screen + xlsx show blue/green/purple/red bands — report.ts formatters + streaming export fonts
- [x] Schedule filename field has token chips + live preview — personal modal + master wizard
- [x] Last Order Export → choose Excel or PDF → file downloads — export route + popup

Committed: `fd35b21` on `cursor/beta-live-page-694b` (pushed). Deploy with `deploy.ps1` when ready.
