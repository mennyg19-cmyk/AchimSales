-- Durable database, first version.
-- app_meta is a tiny key/value store for things like "schema seeded at" and
-- the one-time legacy-import marker. Real feature tables (users, jobs,
-- schedules, report config, audit) arrive in later numbered migrations.

CREATE TABLE app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
