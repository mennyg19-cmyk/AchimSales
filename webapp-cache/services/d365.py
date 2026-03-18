"""
D365 data-fetching service (cache-only version).

All data is served from the local SQLite cache, populated by the
hourly background refresh.  No live OData calls are made from
request handlers.
"""

import logging

log = logging.getLogger(__name__)
