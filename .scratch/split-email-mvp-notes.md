# Split + email MVP notes

Date: 2026-07-25

## Deployed
Azure RuntimeSuccessful — https://reports.achimonline.com/test

## Shipped
- Salesmen admin: email column + edit modal (`salesmen.email`)
- Company schedules on `/schedules#company`; `/master-schedules` → redirect
- Settings: link only
- Wizard step 4: filtered → email selected; unfiltered → split + multi-select
- Fan-out: full workbook to typed/SP; per-salesman files to `salesmen.email`
- Missing salesman email = skip + History note (run still succeeds)
- **Graph send** preferred (fixes Friday): uses `GRAPH_*` + `EMAIL_FROM_ADDRESS`; SMTP fallback; else outbox-only

## Friday root cause
App Settings had Graph + `EMAIL_FROM_ADDRESS`, **no** `SMTP_*`. v3 only SMTP → outbox “success”, no inbox.

## Manual proof on /test
1. Users & access → set salesman emails
2. Schedules → My + Company; Settings link only
3. Ordered: 2 salesmen + email them + own email → Run now
4. Unfiltered: split + multi-select
5. History: `sent_smtp` true after Graph send
