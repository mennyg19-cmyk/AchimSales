-- New views/layout/schedule tables beside the JSON blobs.
-- Old saved_reports / company_views / report_defaults / schedules / master_schedules stay.
-- users.handle is the readable id; integer users.id remains for old FKs.

ALTER TABLE users ADD COLUMN handle TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_handle ON users(handle);

CREATE TABLE views (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('personal', 'company', 'default')),
    report_key TEXT NOT NULL,
    name TEXT NOT NULL,
    owner_handle TEXT REFERENCES users(handle) ON DELETE CASCADE,
    period TEXT,
    start_date TEXT,
    end_date TEXT,
    year TEXT,
    mode TEXT,
    active_tab_key TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by_handle TEXT REFERENCES users(handle) ON DELETE SET NULL,
    legacy_source TEXT,
    legacy_id INTEGER,
    CHECK (kind <> 'personal' OR owner_handle IS NOT NULL),
    CHECK (kind = 'personal' OR owner_handle IS NULL)
);

CREATE UNIQUE INDEX views_default_report ON views(report_key) WHERE kind = 'default';
CREATE UNIQUE INDEX views_company_name ON views(report_key, name) WHERE kind = 'company';
CREATE UNIQUE INDEX views_personal_name ON views(owner_handle, report_key, name) WHERE kind = 'personal';
CREATE UNIQUE INDEX views_legacy ON views(legacy_source, legacy_id)
    WHERE legacy_source IS NOT NULL AND legacy_id IS NOT NULL;

CREATE TABLE view_salesmen (
    id TEXT PRIMARY KEY,
    view_id TEXT NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    salesman TEXT NOT NULL,
    UNIQUE (view_id, salesman)
);

CREATE TABLE view_statuses (
    id TEXT PRIMARY KEY,
    view_id TEXT NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    UNIQUE (view_id, status)
);

CREATE TABLE view_customers (
    id TEXT PRIMARY KEY,
    view_id TEXT NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    customer_account TEXT NOT NULL,
    UNIQUE (view_id, customer_account)
);

CREATE TABLE layout_tabs (
    id TEXT PRIMARY KEY,
    view_id TEXT NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    tab_key TEXT NOT NULL,
    position INTEGER,
    clone_of_tab_key TEXT,
    tab_name TEXT,
    has_view INTEGER NOT NULL DEFAULT 0 CHECK (has_view IN (0, 1)),
    UNIQUE (view_id, tab_key)
);

CREATE TABLE layout_tab_groups (
    id TEXT PRIMARY KEY,
    tab_id TEXT NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    UNIQUE (tab_id, position)
);

CREATE TABLE layout_tab_sorters (
    id TEXT PRIMARY KEY,
    tab_id TEXT NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    dir TEXT NOT NULL CHECK (dir IN ('asc', 'desc')),
    UNIQUE (tab_id, position)
);

CREATE TABLE layout_columns (
    id TEXT PRIMARY KEY,
    tab_id TEXT NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    position INTEGER,
    hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
    frozen INTEGER NOT NULL DEFAULT 0 CHECK (frozen IN (0, 1)),
    width REAL,
    UNIQUE (tab_id, field)
);

CREATE TABLE layout_column_filters (
    id TEXT PRIMARY KEY,
    tab_id TEXT NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    op TEXT NOT NULL DEFAULT 'contains',
    v TEXT,
    v2 TEXT,
    UNIQUE (tab_id, field)
);

CREATE TABLE report_schedules (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('personal', 'company')),
    view_id TEXT NOT NULL REFERENCES views(id) ON DELETE RESTRICT,
    owner_handle TEXT REFERENCES users(handle) ON DELETE SET NULL,
    name TEXT NOT NULL DEFAULT '',
    freq TEXT NOT NULL CHECK (freq IN ('daily', 'weekly', 'monthly')),
    time TEXT NOT NULL DEFAULT '08:00',
    window_period TEXT,
    window_start TEXT,
    window_end TEXT,
    sharepoint_path TEXT NOT NULL DEFAULT '',
    filename_template TEXT NOT NULL DEFAULT '',
    folder_kind TEXT NOT NULL DEFAULT 'onedrive'
        CHECK (folder_kind IN ('onedrive', 'sharepoint')),
    email_subject TEXT NOT NULL DEFAULT '',
    email_html TEXT NOT NULL DEFAULT '',
    email_on_no_data INTEGER NOT NULL DEFAULT 0 CHECK (email_on_no_data IN (0, 1)),
    email_on_no_data_me_only INTEGER NOT NULL DEFAULT 0
        CHECK (email_on_no_data_me_only IN (0, 1)),
    split_by_salesman INTEGER NOT NULL DEFAULT 0 CHECK (split_by_salesman IN (0, 1)),
    email_to_salesmen INTEGER NOT NULL DEFAULT 0 CHECK (email_to_salesmen IN (0, 1)),
    skip_sabbath INTEGER NOT NULL DEFAULT 1 CHECK (skip_sabbath IN (0, 1)),
    run_as_handle TEXT REFERENCES users(handle) ON DELETE SET NULL,
    is_shared INTEGER NOT NULL DEFAULT 1 CHECK (is_shared IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    active_from TEXT,
    active_until TEXT,
    catch_up_pending INTEGER NOT NULL DEFAULT 0 CHECK (catch_up_pending IN (0, 1)),
    catch_up_for_date TEXT,
    last_claimed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    legacy_kind TEXT NOT NULL,
    legacy_id INTEGER NOT NULL,
    UNIQUE (legacy_kind, legacy_id)
);

CREATE TABLE schedule_weekdays (
    schedule_id TEXT NOT NULL REFERENCES report_schedules(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    PRIMARY KEY (schedule_id, weekday)
);

CREATE TABLE schedule_monthdays (
    schedule_id TEXT NOT NULL REFERENCES report_schedules(id) ON DELETE CASCADE,
    monthday INTEGER NOT NULL CHECK (monthday = -1 OR (monthday BETWEEN 1 AND 28)),
    PRIMARY KEY (schedule_id, monthday)
);

CREATE TABLE schedule_recipients (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL REFERENCES report_schedules(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('to', 'cc', 'bcc')),
    UNIQUE (schedule_id, email, role)
);

CREATE TABLE schedule_email_salesmen (
    schedule_id TEXT NOT NULL REFERENCES report_schedules(id) ON DELETE CASCADE,
    salesman TEXT NOT NULL,
    PRIMARY KEY (schedule_id, salesman)
);
