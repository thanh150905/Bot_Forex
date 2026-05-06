"""
Economic news filter using Forex Factory/FairEconomy weekly calendar export.

The export should be cached. Forex Factory's calendar export is updated around
hourly and may rate-limit frequent requests, so callers should not fetch it on
every tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


DEFAULT_NEWS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
DEFAULT_IMPACTS = {"High", "Holiday"}

_cache: dict[str, Any] = {
    "fetched_at": None,
    "events": [],
    "error": None,
}


@dataclass(frozen=True)
class NewsRisk:
    blocked: bool
    reason: str
    events: list[dict[str, Any]]
    source_error: str | None = None


def symbol_currencies(symbol: str) -> set[str]:
    cleaned = "".join(ch for ch in symbol.upper() if ch.isalpha())
    currencies = {
        "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY",
    }
    affected = {code for code in currencies if code in cleaned}
    if cleaned.startswith(("XAU", "XAG", "USOIL", "UKOIL")):
        affected.add("USD")
    return affected or {"USD"}


def _parse_event_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    event_time = _parse_event_time(raw.get("date") or raw.get("datetime") or raw.get("time"))
    if event_time is None:
        return None

    currency = str(raw.get("country") or raw.get("currency") or "").upper()
    if not currency:
        return None

    return {
        "title": str(raw.get("title") or raw.get("event") or "Economic event"),
        "currency": currency,
        "impact": str(raw.get("impact") or "").title(),
        "time": event_time.isoformat(),
        "forecast": raw.get("forecast"),
        "previous": raw.get("previous"),
    }


async def fetch_calendar_events(
    url: str = DEFAULT_NEWS_URL,
    cache_seconds: int = 3600,
) -> tuple[list[dict[str, Any]], str | None]:
    now = datetime.now(timezone.utc)
    fetched_at = _cache.get("fetched_at")
    if fetched_at and (now - fetched_at).total_seconds() < cache_seconds:
        return list(_cache.get("events") or []), _cache.get("error")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        events = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    normalized = _normalize_event(item)
                    if normalized:
                        events.append(normalized)
        _cache.update({"fetched_at": now, "events": events, "error": None})
        return events, None
    except Exception as exc:
        error = str(exc)
        _cache.update({"fetched_at": now, "error": error})
        return list(_cache.get("events") or []), error


async def evaluate_news_risk(
    symbol: str,
    minutes_before: int,
    minutes_after: int,
    impacts: set[str] | None = None,
    url: str = DEFAULT_NEWS_URL,
    cache_seconds: int = 3600,
) -> NewsRisk:
    currencies = symbol_currencies(symbol)
    active_impacts = impacts or DEFAULT_IMPACTS
    events, source_error = await fetch_calendar_events(url=url, cache_seconds=cache_seconds)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=minutes_after)
    window_end = now + timedelta(minutes=minutes_before)

    matching = []
    for event in events:
        event_time = _parse_event_time(event.get("time"))
        if event_time is None:
            continue
        if event.get("currency") not in currencies:
            continue
        if str(event.get("impact") or "").title() not in active_impacts:
            continue
        if window_start <= event_time <= window_end:
            matching.append(event)

    if matching:
        nearest = min(
            matching,
            key=lambda item: abs((_parse_event_time(item["time"]) or now) - now),
        )
        return NewsRisk(
            blocked=True,
            reason=f"{nearest['currency']} {nearest['impact']} news: {nearest['title']}",
            events=matching,
            source_error=source_error,
        )

    return NewsRisk(
        blocked=False,
        reason="No high-impact news inside filter window",
        events=[],
        source_error=source_error,
    )
