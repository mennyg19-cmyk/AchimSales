# Report pipeline notes

## Background

The report routes accept filters from the browser, enforce the signed-in
user's permissions, fetch report data, shape it into tabs, and return it to
the report grid. The same result can also be turned into an Excel file or an
email.

The main path is:

```text
routes_reports.report_run
  -> reports.build_payload
    -> scope the submitted parameters
    -> choose mock data or the Reporting API
    -> apply viewer filters and column metadata
  -> save the completed result as a job
  -> return the result to the browser
```

The request parameters and the response payload are different:

- Parameters are the user's filters, such as dates, salesperson, and
  customers.
- The payload is the completed report result: rows, tabs, columns, filters,
  and source metadata.
- A saved job stores that completed payload as JSON so it can be recalled
  without calling the Reporting API again.

## Why the code can feel like spaghetti

The behavior is mostly in the right order, but several responsibilities are
packed behind similar names:

- `routes_reports._build_payload()` is only a pass-through wrapper.
- `reports.build_payload()` scopes permissions, chooses the data source,
  fetches data, applies filters, and shapes the result.
- `payload` sounds like request data even though it is the result returned by
  the report builder.
- Authorization happens at more than one level. The route checks whether the
  user may access the report, while the report builder narrows the user's
  salesperson scope before making the external request.

That makes the code harder to trace even though the security order is
important:

```text
check report access
  -> restrict user parameters
    -> call the data source
      -> shape and filter returned rows
        -> return the completed result
```

## Possible future improvement

If this area is changed later, make the stages explicit instead of putting
them under one `build_payload()` name. A clearer design would separate:

```text
authorize_report(user, report)
scope_report_parameters(user, parameters)
fetch_report_data(report, scoped_parameters)
format_report_result(report, raw_data, scoped_parameters)
```

The route wrapper could then be removed unless it gains real route-specific
behavior.

This would improve:

- Readability: each function would have one obvious job.
- Security review: the point where parameters are narrowed would be easy to
  find.
- Reuse: grid, Excel, and email could share the same fetch and formatting
  stages without hiding them behind a generic name.
- Testing: permission scoping, data-source selection, and formatting could be
  tested separately.

## Constraints for a future change

- Keep report access checks before any external request.
- Keep salesperson and other row-level restrictions in the parameters sent
  to the Reporting API.
- Keep the result format stable for the grid, saved jobs, Excel export, and
  email delivery.
- Do not add a second copy of the report rows to the database. The saved job
  payload already contains the result.

This is a refactoring note, not a request to change the current behavior.
