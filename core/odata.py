"""
Generic OData v4 client for D365 F&O.

Features:
- Paginated fetch with @odata.nextLink
- Chunked page concatenation (every CHUNK_PAGES pages) to limit peak memory
- Server-side $filter and $select to minimize payload
- Batched ID-based filters (50 IDs per request) for child entities
"""

import logging
from urllib.parse import urlencode

import pandas as pd

from core.http import get_session

log = logging.getLogger(__name__)

CHUNK_PAGES = 10
BATCH_SIZE = 50
REQUEST_TIMEOUT = 120


def fetch_odata_entity(
    base_url: str,
    entity_name: str,
    token: str,
    select: list[str] | None = None,
    filter_expr: str | None = None,
    company_id: str | None = None,
    log_pages: bool = True,
) -> pd.DataFrame:
    """Fetch an OData entity with pagination. Returns a DataFrame.

    Args:
        base_url: e.g. https://org.operations.dynamics.com/data/
        entity_name: e.g. SalesOrderHeadersV3
        select: list of field names for $select
        filter_expr: OData $filter expression
        company_id: optional dataAreaId filter
        log_pages: whether to log page-level progress
    """
    url_base = f"{base_url.rstrip('/')}/{entity_name}"
    query = {}
    if select:
        query["$select"] = ",".join(select)

    filter_parts = []
    if filter_expr:
        filter_parts.append(filter_expr)
    if company_id:
        filter_parts.append(f"(dataAreaId eq '{company_id}')")
    if filter_parts:
        query["$filter"] = " and ".join(filter_parts)

    next_url = f"{url_base}?{urlencode(query)}" if query else url_base
    headers = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    }

    chunks: list[pd.DataFrame] = []
    page_buffer: list[list[dict]] = []
    total_rows = 0
    page = 0

    session = get_session()

    while next_url:
        page += 1
        resp = session.get(next_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        value = data.get("value", [])

        if isinstance(value, list) and value:
            page_buffer.append(value)
            total_rows += len(value)
            if log_pages:
                log.info("  %s: page %d, %d rows (total %d)", entity_name, page, len(value), total_rows)

        if len(page_buffer) >= CHUNK_PAGES:
            flat = [row for page_rows in page_buffer for row in page_rows]
            chunks.append(pd.DataFrame(flat))
            page_buffer.clear()

        next_url = data.get("@odata.nextLink")

    if page_buffer:
        flat = [row for page_rows in page_buffer for row in page_rows]
        chunks.append(pd.DataFrame(flat))
        page_buffer.clear()

    if not chunks:
        if log_pages:
            log.info("  %s: no rows returned", entity_name)
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]
    if log_pages:
        log.info("  %s: fetched %d total rows", entity_name, len(df))
    return df


def fetch_odata_batched(
    base_url: str,
    entity_name: str,
    token: str,
    filter_field: str,
    filter_values: list[str],
    select: list[str] | None = None,
    company_id: str | None = None,
    batch_size: int = BATCH_SIZE,
    log_progress: bool = True,
) -> pd.DataFrame:
    """Fetch an OData entity filtered by a list of IDs, batched to avoid URL length limits.

    Builds OData $filter like: "SalesOrderNumber eq 'SO001' or SalesOrderNumber eq 'SO002'"
    in batches of `batch_size`.
    """
    if not filter_values:
        return pd.DataFrame()

    values = list(filter_values)
    num_batches = (len(values) + batch_size - 1) // batch_size
    if log_progress:
        log.info("Fetching %s for %d values (%d batches)", entity_name, len(values), num_batches)

    chunks: list[pd.DataFrame] = []
    for i in range(0, len(values), batch_size):
        batch = values[i : i + batch_size]
        batch_num = (i // batch_size) + 1

        escaped = [str(v).replace("'", "''") for v in batch]
        conditions = [f"{filter_field} eq '{v}'" for v in escaped]
        filter_expr = " or ".join(conditions)

        should_log = batch_num == 1 or batch_num == num_batches or batch_num % 50 == 0
        if should_log and log_progress:
            log.info("  %s batch %d/%d: %d values", entity_name, batch_num, num_batches, len(batch))

        df = fetch_odata_entity(
            base_url, entity_name, token,
            select=select,
            filter_expr=filter_expr,
            company_id=company_id,
            log_pages=False,
        )
        if not df.empty:
            chunks.append(df)

    if not chunks:
        if log_progress:
            log.info("  %s: no rows returned across all batches", entity_name)
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True).drop_duplicates()
    if log_progress:
        log.info("  %s: fetched %d total rows", entity_name, len(result))
    return result
