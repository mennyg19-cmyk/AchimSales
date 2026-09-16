"""Delivery subsystem (Phase C): apply a saved grid layout to a report payload,
export it to Excel, and deliver via email (outbox / SMTP) and/or SharePoint.

Pure-ish core (`layout`, `service`) is decoupled from Flask so the same code
path serves both the interactive "email now" action and unattended scheduled
runs.
"""
