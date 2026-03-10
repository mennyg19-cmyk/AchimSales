# Amazon Weekly Report – Setup & Scheduling

## What this report does

- **Customer:** 9300 (Amazon) only, via **direct OData** `$filter` on `SalesOrderHeadersV3` (no pull-then-filter).
- **Period:** Last 7 days (rolling), not just the business week. When run on Friday, it’s the prior 7 days including that day.
- **Content:** Same dataset as the Ordered Report: what was **ordered**, **shipped**, **cancelled**, and **remaining** for Amazon.
- **Output:** One Excel file: `Direct Reports/Amazon Weekly/This Week/Amazon_Weekly_Report_Week_YYYY-MM-DD_to_YYYY-MM-DD.xlsx`.
- **Email:** Optional. If configured, the report can be attached and sent to a list of recipients (e.g. every Friday 5pm).

## Run locally

From the `scripts` folder (or with `scripts` on `PYTHONPATH`):

```bash
# Generate report only (no email)
python run.py amazon_weekly

# Generate report and send email (if email is configured)
python run.py amazon_weekly --email
```

Or run the module directly:

```bash
python -m reports.amazon_weekly.runner
python -m reports.amazon_weekly.runner --email
```

Requires the same D365 config as other reports: `D365_ENV_URL`, `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` (and optional `D365_COMPANY_ID`). See main `README.md` and `.env.example`.

**Customer PO (Customer Requisition):** The report includes a “Customer Requisition” column (customer PO number) from sales order headers. The script requests `CustomerRequisitionNumber` from **SalesOrderHeadersV3**. If your D365 environment uses a different field name (e.g. `OrderingCustomerExternalDescription`), or the report fails with an OData error about an invalid property, edit `data/field_maps.py`: in `SALES_ORDER_HEADER_SELECT` replace or add the correct OData field name, and in `SALES_ORDER_HEADER_FIELD_MAP` add a mapping from that name to `CustomerRequisition`.

## Email configuration

Recipients: set **`AMAZON_EMAIL_RECIPIENTS`** (comma- or semicolon-separated addresses). If empty, no email is sent.

You can send via **Microsoft Graph** (recommended for business) or **SMTP**. The script tries Graph first if configured, then SMTP.

### Option A – Microsoft Graph (recommended; no app password)

Uses the **same app registration** as D365/SharePoint (`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`). No user password or app password needed.

| Variable                   | Description |
|----------------------------|-------------|
| `AMAZON_EMAIL_FROM`        | The mailbox to send *from* (user principal name, e.g. `reports@company.com` or a shared mailbox address). |

**One-time setup (IT / admin):**

1. In **Azure Portal** → **App registrations** → your app (the one used for D365/Graph).
2. **API permissions** → Add permission → **Microsoft Graph** → **Application permissions**.
3. Add **Mail.Send** (allows the app to send mail as any user in the org).
4. Click **Grant admin consent for &lt;tenant&gt;**.
5. The app can then send mail “as” the mailbox you put in `AMAZON_EMAIL_FROM` (e.g. a shared mailbox or `reports@company.com`). No password for that mailbox is needed in the script.

If Graph send fails (e.g. permission not yet granted), the script falls back to SMTP when SMTP_USER and SMTP_PASSWORD are set.

### Option B – SMTP (fallback)

| Variable           | Description |
|--------------------|-------------|
| `SMTP_USER`         | From address and SMTP login. |
| `SMTP_PASSWORD`     | Account password or app password (see below). |
| `SMTP_HOST`         | Optional; default `smtp.office365.com`. |
| `SMTP_PORT`         | Optional; default `587`. |

- **No MFA:** Use the account’s normal password; ensure “Authenticated SMTP” is enabled for that mailbox if required.
- **MFA (personal account):** Create an App password at [account.microsoft.com/security](https://account.microsoft.com/security) → App passwords.
- **MFA (business account):** Many orgs disable app passwords. Use **Option A (Graph)** above, or ask IT for a shared/service mailbox without MFA that can use SMTP.

If `AMAZON_EMAIL_RECIPIENTS` is set but neither Graph nor SMTP is configured, the script logs a warning and skips sending.

## Schedule: every Friday at 5pm

### Option A – Windows Task Scheduler (on a PC that runs at 5pm Friday)

1. Open **Task Scheduler**.
2. Create Task:
   - **Trigger:** Weekly, Friday, 5:00 PM.
   - **Action:** Start a program.
     - Program: `python` (or full path to your Python executable).
     - Arguments: `run.py amazon_weekly --email` (adjust if you use a different working directory).
     - Start in: folder that contains `run.py` (e.g. `...\D365 F&O\scripts`).
3. Ensure the machine is on and logged in at 5pm Friday (or use a server/service account that’s always on).

### Option B – Azure Automation (runbook)

**Why the runbook file lives under `scripts/`:** In your repo, `scripts/runbooks/runbook_amazon_weekly.py` sits next to `scripts/reports/`, `scripts/config/`, etc., so when you run locally, Python finds everything. Azure only has the one runbook file. So the runbook **downloads only what the Amazon Weekly report needs** from SharePoint (config, core, data, reports/ordered, reports/amazon_weekly, runbooks/base_runbook), runs the report, then uploads Direct Reports. Other reports and scripts are not downloaded—fastest and no impact on the rest.

**One-time: have the scripts folder in SharePoint**

The runbook downloads from **D365 F&O/scripts** (or whatever you set in **AMAZON_WEEKLY_SCRIPTS_PATH**). It only fetches: **config/** (all), **core/** (all), **data/** (all), **reports/__init__.py**, **reports/ordered/** (all), **reports/amazon_weekly/** (all), **runbooks/__init__.py**, **runbooks/base_runbook.py**. So SharePoint must have **D365 F&O/scripts** with that structure (e.g. from syncing or uploading your repo). Other report folders (invoiced, salesman, number_4) are not downloaded.

**Configure and schedule the runbook**

1. Use the same Azure Automation account and variables as your other runbooks (`D365_ENV_URL`, `GRAPH_*`, `SP_SITE_URL`, `DriveRootPath`).
2. In Azure Automation, create or edit the **Amazon Weekly** runbook and paste in the **full contents** of `scripts/runbooks/runbook_amazon_weekly.py`. Save and Publish.
3. Add variables for email if you want: `AMAZON_EMAIL_RECIPIENTS`, and either `AMAZON_EMAIL_FROM` (Graph) or `SMTP_USER` / `SMTP_PASSWORD`.
4. Create a schedule: Weekly, Friday, 5:00 PM (Eastern), and link it to the Amazon Weekly runbook.

When the runbook runs, it downloads the scripts folder from SharePoint (all directories and files), runs the report (and sends email if configured), then uploads Direct Reports to SharePoint.
