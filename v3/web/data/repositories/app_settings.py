"""Global key/value settings in precious.db `app_settings`."""

from __future__ import annotations

import json

from web.data.connection import Database
from web.delivery.email import split_recipients

_MODE = "schedule_test_mode"
_EMAILS = "schedule_test_emails"
_SEED_SKIP = "seed_skip_schedule_names"
_PARITY = "view_workbook_parity"
_PARITY_DIGEST_EMAILS = "view_parity_digest_emails"
_PARITY_DIGEST_SENT = "view_parity_digest_sent_day"


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

    def skipped_seed_names(self) -> set[str]:
        raw = self._get(_SEED_SKIP)
        if not raw:
            return set()
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return set()
        if not isinstance(parsed, list):
            return set()
        return {str(x).strip() for x in parsed if str(x).strip()}

    def skip_seed_name(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        names = self.skipped_seed_names()
        if name in names:
            return
        names.add(name)
        self._set(_SEED_SKIP, json.dumps(sorted(names)))

    def unskip_seed_name(self, name: str) -> None:
        name = (name or "").strip()
        names = self.skipped_seed_names()
        if name not in names:
            return
        names.discard(name)
        self._set(_SEED_SKIP, json.dumps(sorted(names)))

    def view_workbook_parity_enabled(self) -> bool:
        """Default on while dual-write exists. Set app_settings key to 0 to pause."""
        raw = self._get(_PARITY)
        if raw == "":
            return True
        return raw == "1"

    def view_parity_digest_emails(self) -> list[str]:
        raw = self._get(_PARITY_DIGEST_EMAILS)
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                return split_recipients(raw)
            if isinstance(parsed, list):
                return split_recipients("; ".join(str(x) for x in parsed))
            return split_recipients(str(parsed))
        # Fall back to schedule test emails, then V3_ADMIN_EMAILS.
        test = self.test_emails()
        if test:
            return test
        import os
        return split_recipients(
            os.environ.get("V3_ADMIN_EMAILS") or os.environ.get("V2_ADMIN_EMAILS") or ""
        )

    def set_view_parity_digest_emails(self, emails: list[str]) -> None:
        cleaned = split_recipients("; ".join(str(x) for x in emails))
        self._set(_PARITY_DIGEST_EMAILS, json.dumps(cleaned))

    def view_parity_digest_sent_day(self) -> str:
        return self._get(_PARITY_DIGEST_SENT)

    def set_view_parity_digest_sent_day(self, day: str) -> None:
        self._set(_PARITY_DIGEST_SENT, day)

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
