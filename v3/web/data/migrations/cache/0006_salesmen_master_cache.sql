-- Last good copy of the salesmen_master SP (rpt.usp_salesmen_master). Rebuilt
-- wholesale on every successful fetch; read when a worker boots before the SP
-- has answered or while it is down. Not a master you edit: D365 is.
CREATE TABLE IF NOT EXISTS salesmen_master_cache (
    salesman        TEXT PRIMARY KEY,                    -- raw SalesGroup
    name            TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    commission_pct  REAL NOT NULL DEFAULT 0,             -- fraction (0.06 = 6%)
    refreshed_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
