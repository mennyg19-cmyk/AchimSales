-- Silent dual-build and the morning score email are gone.
DROP TABLE IF EXISTS view_workbook_parity;
DELETE FROM app_settings WHERE key IN (
    'view_workbook_parity',
    'view_parity_digest_emails',
    'view_parity_digest_sent_day'
);
