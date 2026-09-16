"""Web-side report orchestration (plan section 7).

Turns a report request into a payload: Reporting API client -> source adapter ->
pure engine builder -> ONE scope-safe cache. Heavy runs are enqueued to the
durable job worker; this module stays free of business calculation rules (those
live in report_engine/, gated on human sign-off).
"""
