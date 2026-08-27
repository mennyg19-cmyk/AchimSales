# Session Handoff

Last updated: 2026-08-27

**Status:** P0 containment implemented on `cursor/p0-security-containment-adb6`. Single-site cleanup and deletions not started.

## What's done

- Cherry-picked `REPOSITORY-REVIEW.md` + review handoff onto this branch.
- **P0.1–P0.5** as before (cookies untracked, no cursor Production deploys, OData fail-closed, Litestream readiness, no prod DEV_BYPASS_AUTH).
- Review follow-up: download-file owner check, precious-repair GET-only check, security headers, magic-link claim/throttle/fixed origin, history XSS, notif-diag escape, shared Excel formula prefix.
- Session/DB authz: v3 developer routes and login use `Authorization` (not cookie role). Disabled users are signed out. Live→v3 salesman grants replace on copy. Legacy session role is re-read from `app_users`.
- Customer/order access fails closed when the book is unknown. Managers need a matching grant (order-detail no longer skips that check). Address/price/generate-po APIs and `/api/customers` use the same scope. Last-order picker and order-entry names are escaped. Number 4 `make_cell` and salesman `_excel_val` prefix `=+-@`.
- Leftover XSS: email-distribution chips/logs, order-entry matrix labels, settings beta-source keys, db-explorer errors. Ordered summary and Invoiced data/commission cells prefix formula leaders.
- Legacy CSRF on POST/PUT/PATCH/DELETE (Entra callback exempt). Forms use `{% csrf_token %}` so Semgrep's Django rule matches; fetch still uses the meta token. Feather served locally; unused Chart.js CDN removed. Google Maps stays on Google's CDN.

## What's in progress

- Session revoke and git-history purge are **BLOCKED** (need Azure Flask secret rotation + coordinated history rewrite).
- Remaining review security: v3 Tabulator/Feather still load from unpkg. A few innerHTML sinks that are static or already escaped.
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
