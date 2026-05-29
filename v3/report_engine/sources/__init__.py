"""Source adapters: raw data-source rows -> typed facts.

Pure functions (no I/O, no Flask, no DB). The web layer fetches rows from the
Reporting API and hands them here; the CLI/runbook path can hand the same
shapes from OData. Builders consume only the facts these produce, so report
math never depends on which source the rows came from.
"""
