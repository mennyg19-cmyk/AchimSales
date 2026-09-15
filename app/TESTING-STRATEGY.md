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
| xlsx | zip magic `PK` |
| `APP_ENV=production` | `/login/preview` 403 |
| `REPORTING_API_BASE_URL=https://reports.achimonline.com` | boot refuse |
| gunicorn UvicornWorker | `/healthz` 200 |

Never set `REPORTING_API_KEY` in CI.
