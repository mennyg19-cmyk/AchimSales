"""Shared, pure report engine for the v3 Sales Reports app.

Top-level package (rule 3): importable by both the web app and any CLI/runbook
automation, so report math is never duplicated. Nothing here may import Flask,
the database, or perform I/O - sources/ adapters turn raw rows into typed facts,
and reports/ builders turn facts into tab payloads. All inputs come in as plain
data; all outputs are plain data.
"""
