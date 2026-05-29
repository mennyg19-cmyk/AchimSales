"""Data layer: two SQLite databases behind repository interfaces.

- precious.db : durable app state (users, permissions, salesmen, presets,
  schedules, run history, notifications, jobs). Litestream-replicated in prod.
- cache.db    : disposable D365 mirror + report payload cache. Never replicated;
  fully rebuildable from the Reporting API.

Repository interfaces (repositories/) keep the rest of the app ignorant of SQLite
so Postgres is a drop-in later (plan section 6 off-ramp).
"""
