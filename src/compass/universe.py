"""The rulebook's Appendix A as code: 10 themes, 74 members, ETFs, benchmarks.

Source of truth: docs/specs/2026-06-10-rulebook.md (Appendix A). A unit test
asserts the counts here match the appendix.

`member_since` conventions (documented in the appendix):
- Members backdated as "decades"/long-history start at DEVELOPMENT_START
  (2006-01-01) — the earliest date any backtest looks at.
- Where the appendix pins a month (IPO/spin-off/listing), we use the first day
  of that month; price data naturally starts at the actual listing date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

DEV_START = date(2006, 1, 1)


@dataclass(frozen=True)
class Theme:
    slug: str
    name: str
    etf_ticker: str | None  # None => basket-only, labeled hindsight-curated
    etf_is_primary: bool


@dataclass(frozen=True)
class Member:
    ticker: str
    name: str
    theme_slug: str
    member_since: date
    justification: str
    member_until: date | None = None


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    kind: str  # "etf" | "benchmark"


THEMES: list[Theme] = [
    Theme("ai-chips", "AI chips and semiconductors", "SMH", True),
    Theme("ai-memory-storage", "AI memory and storage", None, False),
    Theme("data-centers-power", "Data centers and power", None, False),
    Theme("cloud-software", "Cloud and software", "IGV", True),
    Theme("cybersecurity", "Cybersecurity", "CIBR", True),
    Theme("healthcare-glp1", "Healthcare and GLP-1", "XLV", True),
    Theme("airlines-travel", "Airlines and travel", "JETS", True),
    Theme("banks-payments", "Banks and payments", "XLF", True),
    Theme("energy", "Energy", "XLE", True),
    Theme("big-box-retail", "Big-box and consumer retail", "XLY", True),
]

MEMBERS: list[Member] = [
    # A.1 AI chips and semiconductors
    Member("NVDA", "NVIDIA", "ai-chips", DEV_START, "GPU maker since the 1990s"),
    Member("AMD", "AMD", "ai-chips", DEV_START, "CPU/GPU maker for decades"),
    Member("AVGO", "Broadcom", "ai-chips", DEV_START, "networking/custom silicon, long history"),
    Member("TSM", "TSMC", "ai-chips", DEV_START, "the foundry, decades"),
    Member("MRVL", "Marvell", "ai-chips", DEV_START, "data-infra silicon, long history"),
    Member("QCOM", "Qualcomm", "ai-chips", DEV_START, "mobile/edge silicon, decades"),
    Member("INTC", "Intel", "ai-chips", DEV_START,
           "kept deliberately — missed the AI wave; losers stay in to fight survivorship bias"),
    Member("ARM", "Arm Holdings", "ai-chips", date(2023, 9, 1), "2023-09 IPO"),
    # A.2 AI memory and storage (basket only, hindsight-curated)
    Member("MU", "Micron", "ai-memory-storage", DEV_START, "memory manufacturer since the 1980s"),
    Member("WDC", "Western Digital", "ai-memory-storage", DEV_START, "drives/flash for decades"),
    Member("STX", "Seagate", "ai-memory-storage", DEV_START, "drives for decades"),
    Member("SNDK", "SanDisk", "ai-memory-storage", date(2025, 2, 1), "2025-02 spin-off from WDC"),
    Member("SIMO", "Silicon Motion", "ai-memory-storage", DEV_START,
           "NAND controllers, long history"),
    Member("PSTG", "Pure Storage", "ai-memory-storage", date(2015, 10, 1), "2015-10 IPO"),
    # A.3 Data centers and power (basket only, hindsight-curated)
    Member("VRT", "Vertiv", "data-centers-power", date(2020, 2, 1), "2020-02 listing"),
    Member("SMCI", "Super Micro", "data-centers-power", DEV_START,
           "servers since the 1990s; AI-server story from 2023"),
    Member("DELL", "Dell", "data-centers-power", DEV_START, "servers/infra, decades"),
    Member("ETN", "Eaton", "data-centers-power", DEV_START, "power management, decades"),
    Member("PWR", "Quanta Services", "data-centers-power", DEV_START,
           "grid construction, decades"),
    Member("CEG", "Constellation Energy", "data-centers-power", date(2022, 2, 1),
           "2022-02 spin-off"),
    Member("VST", "Vistra", "data-centers-power", date(2016, 10, 1), "2016-10 listing"),
    Member("NRG", "NRG Energy", "data-centers-power", DEV_START, "power generation, decades"),
    # A.4 Cloud and software
    Member("MSFT", "Microsoft", "cloud-software", DEV_START, "decades"),
    Member("GOOGL", "Alphabet", "cloud-software", DEV_START, "since 2004"),
    Member("AMZN", "Amazon", "cloud-software", DEV_START, "AWS since 2006"),
    Member("ORCL", "Oracle", "cloud-software", DEV_START, "decades"),
    Member("CRM", "Salesforce", "cloud-software", DEV_START, "since 2004"),
    Member("NOW", "ServiceNow", "cloud-software", date(2012, 6, 1), "2012-06 IPO"),
    Member("SNOW", "Snowflake", "cloud-software", date(2020, 9, 1), "2020-09 IPO"),
    Member("DDOG", "Datadog", "cloud-software", date(2019, 9, 1), "2019-09 IPO"),
    # A.5 Cybersecurity
    Member("PANW", "Palo Alto Networks", "cybersecurity", date(2012, 7, 1), "2012-07 IPO"),
    Member("FTNT", "Fortinet", "cybersecurity", date(2009, 1, 1), "since 2009"),
    Member("CRWD", "CrowdStrike", "cybersecurity", date(2019, 6, 1), "2019-06 IPO"),
    Member("ZS", "Zscaler", "cybersecurity", date(2018, 3, 1), "2018-03 IPO"),
    Member("OKTA", "Okta", "cybersecurity", date(2017, 4, 1), "2017-04 IPO"),
    Member("NET", "Cloudflare", "cybersecurity", date(2019, 9, 1), "2019-09 IPO"),
    Member("S", "SentinelOne", "cybersecurity", date(2021, 6, 1), "2021-06 IPO"),
    # A.6 Healthcare and GLP-1
    Member("LLY", "Eli Lilly", "healthcare-glp1", DEV_START, "decades; GLP-1 story from 2022"),
    Member("NVO", "Novo Nordisk", "healthcare-glp1", DEV_START,
           "decades; GLP-1 story from 2021"),
    Member("MRK", "Merck", "healthcare-glp1", DEV_START, "decades"),
    Member("PFE", "Pfizer", "healthcare-glp1", DEV_START,
           "kept deliberately — recent laggard; losers stay in"),
    Member("ABBV", "AbbVie", "healthcare-glp1", date(2013, 1, 1), "2013-01 spin-off"),
    Member("AMGN", "Amgen", "healthcare-glp1", DEV_START, "decades"),
    Member("UNH", "UnitedHealth", "healthcare-glp1", DEV_START, "decades"),
    # A.7 Airlines and travel
    Member("DAL", "Delta", "airlines-travel", date(2007, 5, 1), "2007-05 relisting"),
    Member("UAL", "United", "airlines-travel", date(2006, 2, 1), "2006-02 relisting"),
    Member("AAL", "American", "airlines-travel", date(2013, 12, 1), "2013-12 merger listing"),
    Member("LUV", "Southwest", "airlines-travel", DEV_START, "decades"),
    Member("ALK", "Alaska Air", "airlines-travel", DEV_START, "decades"),
    Member("BKNG", "Booking", "airlines-travel", DEV_START, "since the 2000s"),
    Member("ABNB", "Airbnb", "airlines-travel", date(2020, 12, 1), "2020-12 IPO"),
    Member("RCL", "Royal Caribbean", "airlines-travel", DEV_START, "decades"),
    Member("MAR", "Marriott", "airlines-travel", DEV_START, "decades"),
    # A.8 Banks and payments
    Member("JPM", "JPMorgan", "banks-payments", DEV_START, "decades"),
    Member("BAC", "Bank of America", "banks-payments", DEV_START, "decades"),
    Member("WFC", "Wells Fargo", "banks-payments", DEV_START, "decades"),
    Member("GS", "Goldman Sachs", "banks-payments", DEV_START, "since 1999"),
    Member("MS", "Morgan Stanley", "banks-payments", DEV_START, "decades"),
    Member("V", "Visa", "banks-payments", date(2008, 3, 1), "2008-03 IPO"),
    Member("MA", "Mastercard", "banks-payments", date(2006, 5, 1), "2006-05 IPO"),
    Member("AXP", "American Express", "banks-payments", DEV_START, "decades"),
    Member("PYPL", "PayPal", "banks-payments", date(2015, 7, 1), "2015-07 spin-off"),
    # A.9 Energy
    Member("XOM", "ExxonMobil", "energy", DEV_START, "decades"),
    Member("CVX", "Chevron", "energy", DEV_START, "decades"),
    Member("COP", "ConocoPhillips", "energy", DEV_START, "decades"),
    Member("EOG", "EOG Resources", "energy", DEV_START, "decades"),
    Member("SLB", "SLB (Schlumberger)", "energy", DEV_START, "decades"),
    Member("OXY", "Occidental", "energy", DEV_START, "decades"),
    # A.10 Big-box and consumer retail
    Member("WMT", "Walmart", "big-box-retail", DEV_START, "decades"),
    Member("COST", "Costco", "big-box-retail", DEV_START, "decades"),
    Member("TGT", "Target", "big-box-retail", DEV_START,
           "kept deliberately — recent laggard; losers stay in"),
    Member("HD", "Home Depot", "big-box-retail", DEV_START, "decades"),
    Member("LOW", "Lowe's", "big-box-retail", DEV_START, "decades"),
    Member("MCD", "McDonald's", "big-box-retail", DEV_START, "decades"),
]

ETFS: list[Instrument] = [
    Instrument("SMH", "VanEck Semiconductor ETF", "etf"),
    Instrument("IGV", "iShares Expanded Tech-Software ETF", "etf"),
    Instrument("CIBR", "First Trust NASDAQ Cybersecurity ETF", "etf"),
    Instrument("XLV", "Health Care Select Sector SPDR", "etf"),
    Instrument("JETS", "U.S. Global Jets ETF", "etf"),
    Instrument("XLF", "Financial Select Sector SPDR", "etf"),
    Instrument("XLE", "Energy Select Sector SPDR", "etf"),
    Instrument("XLY", "Consumer Discretionary Select Sector SPDR", "etf"),
]

BENCHMARKS: list[Instrument] = [
    Instrument("VTI", "Vanguard Total Stock Market ETF", "benchmark"),
    Instrument("SPY", "SPDR S&P 500 ETF (Faber calibration)", "benchmark"),
    Instrument("BIL", "SPDR 1-3 Month T-Bill ETF (cash proxy)", "benchmark"),
]


def all_tickers() -> list[str]:
    """Every ticker compass ingests: members, theme ETFs, benchmarks."""
    return (
        [m.ticker for m in MEMBERS]
        + [e.ticker for e in ETFS]
        + [b.ticker for b in BENCHMARKS]
    )


def active_members(theme_slug: str, on: date) -> list[Member]:
    """Point-in-time membership: member_since <= on < member_until (rulebook §4)."""
    return [
        m for m in MEMBERS
        if m.theme_slug == theme_slug
        and m.member_since <= on
        and (m.member_until is None or on < m.member_until)
    ]
