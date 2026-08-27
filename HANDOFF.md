# Session Handoff

## What's done

- Audited production revision `330d1bc` on `webapp-cache`; it matched `origin/webapp-cache`.
- Ran five independent `gpt-5.6-sol-high` passes: functionality, security, UI/UX, architecture, and operations.
- Consolidated all accepted findings into `REPOSITORY-REVIEW.md`.
- Added the owner's required end state: one root web app only, based on the current `/` site; remove its Beta pill and retire/archive all old web generations.
- Added the required junk-cleanup inventory, deletion-confirmation gate, refactor order, and release gate.
- Verified `.scratch/parity-cookies.env` is tracked since `f286ce2` without reading or replaying its values.
- Current working branch: `cursor/repository-review-handoff-edd4`.

## What's in progress

- Documentation handoff only.
- No product code, route, database, deployment, or cleanup deletion has been changed.
- `REPOSITORY-REVIEW.md` and this handoff are ready to commit and push.

## What's next

1. Read `REPOSITORY-REVIEW.md` in full.
2. Revoke the two tracked production sessions and purge `.scratch/parity-cookies.env` from Git history.
3. Remove `cursor/**` from direct Production deployment.
4. Disable hybrid OData for scoped users until every tab is provably scoped.
5. Fix Litestream validation/restore readiness and reject Production `DEV_BYPASS_AUTH`.
6. Create and push an archive tag at the final pre-deletion commit.
7. Inventory every proposed deletion under `cleanup-protocol.mdc`; present exact paths and get approval before deleting.
8. Migrate Entra callback, external magic links, user authority, required legacy features, and active OData dependencies into the root v3 app.
9. Prove `/` runs without `webapp/`, `/test`, or `rebuild/`, then unmount and delete the approved old site code.
10. Remove the Beta pill and rename preview-only concepts while preserving current root behavior.
11. Delete approved stale tests, reports, summaries, plans, build/test output, generated artifacts, logs, and dead code.
12. Complete security, scheduling/delivery, CI/readiness, accessibility, parity, and production review gates in `REPOSITORY-REVIEW.md`.

## Open decisions

- Whether old `/beta` bookmarks should redirect to `/` or return 404/410.
- Which legacy-only email distribution, Azure history, dashboard, or OData features must survive in the root app.
- Whether CLI/Azure Automation report generation will remain long term. It is active today and must not be deleted as junk.
- Whether **Run now** should become a confirmed **Send now** action.
- Whether Shabbos/Holiday calendar failure should delay mail or retain the current fail-open send policy.
- Commission-rate unit/effective-date rules and whether customer display names are guaranteed unique.

## Gotchas

- Do not print or replay `.scratch/parity-cookies.env`.
- Do not delete `webapp/` before replacing the root app's login/session/user/OData dependencies.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/`, or their active tests while Azure Automation/CLI still use them.
- Do not delete tests merely because there are many; remove only tests whose production subject is deleted.
- `static_dist` is required until CI builds frontend assets into the deploy artifact.
- The cleanup protocol requires an exact deletion report and explicit approval before deletion.
- Current `/` is implemented as v3 `is_beta=True`; flipping it to false would change auth, cookie, dashboard, source, and schedule behavior.
- CodeGraph is unavailable in this environment; targeted Read/Glob/ripgrep fallback was used.
- Local pytest/frontend dependencies are absent, so the 792 discovered tests were inspected but not executed.
