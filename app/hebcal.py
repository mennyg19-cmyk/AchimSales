"""Shabbos/Yom Tov check for Brooklyn (Hebcal). Hold when the calendar is missing."""

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
    if not params or "skip_sabbath" not in params:
        return True
    return bool(params.get("skip_sabbath"))


def restriction(now_utc: datetime | None = None) -> tuple[str, str]:
    """('ok', ''), ('assur', reason), or ('hold', reason) if Hebcal is unusable."""
    now = now_utc or datetime.now(timezone.utc)
    try:
        items = _fetch_items(now)
    except Exception:
        log.warning("Hebcal fetch failed; holding scheduled sends", exc_info=True)
        return "hold", "Hebcal calendar could not be loaded"
    if not items:
        return "hold", "Hebcal returned no days covering now"
    assur, reason = _assur_from_items(items, now)
    if assur:
        return "assur", reason
    return "ok", ""


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
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
        hebcal_payload = json.loads(resp.read().decode("utf-8"))
    items = hebcal_payload.get("items", []) or []
    _cache[cache_key] = items
    return items


def _assur_from_items(items: list[dict], now: datetime) -> tuple[bool, str]:
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
        if candle_memo and candle_memo not in ("", weekday):
            return True, f"Yom Tov: {candle_memo}"
        return True, "Shabbos"
    return False, ""


def _parse_dt(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def clear_cache() -> None:
    _cache.clear()
