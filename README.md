# D365 Report Scripts

Refactored report codebase that pulls data directly from Dynamics 365 F&O via OData.

## Reports

| Report | Command | Output |
|--------|---------|--------|
| Ordered Report | `python run.py ordered` | Direct Reports/Ordered Report/{period}/ |
| Invoiced Report | `python run.py invoiced` | Direct Reports/Invoiced Report/{period}/ |
| Salesman Report | `python run.py salesman` | Direct Reports/Salesman Report/{period}/ |
| Number 4 Report | `python run.py number_4` | Direct Reports/Number 4 Report/By Item/{period}/ and By Customer/{period}/ |
| Amazon Weekly | `python run.py amazon_weekly` or `--email` | Direct Reports/Amazon Weekly/This Week/ |
| All Reports | `python run.py all` | All of the above |

## Periods

When run without arguments, each report generates all default periods: Daily, MTD, YTD, This Week.

A single smart fetch is made for the widest date range (YTD), then data is filtered in memory for narrower periods.

```
python run.py ordered                           # all periods
python run.py ordered --period daily            # single period
python run.py ordered --period mtd
python run.py ordered --from 2026-01-01 --to 2026-01-31  # custom range
python run.py ordered --date 2026-02-15         # single date
```

## Local Setup

1. Copy `.env.example` to `.env` and fill in your credentials
2. Install dependencies: `pip install -r requirements.txt`
3. Run from the `scripts/` directory: `python run.py ordered`

## Azure Runbook Setup

1. Upload the `scripts/` folder to Azure Automation
2. Configure Automation Variables: `D365_ENV_URL`, `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `SP_SITE_URL`, `DriveRootPath`
3. Run the appropriate runbook: `runbooks/runbook_ordered.py`, etc.

## Directory Structure

```
scripts/
  run.py                    # Unified CLI entry point
  .env.example              # Environment template
  requirements.txt          # Python dependencies
  D365_REFERENCE_LOG.md     # Entity/field reference for D365 validation
  config/
    settings.py             # Central config loader (Azure + .env)
    paths.py                # Output path resolution
    salesman_map.py         # Salesman lookup table
    commission_map.py        # Commission percentages
  core/
    auth.py                 # MSAL authentication (D365 + Graph)
    odata.py                # OData client with pagination + batching
    graph.py                # SharePoint Graph API client
    dates.py                # US Eastern date utilities + smart fetch
    columns.py              # Column detection + numeric conversion
    excel_styles.py         # Shared Excel styling constants
    excel_writer.py         # Shared Excel writing utilities
    logging.py              # Structured logging setup
    email_report.py         # Send report by email (Graph or SMTP)
  data/
    field_maps.py           # OData field rename maps + $select lists
    d365_entities.py        # Entity-specific fetch functions
  reports/
    base.py                 # Abstract base runner with CLI parsing
    ordered/                # Ordered Report
    invoiced/               # Invoiced Report
    salesman/               # Salesman Report
    number_4/               # Number 4 Report (By Item + By Customer)
    amazon_weekly/          # Amazon Weekly (customer 9300, this week, optional email)
  runbooks/
    base_runbook.py         # Shared runbook logic (run + upload)
    runbook_ordered.py
    runbook_invoiced.py
    runbook_salesman.py
    runbook_number_4.py
    runbook_amazon_weekly.py
  tests/
    compare_reports.py      # Cell-by-cell Excel comparison tool
```

## D365 Entity Reference

See `D365_REFERENCE_LOG.md` for every OData entity and field name used in this codebase.
Cross-reference against your D365 `$metadata` endpoint to verify field names match your environment.
