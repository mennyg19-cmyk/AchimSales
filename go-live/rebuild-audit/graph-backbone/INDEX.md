# Graph backbone (parent digest)

**Date:** 2026-09-02
**App:** live `v3/` (Flask). Production URL https://reports.achimonline.com
**CodeGraph:** CLI not on PATH; `.codegraph/` absent. Digests from named-file Read.
**Mounts:** Beta (`is_beta`) shares Live `session` cookie; `/test` uses `v3_session`. Dashboard blueprint is **not** registered on Beta.

## Areas

| File | Area |
|------|------|
| `auth-admin.md` | Login, Live adopt, roles, Users & access, impersonation, Switch user |
| `reports-excel.md` | Report registry, run/export APIs, grid, saved/company views, Excel writer |
| `schedules-delivery.md` | Personal + master schedules, cadence, Sabbath, email/SharePoint/OneDrive |
| `settings-dashboard-data.md` | Settings, dashboard, jobs worker, sqlite, health, developer tools |

## Job types (worker)

| Constant | Value |
|----------|-------|
| `JOB_TYPE` | `report.run` |
| `EXPORT_JOB_TYPE` | (export handler in `web.reporting.export_jobs`) |
| `DELIVERY_JOB_TYPE` | `report.deliver` |
| `SCHEDULE_RUN_JOB_TYPE` | `schedule.run` |
| `DASHBOARD_REFRESH_JOB_TYPE` | (dashboard.jobs) |

## Roles

`admin` | `developer` | `manager` | `salesman`. Privileged = admin + developer (`web.auth.principal._PRIVILEGED`).
