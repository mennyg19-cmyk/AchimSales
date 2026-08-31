-- Per-user gate for named company views (Daily Ordered, Heshy Open Orders,
-- Home cards, Saved views, schedule wizard). Default off; developers on.
ALTER TABLE users ADD COLUMN can_see_company_views INTEGER NOT NULL DEFAULT 0;
UPDATE users SET can_see_company_views = 1 WHERE role = 'developer';
