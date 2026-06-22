-- Throwaway database, first version.
-- report_snapshots holds one finished report result per cache key. If this file
-- is deleted the app rebuilds it automatically (see connection.cache()).

CREATE TABLE report_snapshots (
  cache_key TEXT PRIMARY KEY,
  report_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
