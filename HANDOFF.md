# Session Handoff

Last updated: 2026-08-27

**Status:** P0 containment implemented on `cursor/p0-security-containment-adb6`. Single-site cleanup and deletions not started.

## What's done

- Cherry-picked `REPOSITORY-REVIEW.md` + review handoff onto this branch.
- **P0.1** Untracked `.scratch/parity-cookies.env`. Tightened `.gitignore`. Added `tools/check-no-tracked-secrets.sh` (paths only). Values not printed or replayed.
- **P0.2** Azure Production workflow deploys only `webapp-cache`. README Rule Preference updated.
- **P0.3** Scoped OData fails the whole report if any non-empty tab has no salesman column.
- **P0.4** Prod config requires Litestream Azure account/key/container. `startup.sh` refuses prod boot when Litestream is missing or precious.db is absent after restore. `/healthz` liveness; `/readyz` readiness.
- **P0.5** `DEV_BYPASS_AUTH` only works with `APP_ENV=dev` and never on Azure. `create_app` refuses otherwise.

## What's in progress

- Session revoke and git-history purge are **BLOCKED** (need Azure Flask secret rotation + coordinated history rewrite).
- Remaining review security after P0: download-file ownership, precious-repair GET mutations, browser headers.
- No archive tag, deletion inventory, or legacy migration yet.

## What's next

1. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie must leave git history.
2. Archive tag at the final pre-deletion commit.
3. Deletion inventory + approval (`cleanup-protocol.mdc`).
4. Migrate Entra / magic links / user authority / OData into root v3.
5. Prove `/` without `webapp/`, `/test`, `rebuild/`; then unmount and delete approved paths.
6. Remove Beta pill; remaining review gates.

## Open decisions

Unchanged from the repository review (beta bookmarks, leftover legacy features, CLI/runbooks, Run now vs Send now, Shabbos fail-open, commission/name rules).

## Gotchas

- Do not print or replay cookie values. History of `webapp-cache` still contains the old blob until rewritten.
- Do not delete `webapp/` before login/OData are native in v3.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/` while Azure Automation uses them.
- Prod Litestream is now fail-closed. Empty replica + empty local disk will refuse boot instead of serving an empty user DB.
