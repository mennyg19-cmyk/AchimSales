-- SharePoint files already live under Direct Reports. Stored paths that
-- repeated that folder name were creating Direct Reports/Direct Reports/...
UPDATE master_schedules
SET sharepoint_path = trim(substr(sharepoint_path, length('Direct Reports/') + 1), '/')
WHERE lower(sharepoint_path) LIKE 'direct reports/%';
UPDATE master_schedules
SET sharepoint_path = trim(substr(sharepoint_path, length('Direct Reports/') + 1), '/')
WHERE lower(sharepoint_path) LIKE 'direct reports/%';
UPDATE master_schedules
SET sharepoint_path = ''
WHERE lower(sharepoint_path) = 'direct reports';

UPDATE master_schedules
SET sharepoint_path = 'Salesman Report/Customer Activity/{Month} {YYYY}'
WHERE name IN ('Monthly 1st 12am Customer Activity', 'Monthly Customer Activity')
  AND sharepoint_path = 'Salesman Report/Customer Activity';
