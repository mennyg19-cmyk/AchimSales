"""Strip magic-link bearer tokens from log records."""

from __future__ import annotations

import logging
import re

_MAGIC = re.compile(r"(/login/magic-link/)[^\s/?#]+")


class RedactMagicLinkFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        redacted = _MAGIC.sub(r"\1<redacted>", msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def install_magic_link_log_redaction() -> None:
    filt = RedactMagicLinkFilter()
    for name in ("", "werkzeug", "gunicorn.access", "gunicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(existing, RedactMagicLinkFilter) for existing in logger.filters):
            logger.addFilter(filt)
