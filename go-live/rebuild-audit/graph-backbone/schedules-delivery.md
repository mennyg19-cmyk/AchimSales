# Area: schedules + delivery

**CodeGraph:** unavailable. Facts from named files.

## Pages (`web.blueprints.schedules`)

| Method | Path | Template / notes |
|--------|------|------------------|
| GET | `/schedules` | `schedules.html` + `personal_schedule_wizard.html` — personal; one table, owner banner rows |
| GET | `/api/schedules/recent-runs` | |
| POST | `/api/schedules` | create personal |
| PUT | `/api/schedules/<id>` | update; privileged CC/BCC |
| POST | `/api/schedules/<id>/toggle` | |
| DELETE | `/api/schedules/<id>` | |
| POST | `/api/schedules/<id>/run` | enqueue `schedule.run` |
| POST | `/api/schedules/<id>/copy` | |
| GET | `/api/schedules/views` | named views eligible to schedule |
| GET | `/schedules/<id>/history` | `schedule_history.html` |
| GET | `/master-schedules/<id>/history` | same history template |
| GET | `/settings/company-schedules` | `company_schedules.html` |
| GET | `/master-schedules` | `master_schedules.html` (alias/settings company wizard) |
| GET | `/api/master-schedules/lookups/status` | |
| GET | `/api/master-schedules/lookups/salesmen` | |
| GET | `/api/master-schedules/lookups/salesmen-emails` | |
| GET | `/api/master-schedules/lookups/customers` | |
| POST | `/api/master-schedules` | create company |
| POST | `/api/master-schedules/<id>/copy` | |
| PUT | `/api/master-schedules/<id>` | |
| POST | `/api/master-schedules/<id>/toggle` | |
| DELETE | `/api/master-schedules/<id>` | |
| POST | `/api/master-schedules/<id>/run` | |

JS: `schedules.ts`, `personal_wizard.ts`, `master_wizard.ts`, `filename_preview.ts`

## Scheduling logic

- `web.scheduling.runner.ScheduleRunner` — owner-scoped personal; master unrestricted; `schedule_runs` row; Graph retry 2×30s; fail-mail wait 15 min, superseded on later success
- `web.scheduling.cadence` — clock / weekday rules
- `web.scheduling.sabbath` — Hebcal skip
- `web.scheduling.catchup` — missed Yesterday/MTD windows
- `web.scheduling.tick` — cron enqueue
- `web.scheduling.personal_views` — which named views can be scheduled (incl. CA named, no period)
- `web.scheduling.company_layouts` — Default vs named company layout
- `web.data.repositories.report_defaults` — `DEFAULT_VIEW_NAME`, `resolve_send_layout`

Filename: `web.delivery.filename_template` — default `{Schedule}_{MM}-{DD}-{YYYY}` for new schedules.

## Delivery

- `web.delivery.service.DeliveryService` — build + layout + Excel + email/SharePoint/OneDrive
- `web.delivery.email.EmailService` — Graph/SMTP; oversized → download/SharePoint link
- `web.delivery.graph_mail`, `graph_upload`, `graph_errors`
- `web.delivery.sharepoint.SharePointService` — `TEST_SHAREPOINT_FOLDER` when test recipients
- `web.delivery.onedrive.OneDriveService`
- `web.delivery.layout` — column order/hide/sort/filter before Excel
- Job: `report.deliver` re-authorizes owner at run time (`delivery/jobs.py`)

## Tables (precious)

`schedules`, `master_schedules`, `schedule_runs` (polymorphic schedule_id), later migrations add keep/filename, share scope, catch-up, last_claimed, company_views, can_see_company_views.
