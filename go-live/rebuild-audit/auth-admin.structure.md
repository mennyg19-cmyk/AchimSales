# auth-admin — structure audit

Model: claude-fable-5-1-thinking-medium
Runner: spawn
Area: auth-admin
Role: structure
graph via parent digest (`codegraph: command not found`; no `.codegraph/`)

## Proof of read

- `AUDITOR-INSTRUCTIONS.md` (37 lines): scope = live `v3/` only, `/legacy` only where v3 calls it; Phase 0 Step 2; no app edits; header format; ≤10-line reply.
- `graph-backbone/INDEX.md` (30 lines): 4 area digests, 5 worker job-type constants, 4 roles with privileged = admin+developer; Beta shares Live `session` cookie, `/test` uses `v3_session`; dashboard blueprint not on Beta.
- `graph-backbone/auth-admin.md` (59 lines): 5 auth module files + `beta_live_session.py`; 8 auth routes (`/login`, `/login/dev`, `/auth/callback`, `/logout`, `/dev/role-picker`, `/impersonate` GET+POST, `/impersonate/end`); 10 admin routes (1 page + 9 API); 3 auth templates; `admin.ts`; 3 seed functions.
- Source read in full: `web/__init__.py` (861), `auth/authorization.py`, `auth/session.py`, `auth/principal.py`, `auth/msal_flow.py`, `auth/decorators.py`, `beta_live_session.py`, `blueprints/auth.py` (352), `blueprints/admin.py` (346), `data/repositories/users.py`, `data/seed_users.py`, templates `login.html`, `role_picker.html`, `impersonate.html`, `admin_users.html`, `base.html`, `static_src/js/admin.ts` (352).

## What is wrong / messy (ranked)

### 1. Two impersonation systems, both registered on every mount
- `/dev/role-picker` (Live-style): writes `session["user"]` with `_dev/_dev_email/_dev_name`, pops `v3_user`, calls `adopt_live_identity()`. Template `role_picker.html`.
- `/impersonate*` (v3-native): writes `v3_user` principal with `impersonating=True`. Template `impersonate.html`. Comment says "/test; home uses /dev/role-picker" but nothing gates it by mount.
- On Beta, `_require_live_login` runs `adopt_live_identity()` every request; it compares `existing.impersonating`/`is_dev` to what the Live cookie implies (no `_dev` → both False) and re-logins the real user. A `/impersonate` POST on Beta is therefore undone on the next request. Dead-on-Beta path, live-on-/test path, same blueprint.
- `admin_users.html` "View as" branches on `is_beta` to pick which endpoint and which form field name (`target_email` vs `email`).
- Both templates titled "Impersonate User"; both have their own grouping code (`_group_users` vs inline dict loop in `impersonate_page`).

### 2. Impersonation state encoded in a display string
`"{display} (as {dev})"` is built in `role_picker` and `impersonate_start`, then parsed with `.split(" (as ")` in `__init__.inject_globals`, `beta_live_session.adopt_live_identity`, `auth.role_picker`, and `base.html`. Four parsers of one magic string. `Principal` already has `real_name`/`impersonating`; the string is redundant state.

### 3. Three ways to ask "is this user privileged/developer"
- `Authorization.is_privileged / is_developer` — DB-resolved (the documented rule).
- `decorators.require_privileged` — reads `p.is_privileged` from the **session cookie**. Contradicts `authorization.py` docstring ("never trusts the session role"). Not used by admin.py, but it lives in the auth package and is the obvious decorator a new route would reach for.
- `admin._guard()` — inline call repeated at the top of all 12 admin handlers instead of a decorator.
`_role_edit_blocked` and `_developer_row_blocked` both re-check `target.role == developer and not is_developer(p)`; `update_user` runs both.

### 4. Three writers of `users.role`, with conflicting persistence rules
- `seed_users_from_live` runs **every boot** and `ON CONFLICT ... SET role, is_external, dashboard_enabled` from Live. Users & access edits to those three fields are reverted at next restart unless mirrored in Live. Digest line "later visits do not overwrite" describes `adopt_live_identity` only; the boot seed does overwrite.
- Delete in Users & access does not stick: mirror re-inserts the row `is_active=1`. Disable does stick (UPDATE clause omits `is_active`). Two outcomes for the "remove a person" intent; the JS confirm text does not mention this.
- `_seed_admins` / `_seed_developers` use raw SQL in the app factory instead of `UserRepository`.
- `seed_users.py` docstring: "never imports live code". `beta_live_session._sync_salesman_scope` and `auth.role_picker` both `from webapp.db import ...`. Coupling policy is stated one way and practiced another.

### 5. `role_picker` "view as yourself" hardcodes `role: "admin"` into the Live cookie
A developer choosing `__self__` becomes `admin` in Live's cookie; v3 then re-resolves developer from DB. Live and Home now disagree on the same person's role for the rest of the session.

### 6. `web/__init__.py` is a god file (861 lines, 5 concerns)
App factory, session-role refresh (35-line `before_request` with impersonation branching), nav/flags context processor, 3 user seeders, 2 hardcoded master-schedule tables (~190 lines), gunicorn leader election. Auth-area pieces that belong in `web/auth/`: `_refresh_session_role`, the `user` dict in `inject_globals`, `_seed_admins`, `_seed_developers`, `_seed_users_from_live`.

### 7. Per-request DB chatter on Beta
Order of registration: `_refresh_session_role` (context) is registered before `_require_live_login` (gate), so the role refresh runs on the stale principal and adoption then rewrites it. Per HTML request the `users` table is hit by: adopt (actor + user), refresh (real_row and/or actor + row), `inject_globals` (row) — 4–6 lookups for one identity.

### 8. Users & access save is N+2 non-atomic requests
`saveUser`: PUT user → optional POST salesman-access → one POST per built report → `location.reload()`. Report POST results are never checked (`Promise.all` on raw responses). A failure after the PUT leaves role changed but scope/report overrides unchanged, with no message.

### 9. Salesman scope has two write semantics on one table
`sales_group` (single value, salesman role, `_sync_salesman_access_from_group` replace-all) vs `keys` list (manager role). `create_user` adds a third: managers with no group fall back to `SalesmanRepository.keys_for_email`. That fallback is a business rule living in a route with no test or comment stating why.

### 10. Non-privileged HTML request gets raw JSON
`/admin/users` uses `require_login` (HTML-aware redirect) but `_guard()` always returns `jsonify 403`. A manager opening the URL sees `{"error":"Forbidden"}` instead of a page.

### 11. Redirect targets
- `_safe_next()` default and `callback()` fallback = `health.healthz` → a fresh MSAL login with no `next` lands on health JSON.
- `logout_route` on Beta: `redirect("/login")` literal; `live_login_redirect` and `login_page` build `/login` and `/legacy/login/start` literals. `_require_live_login` computes `request.script_root` for its `next`, the others do not. Mount-prefix handling is inconsistent within one flow.

### 12. Templates
- `login.html` holds two unrelated screens (Live launcher + external magic-link modal posting to `/legacy/login/magic-link`; dev sign-in form) behind one flag, with inline styles and an inline `<script>`. Everything else on the page tree ships TS from `static_src`.
- `role_picker.html`: inline styles on every row, inline filter script duplicating `admin.ts initSearch`.
- `impersonate.html`: one `<form>` per user button.
- `base.html` "Viewing as" badge only when `user._dev and role not in (admin, developer)`: impersonating an admin/manager-turned-admin shows no badge.

### 13. Smaller
- `login_dev` passes `role` to `UserRepository.upsert`, whose `ON CONFLICT` never updates role → chosen role silently ignored for an existing email (dev-only).
- `User.from_row` tolerates missing `can_see_company_views` / `sales_group` columns — schema drift defense that migrations should make unnecessary.
- `admin._user_dict` hand-copies the `User` dataclass (`dataclasses.asdict` covers it).
- `list_all()` vs `all_users(include_inactive=True)` — same table, different sort, names do not say which is which.
- `is_dev` means "dev-mode login" in `login_dev`, "actor is a developer" in `adopt_live_identity`, and "show Switch user link" in `base.html`.
- `/api/admin/exports` sits in the admin blueprint with no control on `admin_users.html` (caller unknown without graph).
- Salesmen D365 master table + edit modal live on the Users page (mixed concern, per the page's own hint text).

## Coverage skeleton (names only)

**Login** `/login` (`login.html`)
- Beta: "Achim User Login" → `/legacy/login/start?next=`; "External Rep Login" button → modal `externalLoginModal` (email, Cancel, "Send sign-in link" → POST `/legacy/login/magic-link`, Esc/overlay close)
- Non-Beta dev: email, role select, "Sign in" → POST `/login/dev`
- Non-Beta msal: redirect to Entra; return `/auth/callback`

**Header** (`base.html`, all pages)
- logo → reports; v3 pill (non-prod); Beta badge; user name **or** "Viewing as …" badge; role badge; Recent Reports; theme toggle; Switch user (if `_dev`) → `nav.login`; Sign Out (POST)
- Bottom nav: Reports, Dashboard (non-Beta, gated), Schedules, Test Site (gated), Settings

**Switch user** `/dev/role-picker` (`role_picker.html`, Beta)
- Back; "View as Admin (yourself)" (`__self__`); search `userFilter`; grouped radio list Admins/Developers/Managers/Salesmen (self disabled, salesman_key shown); "View as Selected User"

**Impersonate** `/impersonate` (`impersonate.html`, /test)
- collapsible role groups (salesman open); one button per user (inactive muted + `*`); POST `/impersonate`; `/impersonate/end` (no UI control found in read files)

**Users & access** `/admin/users` (`admin_users.html` + `admin.ts`)
- Back → Settings; count subtitle; hint text
- Add user `<details>`: email, role, display name, SalesGroup select (salesman only, polled via `reports.lookup_status`), External login, "Add user", msg
- Search `userSearch`; table columns Email / Name / Role badge / Flags (Disabled, Dashboard, SharePoint, Test, Company views, External) / actions "View as" (not self; Beta needs `_dev`), "Edit"
- Salesmen table: #, Name, Email, Active switch (PUT `/api/admin/salesmen/<key>`), "Edit"
- Edit user modal: Display name, Role, flags (Active, Dashboard, SharePoint, Test-site, Company views, External), SalesGroup (salesman), Per-salesman access grid (manager), Per-report access Inherit/Allow/Deny per built report, Delete user (confirm), Cancel, Save, msg
- Edit salesman modal: Number, Full name, Display name, Email, Cancel, Save, msg

**APIs** (JSON, privileged): `GET/POST /api/admin/users`, `PUT/DELETE /api/admin/users/<id>`, `GET/POST …/salesman-access`, `GET/POST …/report-access`, `GET /api/admin/sales-groups`, `PUT /api/admin/salesmen/<key>`, `GET /api/admin/exports`

**Boot seed (no UI)**: `seed_users_from_live` (Live `app_users` → v3 `users` + `user_salesman_access`), `V3_ADMIN_EMAILS`/`V2_ADMIN_EMAILS`, `V3_DEVELOPER_EMAILS`

## CodeGraph queries I would have run

`codegraph callers require_privileged`, `callers export_history`, `callers Principal.is_privileged`, `callers adopt_live_identity`, `callers impersonate_end`, `impact Principal`, `callers UserRepository.upsert`, `callers keys_for_email`, `node init_csrf` (does it accept `X-CSRF-Token` header used by `admin.ts`?).
