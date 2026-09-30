-- Tabs and columns last seen when a report was built from the Reporting API.
-- The formatter offers these. A later run updates tabs it returned and
-- replaces that tab's columns. Tabs this run did not return stay.

CREATE TABLE IF NOT EXISTS report_catalog_tabs (
    report_key TEXT NOT NULL,
    tab_key TEXT NOT NULL,
    tab_name TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (report_key, tab_key)
);

CREATE TABLE IF NOT EXISTS report_catalog_columns (
    report_key TEXT NOT NULL,
    tab_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    field TEXT NOT NULL,
    header TEXT NOT NULL,
    PRIMARY KEY (report_key, tab_key, field)
);
