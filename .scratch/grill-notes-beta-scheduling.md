# Grill notes — Beta scheduling (2026-08-12)

## Goal
One Schedules page, one Add flow. Role decides which options exist. Sharing is explicit, not implied by company-wide settings.

## Locked decisions

### Page
- Title: **Schedules**. One **Add a schedule** button.
- **My schedules:** everyone sees their own (personal + private company-setting schedules they own).
- **Company schedules:** admins, developers, and managers. Sales reps never see this list.

### Wizard (one flow)
- Same 5 steps as today: Report → When → Options → Where → Review.
- **Sales reps:** always their own book. No split-by-salesman, no SharePoint, no share-with-company, no run-as-manager. Email + OneDrive only.
- **Managers + admins/developers:** extra options (SharePoint if they have access, split within the run’s scope, share vs private).
- **Admins/developers only:** **Run as a manager** picker (schedule uses that manager’s salesman/customer book). Unscoped company-wide run = no manager picked.

### Private vs shared
- Company-wide *settings* do **not** auto-share.
- Managers and admins get an explicit **Keep private** / **Share with admins and managers**.
- Share = who sees it on the company list, **not** a data upgrade.
- A manager-created shared schedule still runs in **that manager’s book**.
- Only admin/developer can run unscoped, or pick another manager’s scope.

### Company list edit rights
- **Admins/developers:** see and edit all shared schedules.
- **Managers:** see all shared schedules. **Edit** only if they **created** it or it is **scoped to them** (`run_as` = them). Otherwise read-only, with a note: they cannot edit — speak to an admin.
- Toggle/delete follow the same edit rule. History is visible. Run now is allowed if they can see the row.

### Destinations (unchanged)
- Personal/private: email + that user’s OneDrive.
- Shared/company settings may use SharePoint (when the user has access).
- Excel now; PDF later; no CSV.
- Monthly: 1–28 + last day; multi-day chips.

### Explicitly deferred
- PDF; SP/OD link in email body; dry-run; test-email Settings (still pending from earlier grill).

## Validation (done when)
1. Sales rep: Add a schedule → only personal options; list shows only theirs.
2. Manager: can share; shared row stays in their book; other managers see it read-only with the admin note unless it is theirs / scoped to them.
3. Admin: can pick a manager; that manager can edit; unscoped shared schedules are admin-edit only for managers.
4. Private + SharePoint/split does not appear on the company list.
5. Commit + push + `.\deploy.ps1`.
