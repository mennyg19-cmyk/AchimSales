-- One-time cache purge: builder_version for 'ordered' bumped from 1 to 2
-- (remainder formula change). Old cached report payloads used the wrong
-- formula and must not be served. Cache is disposable; users re-run.
DELETE FROM report_payload_cache WHERE report_key = 'ordered';
