"""Yahoo Finance chart API — the primary deep-history price source.

Plan deviation, recorded: the plan named Stooq, but Stooq's CSV endpoints now
404 behind a JavaScript bot challenge (verified 2026-06-10), so it is no longer
usable programmatically. Yahoo's chart API is free, needs no key, reaches back
to the 1990s (SPY from 1993 — covers Faber calibration), and its `adjclose` is
split- AND dividend-adjusted — strictly better for total-return work.

Caveat on record: this is an unofficial API. If it breaks, the adapter seam
(fetch vs parse) localizes the damage and the cache preserves everything
already fetched.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from ..cache import JsonFileCache
from ..models import PriceBar

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# Benchmarks keep pre-2006 history (SPY needs the 1990s for Faber calibration).
HISTORY_START = date(1990, 1, 1)


def parse_chart(ticker: str, payload: dict) -> list[PriceBar]:
    """Parse a Yahoo chart payload into PriceBars. Skip-don't-guess: bars with
    a missing timestamp or adjusted close are dropped, never fabricated."""
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        adjclose = result["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, IndexError, TypeError):
        return []

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    def _at(seq: list, i: int):
        return seq[i] if i < len(seq) else None

    bars: list[PriceBar] = []
    for i, ts in enumerate(timestamps):
        adj = _at(adjclose, i)
        if ts is None or adj is None:
            continue
        d = datetime.fromtimestamp(ts, tz=UTC).date()
        if d < HISTORY_START:
            continue
        volume = _at(volumes, i)
        bars.append(
            PriceBar(
                ticker=ticker,
                d=d,
                open=_at(opens, i),
                high=_at(highs, i),
                low=_at(lows, i),
                close=_at(closes, i),
                adj_close=float(adj),
                volume=int(volume) if volume is not None else None,
                source="yahoo",
            )
        )
    return bars


def _granularity(payload: dict) -> str | None:
    try:
        return payload["chart"]["result"][0]["meta"].get("dataGranularity")
    except (KeyError, IndexError, TypeError):
        return None


def fetch_daily_bars(ticker: str, cache: JsonFileCache, client: httpx.Client) -> list[PriceBar]:
    """Full daily history for one ticker, through the fetch-once cache.

    Uses explicit period1/period2 epochs: `range=max` silently degrades to
    monthly granularity on long histories (verified on SPY), while explicit
    periods keep interval=1d honored. Non-daily payloads are rejected and
    never cached.
    """
    key = f"yahoo:daily:1d:{ticker}"
    payload = cache.get(key)
    if payload is None:
        period1 = int(datetime(1990, 1, 1, tzinfo=UTC).timestamp())
        period2 = int(datetime.now(tz=UTC).timestamp())
        resp = client.get(
            f"{BASE_URL}/{ticker}",
            params={
                "period1": str(period1),
                "period2": str(period2),
                "interval": "1d",
                "events": "div,splits",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if _granularity(payload) != "1d":
            raise ValueError(
                f"yahoo returned granularity {_granularity(payload)!r} for {ticker}, expected 1d"
            )
        if payload.get("chart", {}).get("result"):
            cache.put(key, payload)
    return parse_chart(ticker, payload)
