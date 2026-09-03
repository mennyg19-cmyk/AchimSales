# Remaining click-through (batch 5)

Local app: `http://127.0.0.1:5055`
Sign Out if needed, then `/login` as `golive-dev@local.test` role **developer**.

Do **not** FAIL salesman “Viewing as” on `/login/dev` — that badge is expected in AUTH_MODE=dev (`is_dev=True`). Skip salesman login this batch.

Write `/workspace/.scratch/click-batch-5.md`. Stay under ~7 minutes.

## Do these (still unchecked in the browser)

1. **P13 radio:** `/dev/role-picker` — search golive-sm2, **click the radio** on Test Salesman 2 (View as Selected User stays disabled until you do), then submit. Header Viewing as Test Salesman 2. Then “View as Admin (yourself)” back to developer.
2. **P7** `/settings`: exclusions (“Customer master is not configured” is OK); feature flags; report visibility toggles; Delivery test-mode + email chips; Developer Beta SQL/OData sources. Screenshot each section opened, do not need to persist flag changes.
3. **C10** on `/` open Help overlay (the `?` / help control). Screenshot open + close.
4. **C6** click the header theme button through light → dark → monochrome → monochrome_dark (or however many distinct looks) and screenshot each. Leave it on dark.
5. **P4.3** `/report/customer-last-order` type `a` in customer search. Screenshot empty/loading. No fake account.
6. **P6.7** `/settings/company-schedules` — History on Daily Ordered Report; Run now on that row → expect `REPORTING_API_BASE_URL/KEY not set`.
7. **P9** `/dashboard` as developer: screenshot empty table/tiles.

Skip Run report rows. Skip CLO Excel/PDF.
