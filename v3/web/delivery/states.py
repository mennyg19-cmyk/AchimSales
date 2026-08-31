"""Delivery-leg statuses. `pending` is not a settled state."""

from __future__ import annotations

PREPARED = "prepared"
SENDING = "sending"
ACCEPTED = "accepted"
SENT = "sent"
FAILED = "failed"
UNKNOWN = "unknown"

# Do not auto-send again. `accepted` means Graph already said yes.
SETTLED = frozenset({SENT, UNKNOWN, ACCEPTED})
RETRYABLE = frozenset({FAILED, PREPARED})
EMAIL_KINDS = frozenset({"email", "notice"})
FOLDER_KINDS = frozenset({"sharepoint", "onedrive"})

LEG_RETENTION_DAYS = 90
TOKEN_REFRESH_SKEW_SECONDS = 60
