"""Global key/value settings in precious.db `app_settings`."""

from __future__ import annotations

import json

from web.data.connection import Database
from web.delivery.email import split_recipients

_MODE = "schedule_test_mode"
_EMAILS = "schedule_test_emails"


class AppSettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def is_schedule_test_mode(self) -> bool:
        return self._get(_MODE) == "1"

    def test_emails(self) -> list[str]:
        raw = self._get(_EMAILS)
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return split_recipients(raw)
        if isinstance(parsed, list):
            return split_recipients("; ".join(str(x) for x in parsed))
        return split_recipients(str(parsed))

    def set_schedule_test(self, *, enabled: bool | None = None,
                          emails: list[str] | None = None) -> None:
        cleaned: list[str] | None = None
        if emails is not None:
            cleaned = split_recipients("; ".join(str(x) for x in emails))
        if enabled:
            have = cleaned if cleaned is not None else self.test_emails()
            if not have:
                raise ValueError("Add at least one test email before turning test mode on.")
        if cleaned is not None:
            self._set(_EMAILS, json.dumps(cleaned))
            if not cleaned:
                self._set(_MODE, "0")
                if enabled is None:
                    return
        if enabled is not None:
            self._set(_MODE, "1" if enabled else "0")

    def _get(self, key: str) -> str:
        with self.db.precious() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else ""

    def _set(self, key: str, value: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO app_settings(key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
