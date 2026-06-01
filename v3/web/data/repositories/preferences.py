"""User preferences repository (precious.db `user_preferences` table).

Theme, landing page, and default report tab. One row per user, created on first
write. Reads tolerate a missing row by returning defaults so a brand-new user
never sees an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.data.connection import Database

THEMES = ("light", "dark", "monochrome", "monochrome_dark")
LANDING_PAGES = ("reports", "dashboard")


@dataclass(frozen=True)
class Preferences:
    theme: str = "light"
    landing_page: str = "reports"
    default_report_tab: str = ""


class PreferencesRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, user_id: int) -> Preferences:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT theme, landing_page, default_report_tab FROM user_preferences WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            return Preferences()
        return Preferences(theme=row["theme"], landing_page=row["landing_page"],
                           default_report_tab=row["default_report_tab"])

    def set(self, user_id: int, *, theme: str | None = None,
            landing_page: str | None = None, default_report_tab: str | None = None) -> Preferences:
        """Upsert only the provided fields; unspecified fields keep their value."""
        current = self.get(user_id)
        theme = _coerce(theme, current.theme, THEMES)
        landing_page = _coerce(landing_page, current.landing_page, LANDING_PAGES)
        tab = current.default_report_tab if default_report_tab is None else str(default_report_tab)
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO user_preferences(user_id, theme, landing_page, default_report_tab)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(user_id) DO UPDATE SET"
                "   theme=excluded.theme, landing_page=excluded.landing_page,"
                "   default_report_tab=excluded.default_report_tab",
                (user_id, theme, landing_page, tab),
            )
        return Preferences(theme=theme, landing_page=landing_page, default_report_tab=tab)


def _coerce(value: str | None, fallback: str, allowed: tuple[str, ...]) -> str:
    if value is None:
        return fallback
    v = str(value).strip().lower()
    return v if v in allowed else fallback
