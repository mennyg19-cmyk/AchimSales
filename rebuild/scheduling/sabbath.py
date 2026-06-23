"""Is it Shabbos or Yom Tov right now? (so a scheduled send can skip it)."""

# === What's in this file ===
# The live app skips sends while melacha is assur (Shabbos or Yom Tov), using
# Hebcal's calendar for Brooklyn with 18-minute candle lighting. This re-creates
# that check for the scheduler: ask Hebcal for the candle-lighting and havdalah
# times around now, and if now falls inside one of those windows, it's restricted.
#
# It FAILS OPEN: if Hebcal can't be reached or returns something odd, we report
# "not restricted" so a network hiccup never silently stops every schedule. The
# answer is cached per day so a minute-by-minute poller makes at most one call.
#
# melacha_assur() -- (is_restricted, reason) for now, via Hebcal (cached, fail-open)
# _assur_from_items() -- the pure window check (no network), so it's easy to test

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone

log = logging.getLogger("rebuild.scheduling.sabbath")

_BROOKLYN_GEONAMEID = 5110302
_HTTP_TIMEOUT_SECONDS = 10
_cache: dict[str, list[dict]] = {}


def melacha_assur(now_utc: datetime | None = None) -> tuple[bool, str]:
    """True (with a reason) if it's currently Shabbos or Yom Tov in Brooklyn.

    Fails open: any Hebcal error returns (False, "") so a bad network call can't
    block every scheduled send.
    """
    now = now_utc or datetime.now(timezone.utc)
    try:
        items = _fetch_items(now)
        return _assur_from_items(items, now)
    except Exception:  # noqa: BLE001 - a calendar hiccup must not block sends
        log.warning("Hebcal check failed; treating as not restricted", exc_info=True)
        return False, ""


def _fetch_items(now: datetime) -> list[dict]:
    # A window around now covers the candle/havdalah pair we might be inside.
    start = (now - timedelta(days=4)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=3)).strftime("%Y-%m-%d")
    cache_key = f"{start}_{end}"
    if cache_key in _cache:
        return _cache[cache_key]
    url = (
        "https://www.hebcal.com/hebcal?cfg=json&v=1&maj=on&leyning=off&c=on&M=on"
        f"&geonameid={_BROOKLYN_GEONAMEID}&start={start}&end={end}"
    )
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310 - fixed hebcal URL
        hebcal_payload = json.loads(resp.read().decode("utf-8"))
    items = hebcal_payload.get("items", []) or []
    _cache[cache_key] = items
    return items


def _assur_from_items(items: list[dict], now: datetime) -> tuple[bool, str]:
    """Decide restriction from Hebcal items. now must be timezone-aware."""
    candles: list[tuple[datetime, str]] = []
    havdalahs: list[datetime] = []
    yomtov_titles: dict[str, str] = {}
    for entry in items:
        category = entry.get("category", "")
        when = _parse_dt(entry.get("date", ""))
        if category == "candles" and when is not None:
            candles.append((when, entry.get("memo", "")))
        elif category == "havdalah" and when is not None:
            havdalahs.append(when)
        elif entry.get("yomtov"):
            yomtov_titles[entry.get("date", "")] = entry.get("title", "Yom Tov")

    candles.sort(key=lambda pair: pair[0])
    havdalahs.sort()

    for candle_dt, candle_memo in candles:
        end_dt = next((h for h in havdalahs if h > candle_dt), None)
        if end_dt is None or not (candle_dt <= now <= end_dt):
            continue
        today = now.astimezone(candle_dt.tzinfo).strftime("%Y-%m-%d")
        if today in yomtov_titles:
            return True, f"Yom Tov: {yomtov_titles[today]}"
        if candle_memo:
            return True, f"Yom Tov: {candle_memo}"
        return True, "Shabbos"
    return False, ""


def _parse_dt(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
