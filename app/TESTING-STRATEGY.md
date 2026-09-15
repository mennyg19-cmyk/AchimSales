# Dummy home tests (`app/tests`)

| Case | Expected |
|------|----------|
| `/healthz` | `{"status":"ok"}` |
| AlwaysOn `GET /` | 200 JSON, not a login 302 |
| `/beta` | 302 `/` |
| Preview login | Reports home + mock tabs from `data.tabs` |
| Each grid report POST `/api/reports/{key}/run` | `data.tabs.*.rows` |
| Last Order `C-1001` | SO-88021 |
| Duplicate People email | refused (no self-register) |
| Visibility off | card gone from `/` |
| Schedule Run now | sqlite outbox, not Graph |
| `/schedules/runs/{id}` | Time / Step / Detail log |
| External login copy | preview does not send mail; no “Send sign-in link” |
| xlsx | zip magic `PK` |
| `APP_ENV=production` | `/login/preview` 403 |
| `REPORTING_API_BASE_URL=https://reports.achimonline.com` | boot refuse |
| gunicorn UvicornWorker | `/healthz` 200 |
| Signed-in mutating POST without `X-CSRF-Token` | 403 |
| `next=` off-site | ignored, lands `/` |
| Disabled External row | magic-link 403 |
| Schedule Copy | extra row owned by signed-in user |
| `POST /api/dev/reporting/<id>/run` without key | 501 mock |
| Extra SalesGroup on a salesman | Last Order includes those customers |
| Per-report Allow | card stays when global visibility is off |
| Per-report Deny | card gone even when global is on |
| Item Averages Allow on salesman | still 404 (privileged_only) |
| Manager schedules list | company views only, not another user's personal |
| Schedule CC/filename/SharePoint | mock outbox body |
| `/master-schedules/{id}/history` | 200 for admin |
| `/dev/diagnostics` | P4.I8 blocked copy |
| PWA icons 192/512 | PNG magic |
| Dashboard flag | badge on Users, no Dashboard bottom nav |
| Delete own login | refused |
| Manager Run now | company schedules only, not another user's personal |
| Salesman schedule add | company view_id creates no row |
| Invoiced 2+ salesmen | Audit - Reversals + Totals by Salesman tabs |
| Invoiced salesman/customers | every tab (Full Details, Invoices, Commissions) matches the filter |
| Save view for another user | salesman sees the named view |
| views.params.group | must be a JSON array or omitted |
| Last Order store-visit | Recent invoiced helper + dedicated xlsx PK |
| Cancel running job | 200; finished job 409 |
| DB explorer write | Confirm required; DROP blocked; WITH+UPDATE needs confirm; group array |
| Schedule OneDrive folder | mock outbox body |
| Report chrome | customer picker, Columns, status, More |

Never set `REPORTING_API_KEY` in CI.

| Hidden report | company-view card gone from `/` |
| Salesman vs other user's job/schedule log | 404 / 302 |
| Salesman `/dev/role-picker` | 302 `/settings` |
| Exclusions | Last Order picker hides those accounts |

Never set `REPORTING_API_KEY` in CI.
