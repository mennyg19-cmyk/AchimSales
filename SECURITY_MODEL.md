# Security model: AchimSales

This is the threat model used for Devin security scans. It was drafted from the code and then corrected with Menny's answers in November 2026. Edit it when the system changes, and keep component names stable so findings from different scans line up. No infrastructure repo exists: deploy config is in this repo, and the rest is set in the hosting portal.

## Decisions (these drive finding priorities)
- **Assets:** every asset below matters equally.
- **Attackers:** every attacker profile below is in scope.
- **Out of scope / accepted risk:** none. Report everything, including parked rebuilds, legacy apps, test-only routes and dev tooling.
- **Finding tags:** `Component` (below) and `Site`.

## System overview
### AchimSales (Site: Achim)
- **What it is:** a sales-reporting site for Achim at https://reports.achimonline.com. It is an Azure App Service container (`Dockerfile`, gunicorn `wsgi:application`) and is reachable from the internet.
- **How requests are routed:** `wsgi.py` and `wsgi_dispatch.py` mount several Flask apps in one process:
  - `/` is v3 in beta mode (`v3/web/`).
  - `/legacy` is the old live app (`webapp/`).
  - `/test` is v3 (when `V3_MOUNT_ENABLED` is set).
  - `/test-next` is the rebuild (`rebuild/`, when `REBUILD_MOUNT_ENABLED` is set).
  - `/auth/*` and the magic-link/MSAL login paths always go to the legacy app.
  - The FastAPI rebuild (`app/`) is parked, with its own deploy scripts.
- **Data sources:** D365 F&O over OData (`core/odata.py`), the on-prem SQL Reporting API (stored procedures such as `rpt.usp_salesmen_master`), and Microsoft Graph for mail and SharePoint/OneDrive (`v3/web/delivery/`).
- **Local state:** SQLite (`precious.db`, `cache.db`, the legacy `webapp/db.py`), replicated to Azure Blob by Litestream (`litestream.yml`, `startup.sh`).
- **Scheduled jobs:** Azure Automation runs `runbooks/universal_runbook.py`, which downloads the code from SharePoint and runs the reports through `report_registry.json`. The in-app scheduler is in `v3/web/jobs`, `v3/web/scheduling`, with Hebcal-based Shabbos skip.
- **Auth:**
  - Microsoft Entra ID (MSAL, `v3/web/auth/msal_flow.py`, `webapp/auth.py`).
  - Magic-link email login for external salesmen. Tokens are 32 random bytes, valid for 15 minutes and single use (`webapp/db.py`, `webapp/blueprints/auth.py`).
  - `/dev-login`, gated by `DEV_BYPASS_AUTH`.
  - The Flask session cookie is signed with `FLASK_SECRET_KEY`. `webapp/config.py` falls back to a generated secret when the key is unset.
- **Roles:** `admin`, `developer`, `manager`, `salesman` (`v3/web/auth/principal.py`).
  - Privileged means admin or developer (`require_privileged`). Developer-only covers devtools: DB explorer, raw SQL, cell edit and row delete (`v3/web/blueprints/devtools.py`, `webapp/blueprints/db_explorer.py`).
  - Salesmen are limited to customers whose `SalesGroup` maps to their visible salesman keys (`v3/web/auth/authorization.py`). The report cache and dedup keys include this scope (the scope-safe cache in `v3/web/reporting`).


## Components
| Component | Site | Code |
|---|---|---|
| Achim Web | Achim | `v3/web/` (except `auth/`), `webapp/` (except auth files), `rebuild/`, `wsgi.py`, `wsgi_dispatch.py`, `tools/` |
| Achim Auth | Achim | `v3/web/auth/`, `v3/web/blueprints/auth.py`, `v3/web/beta_access.py`, `webapp/auth.py`, `webapp/blueprints/auth.py`, `webapp/services/magic_link.py`, `config/settings.py` |
| Achim Reporting & Delivery | Achim | `v3/report_engine/`, `v3/web/delivery/`, `v3/web/jobs/`, `v3/web/scheduling/`, `core/`, `config/`, `reports/`, `run.py`, `runbooks/` |
| Achim FastAPI Rebuild | Achim | `app/` |
| Achim Infra | Achim | `Dockerfile`, `startup.sh`, `gunicorn.conf.py`, `deploy.ps1`, `deploy-runbook.ps1`, `litestream.yml`, `.github/workflows/` |

## Trust boundaries and entry points
1. **Internet to Achim:** login pages, the Entra callback, magic-link request and consume, `/dev-login` (when the env flag is on), and the AlwaysOn health check. Everything else requires a session.
2. **Achim session to role:** salesman, manager, admin and developer have different access. The salesman-scope check guards report data, schedules and exports. Devtools run raw SQL against SQLite.
3. **Achim to back ends:** D365 OData, the on-prem SQL Reporting API, Graph (app credentials can send mail as `EMAIL_FROM` and write to SharePoint), and Azure Blob (Litestream key).

## Assets (all equal priority)
- Achim sales data: one salesman must not see another's customers, commissions or invoices.
- Achim credentials: D365, the SQL Reporting API, Graph (mail sending and SharePoint), Litestream/Azure Blob, `FLASK_SECRET_KEY`.
- Admin and developer accounts.

## Attacker profiles (all in scope)
- Anonymous internet users.
- Achim salesmen, including external magic-link users, trying to see beyond their scope.
- Lower-privilege staff (Achim manager or salesman) trying to escalate.
- Malicious insiders with admin or developer roles.

## Existing controls (from code)
- **Achim:** `require_login`, `require_privileged` and developer gates. The salesman scope is part of cache and dedup keys. Magic-link tokens are random, single use and short-lived. A Semgrep guardrail runs on `v3/` only, not on `webapp/`.

## Open questions
- Is `DEV_BYPASS_AUTH` ever enabled on the production App Service, and does `FLASK_SECRET_KEY` always get set there?
- Are the `/test` and `/test-next` mounts enabled in production?
