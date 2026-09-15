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

Never set `REPORTING_API_KEY` in CI.
