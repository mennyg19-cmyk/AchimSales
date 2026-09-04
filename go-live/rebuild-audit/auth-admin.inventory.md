# Auth + Users & access inventory

Model: gpt-5.6-sol-medium
Runner: spawn
Area: auth-admin
Role: inventory
Graph: graph via parent digest

## Proof of read

- `AUDITOR-INSTRUCTIONS.md`: 3 required-reading files, 2 permitted audit roles, 1 live app root, and 1 required deliverable; application-code edits are forbidden.
- `graph-backbone/INDEX.md`: 4 area digests, 5 worker job types, 4 roles, 2 cookie mounts, and 1 Beta blueprint omission.
- `graph-backbone/auth-admin.md`: 8 auth route rows, 9 admin route rows, 4 roles, 3 auth templates, and 3 bootstrap seed functions.

## Preservation counts

- 2 user-facing page families: sign-in and Users & access.
- 4 rendered templates in scope: `login.html`, `role_picker.html`, `impersonate.html`, and `admin_users.html`.
- 8 auth handlers covering 10 method/path operations.
- 12 admin handlers covering 12 method/path operations.
- 4 roles: `admin`, `developer`, `manager`, and `salesman`.
- 2 impersonation systems: Live/Beta Switch user at `/dev/role-picker`, and v3-session impersonation at `/impersonate`.
- 1 duplicate-create conflict: HTTP 409 from `POST /api/admin/users`.

## Authentication pages and routes

### `GET /login`

- Beta first calls `adopt_live_identity()`. If either an adopted Live principal or an existing v3 principal is available, it redirects to the reports list.
- A Beta visitor without an identity sees the Live sign-in form. `next` must start with one `/` and not `//`; an unsafe value becomes `/`.
- The Achim User Login button links to `/legacy/login/start?next=<quoted path>`.
- The External Rep Login button opens a modal. The modal can be closed by its × button, Cancel, clicking the overlay, or Escape.
- The external form has one required, autofocus email field and posts to `/legacy/login/magic-link`.
- The modal promises a one-time link from `reports@achimonline.com` that expires in 15 minutes. Its submit button is “Send sign-in link.”
- In MSAL mode, the route stores a safe destination in session key `v3_login_next` and redirects to the Entra login URL.
- In dev mode, the page renders Developer sign-in with a CSRF token, hidden `next`, required email, role selector containing all four roles, and Sign in.
- Outside the Beta-specific path, an unsafe or absent `next` falls back to `health.healthz`, not `/`.

### `POST /login/dev`

- Beta rejects the route with 403: `Beta uses Live login; open /legacy/login`.
- Any environment whose `AUTH_MODE` is not `dev` rejects it with 403: `Dev login is disabled in this environment`.
- Email is trimmed and lowercased; it must contain `@` or the route returns 400 `valid email required`.
- Role is trimmed and lowercased. Missing or invalid roles become `salesman`.
- The user row is upserted with the submitted role and email as its display name.
- An inactive row is rejected with 403 `This account is disabled`.
- A successful login stores a permanent principal with `is_dev=True`, then redirects only to a safe same-app path.

### `GET|POST /auth/callback`

- Beta never completes a separate Entra callback. It redirects through `live_login_redirect("/")`, which resolves to `/login?next=/`.
- Non-Beta completes the MSAL flow. A returned error becomes HTTP 400 with that error text.
- The callback upserts email and display name, but an inactive account is rejected with 403.
- Success consumes `v3_login_next`; if absent it redirects to `health.healthz`.

### `POST /logout`

- Non-Beta removes only `v3_user`, then returns to `/login`.
- Beta removes the v3 principal, removes the Live `user`, clears the entire shared session, and redirects to `/login`.
- Sign Out is a POST action in the shared header, so logout must remain CSRF-protected rather than become a GET link.

## Cookies, session identity, and Live adoption

- Beta uses Live’s signed `session` cookie. Non-Beta, including `/test`, uses `v3_session`.
- `v3_user` contains the serialized `Principal`; login makes the Flask session permanent and logout removes that key.
- A principal contains email, name, role, `is_dev`, impersonation state, and optional real actor email/name. Email is normalized on deserialization; a missing/invalid role becomes `salesman`.
- The session is authoritative only for identity. Authorization re-resolves active state, role, scope, and flags from v3’s database on every check.
- The per-request role refresh updates cached `v3_user.role` for presentation without requiring a new login. Missing or inactive users are presented as `salesman`.
- The refresh must not overwrite the role while a `_dev` Live-cookie impersonation is active.
- The Beta access gate lets health and static requests pass. Other requests adopt Live identity or redirect to Live login; `auth.*` also attempts adoption. The dashboard blueprint is not mounted on Beta.
- `live_login_redirect(next_path)` accepts only a single-slash local path; unsafe input becomes `/`, and the result points to `/login?next=...`.
- Adoption does nothing destructive when Live `session["user"]` is absent or malformed; it returns the current v3 principal.
- Live email is trimmed/lowercased. Name defaults to email and removes a trailing impersonation marker of the form ` (as ...)` when choosing a stored display name.
- Live role defaults to `salesman` and invalid roles become `salesman`.
- `_dev` or a Live `developer` role marks the cookie as developer-shaped, but actual developer power requires `_dev_email` to resolve to an active v3 developer row.
- A stale impersonation cookie whose actor row no longer exists clears Live identity, logs out v3, and returns no principal.
- If the actor still exists but was demoted or disabled, adoption restores the actor’s own database identity and strips developer/impersonation state.
- A developer’s own first Live login is allowed to create a row even though no actor row exists yet.
- First adoption creates a v3 user using Live role and display name. It also copies salesman scope for non-privileged users from Live `salesman_key` plus deduplicated `get_user_salesman_access(email)` keys.
- Admin/developer first adoption does not copy salesman scope because privileged users are unrestricted.
- Later ordinary visits do not overwrite an existing user’s role, sales group, external flag, other access flags, or nonblank display name. They fill a blank display name only.
- While impersonating, the principal’s session role comes from the Live target. Otherwise it comes from the v3 user row.
- Adoption reuses an existing principal only when email, role, developer status, and impersonation state all still match; otherwise it rewrites `v3_user`.
- If Live salesman-scope lookup fails, adoption continues with any cookie key and logs the failure.

## Switch user: Live/Beta role picker

### `GET|POST /dev/role-picker`

- This is the shared-header “Switch user” flow for a user marked `_dev`; it is separate from `/impersonate`.
- It first adopts Live identity, then falls back to the current v3 principal. No identity redirects to `/login`.
- The real actor email comes from Live `_dev_email`, principal `real_email`, or principal email, in that order.
- The actor must resolve to an active v3 developer row. Failure redirects to the reports list rather than returning 403.
- The picker merges the Live directory with all v3 users, including inactive v3 rows. Invalid Live emails are skipped.
- A matching v3 row overrides the Live display name and role. v3-only users are included; Live salesman keys remain on matching directory entries.
- Failure to import/read the Live directory falls back to v3 users and logs non-import errors.
- Users are shown in fixed Admins, Developers, Managers, Salesmen groups.
- The page has Back, “View as Admin (yourself),” a name/email search field, radio choices, and “View as Selected User.”
- Search filters rows and hides empty role groups. The selected-user button starts disabled and enables after a radio change.
- The actor’s own row is labelled `(you)` and its radio is disabled.
- Submitting `target_email=__self__` rewrites Live `session["user"]` to the actor with role `admin`, `_dev=True`, actor name/email markers, and no salesman key.
- If available, the self action loads the actor’s Live theme; theme failure is ignored.
- A target is looked up in Live first, then by lowercased email in v3. No match returns 404 `User not found`.
- A target action writes target email, role, salesman key, and a display name suffixed with `(as <developer>)`, while preserving `_dev` actor markers.
- If available, the target’s Live theme is loaded; theme failure is ignored.
- After either action, the old `v3_user` is removed, the new Live identity is adopted, and the user returns to the reports list.
- The picker does not reject an inactive target at selection time. Downstream authorization still fails closed because the target’s active v3 row is re-resolved.

## v3-session impersonation

### `GET /impersonate`

- No principal redirects to `/login`.
- Nested impersonation returns 400 `Cannot nest impersonation; end the current session first`.
- Developer authorization is database-resolved; a non-developer gets 403 `Impersonation is developer only`.
- The page lists every v3 user, including inactive accounts, grouped by role.
- Salesmen are expanded by default. Every user is a submit button showing display name, with email in its tooltip.
- Inactive users use muted styling and an asterisk; the page explains `* = inactive account`.

### `POST /impersonate`

- No principal redirects to `/login`; nested impersonation returns 400 `Cannot nest impersonation`.
- A non-developer gets 403 `Impersonation is developer only`.
- Missing email returns 400 `Target email required`; an unknown email returns 404 `User not found`.
- Success stores a principal with the target’s email/role, display text `<target> (as <actor>)`, the actor’s `is_dev`, and real actor email/name, then returns to reports.
- The route does not block an inactive target at selection time; live authorization checks still deny an inactive database row.

### `POST /impersonate/end`

- A missing or non-impersonating principal simply returns to reports.
- If the real actor row is missing or inactive, the route logs out and redirects to `/login`.
- Otherwise it restores the actor using the actor row’s current role and the saved real name, retaining `is_dev`.

## Authorization rules that must survive

- Unknown, missing, and inactive users fail closed.
- Privileged means an active database role of `admin` or `developer`; a principal/session role alone cannot grant it.
- Developer checks require an active database `developer` row.
- Managers are active database `manager` rows.
- Admins, developers, and managers can see company schedules. Salesmen cannot.
- Privileged users may always edit a master schedule. A manager may edit only when their user ID is the owner or run-as user.
- Commissions are visible to privileged users and managers, never salesmen.
- Privileged users have unrestricted salesman scope, represented by `None`.
- Other active users receive exactly their `user_salesman_access` keys. Unknown/inactive users receive an empty set.
- Customer visibility normalizes the customer SalesGroup to a salesman key and requires membership unless scope is unrestricted.
- Unknown reports and reports not in `BUILT` status are never visible.
- `privileged_only` reports cannot be granted to managers or salesmen, even by an explicit allow override.
- A per-user report override wins over global report configuration.
- Without an override, a globally disabled report is hidden from every role, including privileged users.
- Without an override or global disable, privileged users see the report, managers inherit visibility for all non-privileged-only built reports, and salesmen inherit only reports marked `salesman_default`.
- Report run/result/export checks require a nonempty report key and current report access. Builders receive the current salesman scope.
- Deferred delivery re-resolves the stored owner at execution time. A missing/inactive owner, revoked report, or revoked SharePoint permission fails with `Forbidden`.
- SharePoint is always available to privileged users; other active users need `sharepoint_access`.
- Company views are always visible to privileged users; other active users need `can_see_company_views`.

## Users & access page

### Shared header controls

- The shared header keeps Recent Reports, the theme toggle, and a POST Sign Out action.
- “Switch user” appears when the template user has `_dev`.
- While impersonating, the header shows an impersonation badge and must retain the end-impersonation action.

### Page access and rendered tables

- `GET /admin/users` requires login and current database privilege. A logged-in non-privileged user receives JSON 403 `{"error":"Forbidden"}`.
- The page’s Back link returns to Settings.
- The heading shows the user count and explains that role and salesman scope are enforced live.
- The user table supports email/name search and displays Email, Name, Role, Flags, and actions.
- Visible flags are Disabled, Dashboard, SharePoint, Test, Company views, and External.
- “View as” is hidden for the current user. On Beta it appears only for `_dev` actors and posts `target_email` to the role picker; outside Beta it posts `email` to `/impersonate`.
- Every row has Edit.
- The Salesmen table is the D365 master, separate from login users. It displays number, display name, email, active toggle, and Edit.
- D365 customer SalesGroup values, not login rows, populate report-filter and salesman-login dropdowns. A new hire without customers is absent from those dropdowns.

### Add user form

- The collapsible Add user form has required Email, Role, optional Display name, conditional SalesGroup, External login, Add user, and an inline message.
- SalesGroup appears only when role is `salesman`.
- SalesGroups come from the privileged `/api/admin/sales-groups` lookup, the same customer list used by report filters.
- If lookup data is empty, the page polls lookup status every 2.5 seconds. It shows loading or warming text, stops when ready/cached/mirrored rows exist, and then reloads groups.
- Submit sends email, role, display name, external flag, and salesman-only SalesGroup. Success reloads; failure displays the API error or `Failed to add user`.

### Edit user modal

- Fields: Display name and Role.
- Flags: Active (can sign in), Dashboard access, SharePoint access, Test-site access, Company views, and External login.
- A salesman gets one SalesGroup selector. A manager gets per-salesman checkboxes. Admin/developer sees neither scope editor because their scope is unrestricted.
- Per-report access has `Inherit`, `Allow`, and `Deny` for every built report.
- Buttons: × close, Delete user, Cancel, and Save.
- Opening the modal loads both salesman scope and report overrides. One salesman key can backfill a blank SalesGroup selection.
- Changing role to developer checks Company views in the UI; the server-side privileged rule grants company views regardless of this stored flag.
- Save updates the user first. For managers it then saves checked salesman keys. It posts every report’s tri-state selection, then reloads.
- Delete asks: `Delete this user and all their saved data? To block sign-in without wiping data, Disable them instead.` Cancel leaves the row untouched.
- Clicking a modal overlay closes that modal.

### Edit salesman behavior

- The active toggle immediately sends `is_active`; it is disabled while saving and rolls back visually on failure.
- Edit salesman fields are Number, Full name, Display name, and Email.
- Buttons: × close, Cancel, and Save.
- Success reloads; failure shows the API error or `Save failed`.
- The named endpoint does not expose commission or split-mail fields; those must not be invented as controls from the digest’s “etc.” wording.

## Admin APIs and status behavior

All admin routes require a login and then database-resolved admin/developer privilege. Every failed privilege guard returns 403 `{"error":"Forbidden"}`.

### Users

- `GET /api/admin/users` returns all login users with: ID, email, display name, role, active, external, dashboard, SharePoint, test-site, company-views, and SalesGroup values.
- `POST /api/admin/users` normalizes email and role. Invalid email returns 400 `Valid email required`; invalid role returns 400 `Invalid role`.
- Duplicate email returns 409 `User already exists; edit them instead`.
- Only an active database developer may create a developer; otherwise 403 `Only a developer can assign or change the developer role`.
- Create accepts email, role, display name, external flag, and SalesGroup. A salesman with SalesGroup gets exactly its normalized key as salesman scope.
- A newly created non-privileged, non-salesman role with no explicit scope inherits matching D365 salesman keys by email when any exist.
- `PUT /api/admin/users/<id>` returns 404 `Unknown user` if absent and 400 `Invalid role` for an invalid supplied role.
- A user cannot change their own role: 403 `You cannot change your own role`.
- Only a developer may assign developer, change a developer to another role, or mutate any existing developer row. The two 403 messages are respectively `Only a developer can assign or change the developer role` and `Only a developer can change a developer login`.
- Update accepts role, display name, active, external, dashboard, SharePoint, test-site, company-views, and SalesGroup.
- Setting a salesman’s SalesGroup replaces salesman access with that one normalized key, or an empty set for blank SalesGroup.
- `DELETE /api/admin/users/<id>` returns 404 for an unknown user and applies the existing-developer guard.
- Self-delete returns 400 `You cannot delete your own account`.
- Successful delete removes the user and returns its ID. The UI warns that associated saved data is also deleted.

### Salesman scope and SalesGroups

- `GET /api/admin/users/<id>/salesman-access` returns sorted keys; unknown user is 404 `Unknown user`.
- `POST /api/admin/users/<id>/salesman-access` requires `keys` to be a list or returns 400 `keys must be a list`; unknown user is 404. Values are converted to strings and replace current scope.
- `GET /api/admin/sales-groups` returns `{ok:true, items:[...]}` from `LOOKUP_SERVICE.salesmen()`. It is privileged and intentionally independent of report access.

### Report access

- `GET /api/admin/users/<id>/report-access` returns only explicit overrides as `allow` or `deny`; an absent report key means inherit. Unknown user is 404.
- `POST /api/admin/users/<id>/report-access` rejects an unknown report with 400 `Unknown report` and an unknown user with 404.
- `access=inherit` deletes the override. `allow` and `deny` store booleans.
- Backward compatibility accepts a bare `allowed: bool`.
- A body containing neither `access` nor `allowed`, or an invalid access value, returns 400 `access must be inherit|allow|deny`; it must never silently write deny.

### D365 salesman and export history

- `PUT /api/admin/salesmen/<key>` accepts only number, full name, display name, email, and active. Strings are trimmed.
- Unknown salesman or a request with no editable fields returns 404 `Unknown salesman or no editable fields`.
- `GET /api/admin/exports` accepts optional `report_key` and `owner`, limits history to 200, and returns job ID, report key, filename, byte size, build timestamp, export type, and owner email.

## Explicit 403 and 409 preservation list

### HTTP 403

1. Disabled login in dev or MSAL callback: `This account is disabled`.
2. Dev login attempted on Beta: `Beta uses Live login; open /legacy/login`.
3. Dev login outside `AUTH_MODE=dev`: `Dev login is disabled in this environment`.
4. `/impersonate` page or start by a non-developer: `Impersonation is developer only`.
5. Any Users & access page/API call by a logged-in non-privileged user: JSON `Forbidden`.
6. Non-developer creates or assigns developer, or changes a developer’s role: `Only a developer can assign or change the developer role`.
7. Non-developer updates or deletes an existing developer row: `Only a developer can change a developer login`.
8. A user attempts to change their own role: `You cannot change your own role`.
9. `Authorization.Forbidden` maps current report, customer, delivery, and SharePoint access failures to 403.

### HTTP 409

1. `POST /api/admin/users` for an existing normalized email: `User already exists; edit them instead`.

## Graph queries deferred to parent

CodeGraph was not installed in `/workspace`, so structural facts came from the parent digest and the named files. If available, the useful follow-ups would be:

- impact/callers of `adopt_live_identity`
- callers of `Authorization.can_view_report` and `Authorization.assert_report_runnable`
- callers of `Authorization.visible_salesman_keys`
- impact/callers of `sync_role`
- route registration and mount conditions for `auth_bp` and `admin_bp`
