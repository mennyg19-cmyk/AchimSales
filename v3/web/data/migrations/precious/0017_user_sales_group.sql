-- Raw D365 SalesGroup on the login (same string as report salesman filters).
-- Access rows stay on user_salesman_access as normalized keys.
ALTER TABLE users ADD COLUMN sales_group TEXT NOT NULL DEFAULT '';
