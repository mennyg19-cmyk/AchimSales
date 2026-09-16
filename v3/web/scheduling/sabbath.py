"""Is it Shabbos or Yom Tov right now? (so a scheduled send can skip it).

Matches the live Azure runbook: Hebcal for Brooklyn, 18-minute candles.
Fails open — a calendar hiccup must never block every send.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_BROOKLYN_GEONAMEID = 5110302
_HTTP_TIMEOUT_SECONDS = 10
_cache: dict[str, list[dict]] = {}


def skip_sabbath_enabled(params: dict | None) -> bool:
    """Clock runs skip Shabbos unless the schedule sets skip_sabbath to false."""
    if not params or "skip_sabbath" not in params:
        return True
    return bool(params.get("skip_sabbath"))


def melacha_assur(now_utc: datetime | None = None) -> tuple[bool, str]:
    """True (with a reason) if it's currently Shabbos or Yom Tov in Brooklyn."""
    now = now_utc or datetime.now(timezone.utc)
    try:
        items = _fetch_items(now)
        return _assur_from_items(items, now)
    except Exception:  # noqa: BLE001 - a calendar hiccup must not block sends
        log.warning("Hebcal check failed; treating as not restricted", exc_info=True)
        return False, ""


def _fetch_items(now: datetime) -> list[dict]:
    start = (now - timedelta(days=4)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=3)).strftime("%Y-%m-%d")
    cache_key = f"{start}_{end}"
    if cache_key in _cache:
        return _cache[cache_key]
    url = (
        "https://www.hebcal.com/hebcal?cfg=json&v=1&maj=on&leyning=off&c=on&M=on"
        f"&geonameid={_BROOKLYN_GEONAMEID}&start={start}&end={end}"
    )
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
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
            candles.append((when, entry.get("memo", "") or ""))
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
        weekday = now.astimezone(candle_dt.tzinfo).strftime("%A")
        if today in yomtov_titles:
            return True, f"Yom Tov: {yomtov_titles[today]}"
        # Hebcal sometimes puts the weekday name on regular Shabbos candles.
        if candle_memo and candle_memo not in ("", weekday):
            return True, f"Yom Tov: {candle_memo}"
        return True, "Shabbos"
    return False, ""


def _parse_dt(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
