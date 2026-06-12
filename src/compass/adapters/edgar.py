"""SEC EDGAR companyfacts — official, free, key-less fundamentals.

Added 2026-06-11 by owner decision (rulebook §6 source table updated): Alpha
Vantage's 25-requests/day cap made full coverage a multi-week wait; EDGAR
companyfacts provides quarterly revenue and operating income for all US
filers with the exact FILING date attached — the strongest possible
point-in-time anchor for the no-lookahead rule.

Honest limits, on record:
- XBRL data effectively starts 2007-2009 (the SEC mandate), so dev-window
  coverage tops out around ~79% of member-quarters — above the 70% gate.
- EPS estimates/surprise are analyst data and do NOT exist in SEC filings;
  those fields stay None and the background Alpha Vantage loop keeps filling
  them (H2's scoring averages whatever metrics exist).
- Foreign private issuers (TSM, NVO) file annual 20-Fs; quarterly facts are
  sparse-to-absent. Skip-don't-guess: they stay with Alpha Vantage.
- `report_date` = the EARLIEST `filed` date that contains the fact, and the
  value is taken from that same earliest filing — what the market actually
  knew, before any restatements.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from ..cache import JsonFileCache
from ..config import require_env
from ..models import FundamentalsQuarter

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "SalesRevenueServicesNet",
]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]

QUARTER_DAYS = (75, 100)
ANNUAL_DAYS = (350, 380)


def _headers() -> dict[str, str]:
    return {"User-Agent": require_env("SEC_USER_AGENT")}


def fetch_ticker_cik_map(cache: JsonFileCache, client: httpx.Client) -> dict[str, int]:
    key = "edgar:ticker-cik-map"
    payload = cache.get(key)
    if payload is None:
        resp = client.get(TICKER_MAP_URL, headers=_headers(), timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        cache.put(key, payload)
    return {row["ticker"].upper(): int(row["cik_str"]) for row in payload.values()}


def fetch_company_facts(
    cik: int, cache: JsonFileCache, client: httpx.Client, *, fresh: bool = False
) -> dict:
    key = f"edgar:companyfacts:{cik}"
    payload = None if fresh else cache.get(key)
    if payload is None:
        resp = client.get(COMPANYFACTS_URL.format(cik=cik), headers=_headers(), timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        cache.put(key, payload)
        time.sleep(0.15)  # SEC politeness rate
    return payload


@dataclass(frozen=True)
class _Fact:
    start: date
    end: date
    val: float
    filed: date


def _collect_facts(payload: dict, tags: list[str]) -> list[_Fact]:
    """All USD duration facts across the tag fallback chain, keeping the
    EARLIEST filing per (start, end) period — as-originally-reported."""
    best: dict[tuple[date, date], _Fact] = {}
    gaap = (payload.get("facts") or {}).get("us-gaap") or {}
    for tag in tags:
        entries = ((gaap.get(tag) or {}).get("units") or {}).get("USD") or []
        for e in entries:
            try:
                start = date.fromisoformat(e["start"])
                end = date.fromisoformat(e["end"])
                filed = date.fromisoformat(e["filed"])
                val = float(e["val"])
            except (KeyError, ValueError, TypeError):
                continue
            period = (start, end)
            if period not in best or filed < best[period].filed:
                best[period] = _Fact(start, end, val, filed)
    return list(best.values())


def _quarterly_values(facts: list[_Fact]) -> dict[date, _Fact]:
    """Quarter-end -> fact. Direct ~90-day durations first; Q4 derived as
    annual minus its three contained quarters when all three exist."""
    quarters: dict[date, _Fact] = {}
    for f in facts:
        if QUARTER_DAYS[0] <= (f.end - f.start).days <= QUARTER_DAYS[1]:
            if f.end not in quarters or f.filed < quarters[f.end].filed:
                quarters[f.end] = f

    for f in facts:
        if not (ANNUAL_DAYS[0] <= (f.end - f.start).days <= ANNUAL_DAYS[1]):
            continue
        if f.end in quarters:
            continue
        contained = [
            q for q in quarters.values()
            if f.start - timedelta(days=10) <= q.start and q.end < f.end
        ]
        if len(contained) != 3:
            continue
        derived_val = f.val - sum(q.val for q in contained)
        derived_filed = max([f.filed] + [q.filed for q in contained])
        quarters[f.end] = _Fact(
            start=max(q.end for q in contained) + timedelta(days=1),
            end=f.end, val=derived_val, filed=derived_filed,
        )
    return quarters


def parse_quarterly_fundamentals(ticker: str, payload: dict) -> list[FundamentalsQuarter]:
    revenue = _quarterly_values(_collect_facts(payload, REVENUE_TAGS))
    op_income = _quarterly_values(_collect_facts(payload, OPERATING_INCOME_TAGS))
    rows: list[FundamentalsQuarter] = []
    for fqe in sorted(set(revenue) | set(op_income)):
        r = revenue.get(fqe)
        o = op_income.get(fqe)
        filed_dates = [f.filed for f in (r, o) if f is not None]
        rows.append(
            FundamentalsQuarter(
                ticker=ticker,
                fiscal_quarter_end=fqe,
                report_date=min(filed_dates) if filed_dates else None,
                revenue=r.val if r else None,
                operating_income=o.val if o else None,
                eps_estimate=None,
                eps_actual=None,
                surprise_pct=None,
                source="edgar",
            )
        )
    return rows


def fetch_fundamentals(
    ticker: str, cik: int, cache: JsonFileCache, client: httpx.Client, *, fresh: bool = False
) -> list[FundamentalsQuarter]:
    return parse_quarterly_fundamentals(
        ticker, fetch_company_facts(cik, cache, client, fresh=fresh)
    )
