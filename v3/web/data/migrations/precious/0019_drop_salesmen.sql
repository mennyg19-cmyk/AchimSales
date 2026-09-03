-- The salesman master is D365 (rpt.usp_salesmen_master via the Reporting API).
-- Access rows (user_salesman_access) already store normalized keys with no FK
-- here (0018), and the last good SP list lives in cache.db, so nothing reads
-- this table any more.
DROP TABLE IF EXISTS salesmen;
