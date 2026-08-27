# Session Handoff

Last updated: 2026-08-27

**Status:** P0 + review security on `cursor/p0-security-containment-adb6`. Junk cleanup done after tag `archive/pre-cleanup-2026-08-27`. `webapp/` and mounts still required.

## What's done

- P0.1–P0.5 and review security (CSRF, local Feather/Tabulator, authz, customer access, headers, magic links, XSS/Excel).
- Rollback tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- Untracked `.scratch/` (168 files). Deleted `logs/run_log.csv`, `v3/REVIEW-LOG.md`, `rebuild/rebuild-audit/`, `rebuild/proposals/`, `rebuild/BUILD-HISTORY.md`, `rebuild/DEBATE-LOG.md`.

## What's in progress

- Session revoke and git-history purge are **BLOCKED** (Azure Flask secret rotation + history rewrite).
- Single-site migration not started: Entra / magic links / user directory / OData still go through `webapp/`.

## What's next

1. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie must leave git history.
2. Migrate Entra / magic links / user authority / OData into root v3.
3. Prove `/` without `webapp/`, `/test`, `rebuild/`; then unmount and delete those trees.
4. Remove Beta pill; remaining review gates.

## Open decisions

Unchanged from the repository review (beta bookmarks, leftover legacy features, CLI/runbooks, Run now vs Send now, Shabbos fail-open, commission/name rules).

## Gotchas

- Rollback: `git checkout archive/pre-cleanup-2026-08-27`
- Do not print cookie values. History of `webapp-cache` still contains the old blob until rewritten.
- Do not delete `webapp/` before login/OData are native in v3.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/` while Azure Automation uses them.
- Do not add a repo `.semgrepignore`; it replaces Semgrep defaults.
