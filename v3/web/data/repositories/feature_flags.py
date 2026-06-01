"""Feature-flag repository (precious.db `feature_flags`).

Global on/off switches that gate optional surfaces (dashboard tab, order entry,
the test-site link). Mirrors the live app's flags. Reads default to the seeded
value; an unknown key returns the caller's default so a missing row never raises.
"""

from __future__ import annotations

from web.data.connection import Database

# key -> (default_enabled, description). Single source of truth for seeding.
DEFAULTS: dict[str, tuple[bool, str]] = {
    "dashboard_enabled": (True, "Show the Dashboard tab"),
    "order_entry_enabled": (False, "Show the Order Entry tab"),
    "test_site_enabled": (False, "Show the link to the legacy test site"),
}


class FeatureFlagRepository:
    def __init__(self, db: Database):
        self.db = db

    def seed_defaults(self) -> None:
        """Insert any missing flags at their default. Idempotent; never overwrites."""
        with self.db.precious() as conn:
            for key, (enabled, desc) in DEFAULTS.items():
                conn.execute(
                    "INSERT INTO feature_flags(key, enabled, description) VALUES (?, ?, ?)"
                    " ON CONFLICT(key) DO NOTHING",
                    (key, 1 if enabled else 0, desc),
                )

    def all(self) -> dict[str, bool]:
        with self.db.precious() as conn:
            rows = conn.execute("SELECT key, enabled FROM feature_flags").fetchall()
        return {r["key"]: bool(r["enabled"]) for r in rows}

    def is_enabled(self, key: str, default: bool = False) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT enabled FROM feature_flags WHERE key=?", (key,)
            ).fetchone()
        if row is None:
            return default
        return bool(row["enabled"])

    def set(self, key: str, enabled: bool) -> None:
        desc = DEFAULTS.get(key, (False, ""))[1]
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO feature_flags(key, enabled, description) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET enabled=excluded.enabled",
                (key, 1 if enabled else 0, desc),
            )
