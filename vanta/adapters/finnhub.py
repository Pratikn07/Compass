"""Finnhub adapter: company news, earnings calendar dates, and estimates."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import requests

from .. import config
from ..models import EarningsDate, Estimate, NewsItem
from .base import AdapterResult

BASE = "https://finnhub.io/api/v1"
TIMEOUT = 30


def _quarter_label(item: dict) -> str:
    year = item.get("year")
    quarter = item.get("quarter")
    if year and quarter:
        return f"{year}Q{quarter}"
    return item.get("date", "unknown")


def fetch(ticker: str, days: int = 30) -> AdapterResult:
    key = config.require_env("FINNHUB_API_KEY")
    result = AdapterResult()
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=days)).isoformat()
    to = today.isoformat()

    # Company news
    resp = requests.get(
        f"{BASE}/company-news",
        params={"symbol": ticker, "from": frm, "to": to, "token": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    for art in resp.json() or []:
        ts = art.get("datetime")
        published = (
            datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        )
        if not art.get("url"):
            continue
        result.news.append(NewsItem(
            ticker=ticker,
            source="finnhub",
            published_at=published or datetime.now(timezone.utc),
            headline=art.get("headline", ""),
            url=art["url"],
            sentiment=None,
            raw=art,
        ))

    # Earnings calendar (dates + estimates)
    resp = requests.get(
        f"{BASE}/calendar/earnings",
        params={"symbol": ticker, "from": frm,
                "to": (today + timedelta(days=60)).isoformat(), "token": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    for item in (resp.json() or {}).get("earningsCalendar", []):
        d = item.get("date")
        if d:
            result.earnings_dates.append(EarningsDate(
                ticker=ticker,
                report_date=date.fromisoformat(d),
                confirmed=item.get("epsActual") is not None,
            ))
            result.estimates.append(Estimate(
                ticker=ticker,
                period=_quarter_label(item),
                eps_est=item.get("epsEstimate"),
                rev_est=item.get("revenueEstimate"),
                eps_actual=item.get("epsActual"),
                surprise_pct=None,
                as_of=today,
            ))
    return result
