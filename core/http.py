"""
Shared HTTP session with automatic retry for transient failures.

Provides a pre-configured ``requests.Session`` that retries on 429
(throttled), 500, 502, 503, 504 and connection/timeout errors with
exponential backoff.  All modules that hit D365 OData or Microsoft
Graph should use ``get_session()`` instead of raw ``requests``.
"""

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF = 1.0
_DEFAULT_STATUS_FORCELIST = (429, 500, 502, 503, 504)

_session: requests.Session | None = None


def build_retry_session(
    retries: int = _DEFAULT_RETRIES,
    backoff_factor: float = _DEFAULT_BACKOFF,
    status_forcelist: tuple[int, ...] = _DEFAULT_STATUS_FORCELIST,
) -> requests.Session:
    """Build a new ``requests.Session`` with retry + backoff.

    The session honours the ``Retry-After`` header returned by 429
    responses so D365 throttling is handled gracefully.
    """
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_session() -> requests.Session:
    """Return a module-level singleton retry session (created on first call)."""
    global _session
    if _session is None:
        _session = build_retry_session()
    return _session


def retry_call(fn, *args, retries: int = 2, delay: float = 1.0, **kwargs):
    """Simple retry wrapper for non-HTTP calls (e.g. MSAL token acquisition).

    Retries ``fn(*args, **kwargs)`` up to *retries* times with a fixed
    *delay* between attempts.  Only retries on ``Exception``; lets
    ``KeyboardInterrupt`` and ``SystemExit`` propagate immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt <= retries:
                log.warning("Attempt %d/%d failed (%s), retrying in %.1fs",
                            attempt, retries + 1, exc, delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
