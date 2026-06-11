"""Alpaca daily bars (adjustment=all) — the recent-window cross-check source.

Free data starts ~2016; compass uses Alpaca to cross-check Stooq's adjusted
closes on the overlap window, not as the deep-history source.
"""
from __future__ import annotations

from datetime import date

import httpx

from ..cache import JsonFileCache
from ..config import require_env
from ..models import PriceBar

BASE_URL = "https://data.alpaca.markets/v2/stocks"


def parse_bars(ticker: str, payloads: list[dict]) -> list[PriceBar]:
    """Parse one or more pages of Alpaca bar payloads. Skip-don't-guess."""
    bars: list[PriceBar] = []
    for payload in payloads:
        for bar in payload.get("bars") or []:
            t = bar.get("t") or ""
            try:
                d = date.fromisoformat(t[:10])
                close = float(bar["c"])
            except (ValueError, KeyError, TypeError):
                continue
            bars.append(
                PriceBar(
                    ticker=ticker,
                    d=d,
                    open=bar.get("o"),
                    high=bar.get("h"),
                    low=bar.get("l"),
                    close=close,
                    adj_close=close,  # adjustment=all => close is fully adjusted
                    volume=int(bar["v"]) if bar.get("v") is not None else None,
                    source="alpaca",
                )
            )
    return bars


def fetch_daily_bars(
    ticker: str,
    cache: JsonFileCache,
    client: httpx.Client,
    *,
    start: date = date(2016, 1, 1),
    end: date | None = None,
) -> list[PriceBar]:
    end = end or date.today()
    key = f"alpaca:daily:{ticker}:{start.isoformat()}:{end.isoformat()}"
    pages = cache.get(key)
    if pages is None:
        headers = {
            "APCA-API-KEY-ID": require_env("ALPACA_API_KEY_ID"),
            "APCA-API-SECRET-KEY": require_env("ALPACA_API_SECRET_KEY"),
        }
        pages = []
        page_token: str | None = None
        while True:
            params: dict[str, str] = {
                "timeframe": "1Day",
                "adjustment": "all",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": "10000",
            }
            if page_token:
                params["page_token"] = page_token
            resp = client.get(
                f"{BASE_URL}/{ticker}/bars", params=params, headers=headers, timeout=30
            )
            resp.raise_for_status()
            payload = resp.json()
            pages.append(payload)
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        cache.put(key, pages)
    return parse_bars(ticker, pages)
