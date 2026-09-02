# Remaining click-through (batch 4)

Local app: `http://127.0.0.1:5055`
Start at `/login`. If already in a session, **Sign Out first**.

REQUIRED: true salesman login this time — Sign Out, then `/login` email `golive-sales@local.test` role **salesman**. Header must **not** say “Viewing as”. After that item, Sign Out and login `golive-dev@local.test` role **developer** for the rest.

Write `/workspace/.scratch/click-batch-4.md`. Stay under ~7 minutes. No D365 waits >8s.

## Do these (skipped from batch 3)

1. **Salesman true login:** after Sign Out + `/login/dev` as salesman, screenshot header (no Viewing as). Settings = Profile/Appearance/Exclusions. `/admin/users` → 403 JSON. `/dashboard` — note whether it loads or hides (F2: nav hidden, route may still 200).
2. **P14** `/impersonate` as developer after re-login. If 404, record that. If it loads, click one user and End if there is an End control.
3. **P13** `/dev/role-picker` — search golive-sm2, View as, header Viewing as Test Salesman 2 / golive-sm2. Then Sign Out or View as yourself back to golive-dev.
4. **P7** `/settings` as developer: open exclusions (expect “Customer master is not configured”); feature flags; report visibility toggles; Delivery test-mode + email chips; Developer Beta SQL/OData sources.
5. **C10** Help overlay on `/` (reports home).
6. **C6** click the theme control through its cycle (light / dark / mono if present) and screenshot each distinct look. Return to dark if that was the start.
7. **P4.3** `/report/customer-last-order` — type `a` in customer search; screenshot empty/loading. Do not invent an account.
8. **P6.7** `/settings/company-schedules` — History on Daily Ordered Report; Run now on one row → expect API-not-set. Screenshot.
9. **P9** `/dashboard` as developer: empty tiles already seen; screenshot table empty state. If a customer link exists, open it.

Skip Run report rows. Skip CLO Excel/PDF.
