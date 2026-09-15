# Area: auth + Users & access

**CodeGraph:** unavailable (no CLI, no `.codegraph/`). Facts from named files.

## Boot / cookies

- Factory: `v3/web/__init__.py` `create_app`
- Cookie name: `session` if `cfg.is_beta` else `v3_session`
- CSRF: `web.extensions.init_csrf`
- Beta gate: `_register_beta_access_gate` — adopt Live identity or redirect `live_login_redirect`; health + static skip; `auth.*` still calls `adopt_live_identity`
- Session role refresh: `_refresh_session_role` before_request; impersonation ends if real actor is not an active developer row; `_dev` cookie impersonation skipped for role overwrite; missing/inactive user → session role `salesman`

## Auth module files

- `v3/web/auth/authorization.py` — `Authorization`, `Forbidden`, `is_developer`, `is_active_developer_row`, report/salesman/SharePoint scope
- `v3/web/auth/session.py` — login/logout/current_principal/sync_role
- `v3/web/auth/principal.py` — `Principal`, `VALID_ROLES`
- `v3/web/auth/msal_flow.py` — Entra login URL
- `v3/web/beta_live_session.py` — `adopt_live_identity` (first Live login creates v3 row + salesman scope; later visits do not overwrite display_name/role/sales_group/is_external/access)

## Routes (`web.blueprints.auth`)

| Method | Path | Handler |
|--------|------|---------|
| GET | `/login` | `login_page` — Beta: Live start or reports; MSAL redirect; else `login.html` |
| POST | `/login/dev` | `login_dev` — refused unless `AUTH_MODE=dev` (and not Beta) |
| GET/POST | `/auth/callback` | MSAL callback |
| POST | `/logout` | `logout_route` |
| GET/POST | `/dev/role-picker` | Switch user; requires live DB developer |
| GET | `/impersonate` | page; developer-only |
| POST | `/impersonate` | start impersonation; developer-only |
| POST | `/impersonate/end` | end impersonation |

Templates: `login.html`, `role_picker.html`, `impersonate.html`

## Admin (`web.blueprints.admin`)

| Method | Path | Handler |
|--------|------|---------|
| GET | `/admin/users` | Users & access page `admin_users.html` |
| GET | `/api/admin/users` | list |
| POST | `/api/admin/users` | create; 409 if email exists |
| PUT | `/api/admin/users/<id>` | update display_name/role/flags; cannot self-change role; only DB developer may mint/change/disable/delete developers |
| DELETE | `/api/admin/users/<id>` | delete v3 row |
| GET/POST | `/api/admin/users/<id>/salesman-access` | scope |
| GET | `/api/admin/sales-groups` | privileged lookup for SalesGroup dropdown |
| GET/POST | `/api/admin/users/<id>/report-access` | per-report allow/deny; missing user 404 |
| PUT | `/api/admin/salesmen/<key>` | salesman row (commission, split-mail, etc.) |
| GET | `/api/admin/exports` | export list (admin) |

JS: `v3/web/static_src/js/admin.ts` → `static_dist/js/admin.js`

## Header / Switch user (template facts)

`base.html`: Sign Out POST; theme toggle; Recent Reports; Switch user link if `user._dev`; impersonate badge.

## Seed

`_seed_users_from_live`, `_seed_admins`, `_seed_developers` in `v3/web/__init__.py` bootstrap.
