# Session Handoff

Last updated: 2026-08-27

**Status:** P0 + review security on `cursor/p0-security-containment-adb6`. CI green on `954845b`. Deletion inventory written; no deletes.

## What's done

- Cherry-picked `REPOSITORY-REVIEW.md` + review handoff onto this branch.
- **P0.1–P0.5** (cookies untracked, no cursor Production deploys, OData fail-closed, Litestream readiness, no prod DEV_BYPASS_AUTH).
- Review follow-up: download-file owner check, precious-repair GET-only check, security headers, magic-link claim/throttle/fixed origin, history XSS, notif-diag escape, shared Excel formula prefix.
- Session/DB authz, customer access fail-closed, leftover XSS, Ordered/Invoiced formula prefix.
- Legacy CSRF (`{% csrf_token %}` + `nosemgrep` on Django form rule). Feather + v3 Tabulator 6.3.1 local. CSP drops unpkg/jsdelivr. Google Maps stays on Google.
- `DELETION-INVENTORY.md` — candidates only; nothing untracked or deleted.

## What's in progress

- Session revoke and git-history purge are **BLOCKED** (need Azure Flask secret rotation + coordinated history rewrite).
- Deletions **BLOCKED** on owner approval of `DELETION-INVENTORY.md`.
- Rebuild (`/test-next`) still loads Tabulator from unpkg. A few innerHTML sinks that are static or already escaped.

## What's next

1. Owner: approve inventory groups (default “approve the inventory” = untrack `.scratch/` only).
2. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie must leave git history.
3. Archive tag at the final pre-deletion commit.
4. Migrate Entra / magic links / user authority / OData into root v3.
5. Prove `/` without `webapp/`, `/test`, `rebuild/`; then unmount and delete approved paths.
6. Remove Beta pill; remaining review gates.

## Open decisions

Unchanged from the repository review (beta bookmarks, leftover legacy features, CLI/runbooks, Run now vs Send now, Shabbos fail-open, commission/name rules).

## Gotchas

- Do not print or replay cookie values. History of `webapp-cache` still contains the old blob until rewritten.
- Do not delete `webapp/` before login/OData are native in v3.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/` while Azure Automation uses them.
- Prod Litestream is fail-closed. Empty replica + empty local disk will refuse boot.
- Do not add a repo `.semgrepignore`; it replaces Semgrep defaults (`tests/`, `*.min.js`).
