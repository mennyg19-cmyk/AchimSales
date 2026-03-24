"""
Generic OData v4 client for D365 F&O.

Features:
- Paginated fetch with @odata.nextLink
- Chunked page concatenation (every CHUNK_PAGES pages) to limit peak memory
- Server-side $filter and $select to minimize payload
- Batched ID-based filters (200 IDs per request) for child entities
- Parallel batch fetching with configurable concurrency
- Auto-refreshing tokens via D365TokenManager for long-running fetches
"""

import gc
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode

import pandas as pd

from core.auth import resolve_token
from core.http import build_retry_session, get_session

_thread_local = threading.local()

log = logging.getLogger(__name__)

CHUNK_PAGES = 5
BATCH_SIZE = 200
REQUEST_TIMEOUT = 120
MAX_WORKERS = 6


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

    chunks: list[pd.DataFrame] = []
    page_buffer: list[list[dict]] = []
    total_rows = 0
    page = 0

    session = getattr(_thread_local, "session", None) or get_session()

    while next_url:
        page += 1
        headers = {
            "Authorization": f"Bearer {resolve_token(token)}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
        }
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
    del chunks
    gc.collect()
    if log_pages:
        log.info("  %s: fetched %d total rows", entity_name, len(df))
    return df


def _fetch_one_batch(
    base_url: str,
    entity_name: str,
    token: str,
    filter_field: str,
    batch: list[str],
    select: list[str] | None,
    company_id: str | None,
) -> pd.DataFrame:
    """Fetch a single batch of IDs. Thread-safe helper for parallel batching."""
    if not getattr(_thread_local, "session", None):
        _thread_local.session = build_retry_session()
    escaped = [str(v).replace("'", "''") for v in batch]
    conditions = [f"{filter_field} eq '{v}'" for v in escaped]
    filter_expr = " or ".join(conditions)
    return fetch_odata_entity(
        base_url, entity_name, token,
        select=select,
        filter_expr=filter_expr,
        company_id=company_id,
        log_pages=False,
    )


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
    max_workers: int = MAX_WORKERS,
) -> pd.DataFrame:
    """Fetch an OData entity filtered by a list of IDs, batched to avoid URL length limits.

    Runs batches in parallel (up to ``max_workers`` threads) to drastically reduce
    wall-clock time for large ID lists.
    """
    if not filter_values:
        return pd.DataFrame()

    values = list(filter_values)
    num_batches = (len(values) + batch_size - 1) // batch_size
    if log_progress:
        log.info("Fetching %s for %d values (%d batches, %d parallel workers)",
                 entity_name, len(values), num_batches, max_workers)

    batches = [values[i : i + batch_size] for i in range(0, len(values), batch_size)]

    chunks: list[pd.DataFrame] = []
    total_rows = 0
    completed = 0
    consolidate_every = 50

    # Submit batches in waves to limit how many DataFrames sit in memory
    # waiting to be consumed. Each wave submits `wave_size` futures.
    wave_size = max_workers * 8

    for wave_start in range(0, num_batches, wave_size):
        wave_end = min(wave_start + wave_size, num_batches)
        wave_batches = batches[wave_start:wave_end]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _fetch_one_batch,
                    base_url, entity_name, token, filter_field,
                    batch, select, company_id,
                ): wave_start + idx
                for idx, batch in enumerate(wave_batches)
            }

            for future in as_completed(futures):
                completed += 1
                should_log = completed == 1 or completed == num_batches or completed % 50 == 0
                if should_log and log_progress:
                    log.info("  %s: completed %d/%d batches (%d rows so far)",
                             entity_name, completed, num_batches, total_rows)
                try:
                    df = future.result()
                    if not df.empty:
                        chunks.append(df)
                        total_rows += len(df)
                except Exception:
                    batch_idx = futures[future]
                    log.warning("  %s batch %d failed, skipping", entity_name, batch_idx + 1, exc_info=True)

                if len(chunks) >= consolidate_every:
                    chunks = [pd.concat(chunks, ignore_index=True)]

    if not chunks:
        if log_progress:
            log.info("  %s: no rows returned across all batches", entity_name)
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]
    del chunks
    gc.collect()
    if log_progress:
        log.info("  %s: fetched %d total rows", entity_name, len(result))
        try:
            from core.logging import log_memory
            log_memory("odata:batched:%s:done (%d rows)" % (entity_name, len(result)))
        except Exception:
            pass
    return result
