"""Report builders: typed facts -> multi-tab viewer payloads.

Pure functions. Each builder returns a list of tab dicts:

    {"key": str, "name": str, "columns": [{"field","header","type"}], "rows": [ {...} ]}

with an optional "layout" for non-tabular tabs (e.g. commission cards). Column
`type` is one of: text | int | money | percent | date - it drives both the
on-screen grid and the Excel export formatting. Column ORDER and HEADERS match
the LIVE app's exports; the MATH matches the LIVE app. Data SOURCE is the
Reporting API (test-app data path).
"""
