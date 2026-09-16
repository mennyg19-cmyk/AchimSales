# What we changed on 2 September 2026

This is a plain-English list of everything that landed in the Achim Sales Reports app today (the live site at https://reports.achimonline.com). It is written for a human, not for another programmer.

**Production copies from the `main` branch.** A pull request is a proposed photocopy. Until it is merged into `main`, Azure does not pick it up.

At the time this file was written:

- Pull requests **#11 through #32** were already on `main` (already live, or live as soon as Azure finished those deploys).
- Pull request **#33** (the security / review fixes) was still waiting to merge. The next step after this report is to merge #33 into `main`.

---

## Can we see the database changes you made today?

**The short answer: no, not the actual rows you typed into the live site.**

Git (the history of the *code*) does not record what you clicked in Users & access, which schedules you saved, or which views you renamed. Those live in a SQLite file on the Azure App Service, not in GitHub.

This cloud machine also has **no Azure login**, so it cannot open the production database or Litestream backups.

What we *can* see from git is **schema** (the shape of the tables), not your data:

| Change | What it means in English |
|--------|--------------------------|
| Migration `0017_user_sales_group.sql` | Each login gained a `sales_group` text field. That is the same SalesGroup string the report filters send to Dynamics. |
| Migration `0018_usa_drop_salesmen_fk.sql` | The “which salesmen can this login see” table no longer requires a matching row in the old `salesmen` table. You can grant a customer-master SalesGroup without inventing a dummy salesman row. |

Local `.db` files under `.scratch/` on this machine are **throwaway review databases**. They are not production and they are not a log of your day’s edits.

If you need a list of “what I changed in the live database today,” that has to come from Azure (App Service file / Litestream replica) or from notes you kept while clicking. I cannot invent that list.

---

## Already on `main` today (PRs #11–#32)

Grouped by what you actually see, not by pull-request number.

### Users & access

- **Rename people.** Edit user now has Display name. Saving it sticks. Login email does not change. Microsoft login will not overwrite a name you already set.
- **SalesGroup on a salesman login.** For salesman role only, SalesGroup is a dropdown filled from the same lookup the reports use (`GET /api/admin/sales-groups`). Managers still use checkboxes for which salesmen they can see.
- **Company views permission** (earlier today). Seeing company views can be gated per user. Later, admins and developers were allowed to manage company views even without that flag (see below).
- **Switch user / save for someone else.** Admins can save a named view onto another user’s account without impersonating them. Switch user lists people from both the old Live directory and the v3 users table, so a newly added salesman is not invisible. Creating a salesman/manager whose email matches an active salesman row auto-checks that salesman for access.

### Reports on screen

- **Salesman report filter.** Same Salesman dropdown Ordered already had. It filters rows after fetch (by aliases), and still respects the user’s salesman scope. It does **not** send the SalesGroup token into the stored procedure as `SalesmanName` (that would often return zero rows).
- **Daily Ordered grouping.** Group by salesman, then customer. No period stored on that company view. **By Customer** is salesman-only. **By Order** is ungrouped.
- **Saved views.** Company and personal views collapse in the Saved views panel. Applying a saved view no longer throws `_isDuplicate`. Company views can be deleted from that panel if you are allowed to edit company views. Salesmen who can only *see* company views still cannot delete them.
- **Admins/developers and company views.** Privileged users always see and can create/edit/delete company views. They can schedule from **Default**. Salesmen/managers still need a named view unless they have the company-views flag (managers keep edit/delete when they have the flag).
- **Customer Activity scheduling.** Named personal Customer Activity views can be scheduled even with no period selected. Empty params are not treated as a custom date range. Default, company views, and custom from/to stay off that list. Company monthly CA schedules are unchanged.
- **Settings customer exclusions.** The exclusion list is filled from the same customer list the reports use.
- **Ordered Summary** gained **Extended Price Cancelled**.
- **Number 4.** Column order is months then totals; By Item uses dollars. Ungrouped Number 4 Default is honoured in emailed workbooks.

### Personal and company schedules

- **Personal schedules are full width**, same as company schedules (the 800px cap is gone).
- **One table for everyone’s personal schedules.** Owner name is a banner row so Avi / Heshy / Mendy columns line up.
- **CC and BCC** when an admin edits a personal schedule or uses More → Schedule. The salesman themselves still only emails themselves; the extra fields are privileged.
- **New filename default** is `{Schedule}_{MM}-{DD}-{YYYY}`. Existing saved templates are not rewritten. Same-day reruns of the same schedule can overwrite because the clock time is gone from the default.
- **Personal schedules from named saved views**; company wizard lives under Settings (from earlier today).
- **Fail mail** waits so a retry success can replace a failure notice (home-site extra delivery).
- **Oversized Number 4 mail** includes a SharePoint / download link when the file is too big to attach, including after chunked Graph uploads that omit `webUrl`.

### Excel files

- **Do not total Net Price** on Ordered group footers (Net Price is Extended / Qty; summing it is a fake number). Number 4 Avg/Book Price still sums.
- **Nested header/footer colours.** Greys on footers (darker further out), blues on headers, white vs dark text by contrast. Grid and Excel share the same RGB.
- **Salesman Excel bands** colour by field name, not Excel column letter, so hidden columns do not paint the wrong band.
- **Outline groups were added, then rolled back.** You did not want the collapse gutter. Innermost footer grey was too close to white; it is darker now (`#9CA3AF` for 2-level customer totals, not `#E5E7EB`).

### Deploy / scanning (not user-visible, but it happened today)

- Official branch renamed to **`main`**. Azure deploys **only from `main`**.
- Agent Guardrails Semgrep scans live `v3/` only, not the old `/legacy` webapp, and skips noisy rules that do not match this Flask + SQLite app.

---

## Pull request #33 — review fixes (merging after this report)

This is the large “make go-live safe” patch. It was reviewed with Flask’s test client and pytest against an **isolated sqlite**, not by clicking the live website.

### Security and login

- **GET no longer deletes or mutates** the precious-repair diagnostic. Delete-ghosts and other mutating actions are POST with CSRF. GET may only `action=check`.
- **Missing user on salesman/report-access** returns 404, not a raw SQLite 500.
- **Live (Microsoft) login vs Users & access.** The first time someone signs in through Live, v3 still creates their row and copies salesman scope. After that, the Live cookie **does not overwrite** display name, role, SalesGroup, external flag, or salesman-access. So renaming someone or changing their role in Users & access actually sticks on the Beta/Live site.
- **Developer tools and Switch user** require a real `developer` row in the database, not an old `_dev` cookie left in the browser.
- **Leftover impersonation.** If an admin was “View as” someone and then that developer is demoted, the leftover cookie does not keep developer powers. It becomes the actor’s own identity, or logs out if that row is gone.
- **A developer’s first Live login** still creates the developer row. It must not bounce to logout and wipe the shared Live session.
- **Export download** re-checks salesman scope after demotion, so a demoted admin cannot keep downloading a company-wide workbook they started earlier.
- **claim-once** (schedule runner claiming a job) is POST-only and only succeeds if exactly one row was updated.

### Who may create or destroy a developer

- Only a database **developer** can create, change, **disable, or delete** a developer login. Admins cannot mint themselves as developers, and cannot delete a developer and re-add the same email as a salesman.
- **Nobody can change their own role.**
- **Add user** on an email that already exists returns **409** (“User already exists; edit them instead”), instead of silently overwriting the row.
- **`/test` impersonate** is developer-only. If the real impersonation actor is not an active developer, session refresh logs out.
- Delete confirm text: “To block sign-in without wiping data, Disable them instead.” **Accepted risk:** Delete only removes v3 data. A still-valid Live cookie can recreate the row from Live’s role. Disable sticks.

### Small craft fixes bundled in the same PR

- One shared “is this an active developer row?” check.
- Settings “developer?” uses that same check.
- Export list applies salesman scope **before** the 15-item cap (so you do not lose in-scope files because out-of-scope ones filled the list).
- Non-string precious-repair action → 400.

---

## What we did *not* do in a browser today

The review that produced PR #33 used automated tests (633 passed, 1 skipped) talking to Flask in-process. That is not the same as opening https://reports.achimonline.com and clicking every screen.

After #33 is on `main` and Azure is green, the next work is:

1. Inventory every live-site page and control (rebuild protocol Phase 0–1 on **live `v3/`**, not a from-scratch rewrite).
2. Click through every inventory item in a real browser.
3. Read schedules from a database we *can* reach (local test copy, or production if Azure access appears), run them, and check Excel / mail files against what they are supposed to be.

---

## Pull request index (today)

| PR | Title (GitHub) |
|----|----------------|
| #11 | Gate company views behind a per-user permission |
| #12 | Include a download link when the workbook is too big to attach |
| #13 | Add Extended Price Cancelled to Ordered Summary |
| #14 | Honour ungrouped Number 4 Default in emailed workbooks |
| #15 | Hold fail mail until a retry success can replace it |
| #16 | Scan only live v3; skip noisy Semgrep rules |
| #17 | Fix Number 4 column order: months then totals, dollars on By Item |
| #18 | Personal schedules from named saved views; company wizard under Settings |
| #19 | Put a SharePoint download link on oversized Number 4 mail |
| #20 | Group Daily Ordered by salesman then customer; no period on the view |
| #21 | Fix salesman Excel colors when columns are hidden |
| #22 | Daily Ordered: By Customer salesman-only, By Order ungrouped |
| #23 | Fix `_isDuplicate` error when applying a saved view |
| #24 | Make personal schedules full width like company schedules |
| #25 | Settings exclusions use the report customer dropdown |
| #27 | Ordered groups: no Net Price totals, nested header/footer shades |
| #28 | Schedule Customer Activity views; drop Excel outline groups; darken footer grey |
| #29 | Personal schedule CC/BCC, filename default, and admin save-for-other-user |
| #30 | Align schedule columns; add SalesGroup on salesman users |
| #31 | Salesman filter, company views, and Default schedules |
| #32 | Let admins rename users on Users & access |
| #33 | Fix review findings: CSRF, Live login, impersonation, developer-role boundary |

PR #26 was folded into another branch and closed; it is not a separate merge.
