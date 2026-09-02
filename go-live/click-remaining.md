# Remaining click-through (batch 3+)

Local app: `http://127.0.0.1:5055` — `python3 /workspace/.scratch/golive_serve.py`
Login: `/login` email `golive-dev@local.test` role **developer**. CSRF is on the form.

Do **not** start rebuild Phase 2–4. Do **not** invent D365 data. If a control needs API data, screenshot the empty/error state and move on.

Write results to `/workspace/.scratch/click-batch-3.md` (parent will copy to `go-live/`).

## Must retest

1. **P6** open `/settings/company-schedules` directly. Screenshot the table (expect 12 seeded names). Open 5-step wizard far enough to see Report → When → Options → Where → Review. Do not need to save a 13th company schedule unless save is one click and clearly succeeds.
2. **P3.16 Schedule modal** from `/reports/ordered` **without** `cview`. Wait for Saved views / Default. Open More → Schedule. Screenshot `#scheduleModal` (title “Schedule this view”, filename field, Email to me). If the button is disabled, screenshot the hint text. Then try Saved views → Default if needed.
3. **P5 save** complete Add a schedule through Save so a row appears on `/schedules`. Then History, Copy (if enabled), toggle on/off. **Run now** is expected to fail locally (no Reporting API) — screenshot the error, do not treat as a product bug.

## Still unchecked UI

4. **P8.3** Edit `golive-sm2@local.test`: change display name, save. Salesmen master table (likely empty).
5. **P7** Settings: exclusions picker; feature flags; report visibility; Delivery test-mode chips; Developer Beta SQL/OData sources page.
6. **P13** `/dev/role-picker` — search, pick golive-sm2, View as. Header “Viewing as”. End via Switch user → yourself or Sign Out + re-login as golive-dev.
7. **P14** `/impersonate` if the route loads (this mount is AUTH_MODE=dev). If 404, note it.
8. **C10** Help overlay on reports home.
9. **C6** theme cycle light → dark → monochrome → monochrome_dark (or whatever the toggle actually does) and back.
10. **P9** dashboard: empty tiles already seen; open a customer link if any row exists; otherwise screenshot empty table.
11. **P4.3** type a letter in last-order search; screenshot empty/loading. Do not fake a customer.
12. **P5.2** after save, privileged table with owner banner.
13. **P6.7** one master row: History page. Run now → expect API-not-set failure.
14. **Salesman gate:** login as `golive-sales@local.test` salesman (Sign Out, then `/login/dev` — not only Switch user). Confirm no Users, no Dashboard, Settings = Profile/Appearance/Exclusions. Hit `/admin/users` — expect 403 JSON (F18).

Skip Run report expecting rows. Skip CLO Excel/PDF without a customer account.
