"""Alpha Vantage fundamentals — EARNINGS + INCOME_STATEMENT (free tier).

Free-tier reality (planned for in the rulebook): ~25 requests/day. The
fetch-once cache makes the multi-evening backfill resumable; a RateLimited
exception lets the ingest loop stop cleanly instead of caching garbage.
"""
from __future__ import annotations

import time
from datetime import date

import httpx

from ..cache import JsonFileCache
from ..config import require_env
from ..models import FundamentalsQuarter

BASE_URL = "https://www.alphavantage.co/query"


class RateLimited(Exception):
    """Raised when Alpha Vantage returns a throttle note instead of data."""


def _check_throttle(payload: dict) -> None:
    for key in ("Note", "Information"):
        msg = payload.get(key)
        if msg and ("rate limit" in msg.lower() or "premium" in msg.lower()
                    or "requests per day" in msg.lower() or "call frequency" in msg.lower()):
            raise RateLimited(msg)


def _parse_date(value: str | None) -> date | None:
    if not value or value in ("None", "0000-00-00"):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_float(value) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_earnings(payload: dict) -> dict[date, dict]:
    """fiscal_quarter_end -> {report_date, eps_actual, eps_estimate, surprise_pct}."""
    out: dict[date, dict] = {}
    for q in payload.get("quarterlyEarnings") or []:
        fqe = _parse_date(q.get("fiscalDateEnding"))
        if fqe is None:
            continue
        out[fqe] = {
            "report_date": _parse_date(q.get("reportedDate")),
            "eps_actual": _parse_float(q.get("reportedEPS")),
            "eps_estimate": _parse_float(q.get("estimatedEPS")),
            "surprise_pct": _parse_float(q.get("surprisePercentage")),
        }
    return out


def parse_income_statement(payload: dict) -> dict[date, dict]:
    """fiscal_quarter_end -> {revenue, operating_income}."""
    out: dict[date, dict] = {}
    for q in payload.get("quarterlyReports") or []:
        fqe = _parse_date(q.get("fiscalDateEnding"))
        if fqe is None:
            continue
        out[fqe] = {
            "revenue": _parse_float(q.get("totalRevenue")),
            "operating_income": _parse_float(q.get("operatingIncome")),
        }
    return out


def merge_fundamentals(
    ticker: str, earnings: dict[date, dict], income: dict[date, dict]
) -> list[FundamentalsQuarter]:
    """Outer-join the two endpoints on fiscal quarter end. Quarters present in
    only one endpoint keep None for the other's fields (skip-don't-guess)."""
    rows: list[FundamentalsQuarter] = []
    for fqe in sorted(set(earnings) | set(income)):
        e = earnings.get(fqe, {})
        i = income.get(fqe, {})
        rows.append(
            FundamentalsQuarter(
                ticker=ticker,
                fiscal_quarter_end=fqe,
                report_date=e.get("report_date"),
                revenue=i.get("revenue"),
                operating_income=i.get("operating_income"),
                eps_estimate=e.get("eps_estimate"),
                eps_actual=e.get("eps_actual"),
                surprise_pct=e.get("surprise_pct"),
                source="alphavantage",
            )
        )
    return rows


def _fetch_function(
    function: str, ticker: str, cache: JsonFileCache, client: httpx.Client
) -> dict:
    key = f"alphavantage:{function}:{ticker}"
    payload = cache.get(key)
    if payload is None:
        resp = client.get(
            BASE_URL,
            params={
                "function": function,
                "symbol": ticker,
                "apikey": require_env("ALPHAVANTAGE_API_KEY"),
            },
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        _check_throttle(payload)  # never cache a throttle response
        cache.put(key, payload)
        time.sleep(1.1)  # the free tier asks for ~1 request/second spacing
    return payload


def fetch_fundamentals(
    ticker: str, cache: JsonFileCache, client: httpx.Client
) -> list[FundamentalsQuarter]:
    earnings = parse_earnings(_fetch_function("EARNINGS", ticker, cache, client))
    income = parse_income_statement(_fetch_function("INCOME_STATEMENT", ticker, cache, client))
    return merge_fundamentals(ticker, earnings, income)
