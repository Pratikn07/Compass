from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from prescient.data import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    EarningsCalendarResult,
    EarningsCalendarSnapshot,
    HistoricalPriceCandle,
    HistoricalPriceResult,
    NewsArticle,
    NewsSentimentResult,
    NewsSentimentSnapshot,
    NewsTickerSentiment,
    PeerListResult,
    PeerListSnapshot,
)
from prescient.data.assembly import (
    PipelineInputAssemblySettings,
    PipelineInputProviders,
    assemble_pipeline_inputs,
    derive_indicator_snapshot,
    derive_price_reaction_pct,
    derive_target_market_data,
)
from prescient.signal.models import PriceVsVwapState, StrategySettings, StrategyUniverse, ThemeConfig


class FakeEarningsProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date, list[str] | None]] = []

    def get_earnings_calendar(
        self,
        date_from: date,
        date_to: date,
        tickers: list[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> EarningsCalendarResult:
        self.calls.append((date_from, date_to, list(tickers) if tickers else None))
        if date_from == date(2026, 6, 1):
            return EarningsCalendarResult(
                snapshots=[
                    EarningsCalendarSnapshot(
                        ticker="ntnx",
                        earnings_date=date(2026, 6, 2),
                        report_time="AMC",
                        eps_estimate=1.1,
                        revenue_estimate=1000.0,
                        provider=DataProvider.FINNHUB,
                        source_endpoint="/calendar/earnings",
                        fetched_at=fetched_at,
                    )
                ]
            )
        return EarningsCalendarResult(
            snapshots=[
                EarningsCalendarSnapshot(
                    ticker="ntap",
                    earnings_date=date(2026, 5, 20),
                    report_time="BMO",
                    eps_estimate=1.0,
                    eps_actual=1.2,
                    revenue_estimate=100.0,
                    revenue_actual=110.0,
                    provider=DataProvider.FINNHUB,
                    source_endpoint="/calendar/earnings",
                    fetched_at=fetched_at,
                ),
                EarningsCalendarSnapshot(
                    ticker="pstg",
                    earnings_date=date(2026, 5, 20),
                    report_time="AMC",
                    eps_estimate=1.0,
                    eps_actual=1.2,
                    revenue_estimate=100.0,
                    revenue_actual=111.0,
                    provider=DataProvider.FINNHUB,
                    source_endpoint="/calendar/earnings",
                    fetched_at=fetched_at,
                ),
                EarningsCalendarSnapshot(
                    ticker="msft",
                    earnings_date=date(2026, 5, 20),
                    report_time="BMO",
                    eps_actual=1.2,
                    provider=DataProvider.FINNHUB,
                    source_endpoint="/calendar/earnings",
                    fetched_at=fetched_at,
                ),
            ]
        )


class FakePeerProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_stock_peers(
        self,
        ticker: str,
        *,
        fetched_at: datetime | None = None,
    ) -> PeerListResult:
        self.calls.append(ticker.strip().upper())
        return PeerListResult(
            snapshots=[
                PeerListSnapshot(
                    ticker=ticker,
                    peers=["PSTG", "MSFT", "NTAP"],
                    provider=DataProvider.FMP,
                    source_endpoint="/stock-peers",
                    fetched_at=fetched_at,
                )
            ]
        )


class FakeMarketProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_historical_prices(
        self,
        ticker: str,
        date_from: date,
        date_to: date,
        fetched_at: datetime | None = None,
    ) -> HistoricalPriceResult:
        symbol = ticker.strip().upper()
        self.calls.append(symbol)
        if symbol == "PSTG":
            return HistoricalPriceResult(candles=_peer_candles(symbol, amc=True))
        if symbol == "NTAP":
            return HistoricalPriceResult(candles=_peer_candles(symbol, amc=False))
        return HistoricalPriceResult(candles=_target_candles(symbol))


class FakeNewsProvider:
    def get_news_sentiment(
        self,
        *,
        tickers: list[str] | None = None,
        topics: list[str] | None = None,
        time_from: str | None = None,
        time_to: str | None = None,
        sort: str | None = None,
        limit: int | None = None,
        fetched_at: datetime | None = None,
    ) -> NewsSentimentResult:
        ticker = (tickers or ["NTNX"])[0].strip().upper()
        return NewsSentimentResult(
            snapshots=[
                NewsSentimentSnapshot(
                    query_tickers=[ticker],
                    articles=[
                        NewsArticle(
                            title="Target faces demand concern",
                            url="https://example.test/news",
                            ticker_sentiment=[
                                NewsTickerSentiment(
                                    ticker=ticker,
                                    relevance_score=0.5,
                                    sentiment_score=-0.4,
                                    sentiment_label="Somewhat-Bearish",
                                )
                            ],
                        )
                    ],
                    provider=DataProvider.ALPHA_VANTAGE,
                    source_endpoint="/query?function=NEWS_SENTIMENT",
                    fetched_at=fetched_at,
                )
            ]
        )


class FailingMarketProvider(FakeMarketProvider):
    def get_historical_prices(
        self,
        ticker: str,
        date_from: date,
        date_to: date,
        fetched_at: datetime | None = None,
    ) -> HistoricalPriceResult:
        return HistoricalPriceResult(
            errors=[
                DataProviderError(
                    provider=DataProvider.FMP,
                    error_type=DataProviderErrorType.RATE_LIMITED,
                    message="FMP historical prices were rate limited.",
                    endpoint="/historical-price-eod/full",
                    symbol=ticker,
                )
            ]
        )


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG"],
                drivers=["AI data center demand"],
            )
        ]
    )


def _candle(ticker: str, trading_date: date, close: float, volume: int = 2_000_000) -> HistoricalPriceCandle:
    return HistoricalPriceCandle(
        ticker=ticker,
        trading_date=trading_date,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=volume,
        vwap=close - 1.0,
        provider=DataProvider.FMP,
        source_endpoint="/historical-price-eod/full",
    )


def _target_candles(ticker: str) -> list[HistoricalPriceCandle]:
    start = date(2026, 4, 22)
    candles: list[HistoricalPriceCandle] = []
    for index in range(35):
        close = 100.0 + index
        candles.append(_candle(ticker, start + timedelta(days=index), close))
    candles[-22] = candles[-22].model_copy(update={"close": 120.0, "vwap": 119.0})
    candles[-1] = candles[-1].model_copy(update={"close": 132.0, "vwap": 130.0})
    return candles


def _peer_candles(ticker: str, *, amc: bool) -> list[HistoricalPriceCandle]:
    if amc:
        return [
            _candle(ticker, date(2026, 5, 19), 100.0),
            _candle(ticker, date(2026, 5, 20), 102.0),
            _candle(ticker, date(2026, 5, 21), 106.0),
        ]
    return [
        _candle(ticker, date(2026, 5, 19), 100.0),
        _candle(ticker, date(2026, 5, 20), 104.0),
    ]


def test_derive_target_market_data_uses_21_day_runup_and_conservative_news() -> None:
    target = derive_target_market_data(
        ticker="ntnx",
        candles=_target_candles("NTNX"),
        news_result=FakeNewsProvider().get_news_sentiment(tickers=["NTNX"]),
        settings=PipelineInputAssemblySettings(runup_trading_days=21),
    )

    assert target.avg_daily_volume == 2_000_000
    assert target.pre_earnings_runup_pct == 10.0
    assert target.has_conflicting_news is True


def test_derive_price_reaction_uses_report_time_rule() -> None:
    bmo = derive_price_reaction_pct(
        candles=_peer_candles("NTAP", amc=False),
        earnings_date=date(2026, 5, 20),
        report_time="BMO",
    )
    amc = derive_price_reaction_pct(
        candles=_peer_candles("PSTG", amc=True),
        earnings_date=date(2026, 5, 20),
        report_time="AMC",
    )

    assert bmo == 4.0
    assert amc == 6.0


def test_derive_indicator_snapshot_marks_missing_values_and_vwap_state() -> None:
    sparse = derive_indicator_snapshot(
        ticker="NTNX",
        candles=_target_candles("NTNX")[-10:],
        as_of=date(2026, 6, 1),
    )
    complete = derive_indicator_snapshot(
        ticker="NTNX",
        candles=_target_candles("NTNX"),
        as_of=date(2026, 6, 1),
    )

    assert sparse.rsi_14 is None
    assert "rsi_14" in sparse.missing_fields
    assert "macd_line" in sparse.missing_fields
    assert complete.rsi_14 is not None
    assert complete.price_vs_vwap == PriceVsVwapState.ABOVE
    assert complete.vwap == 130.0


def test_assemble_pipeline_inputs_builds_runtime_ready_inputs_without_expanding_peers() -> None:
    earnings = FakeEarningsProvider()
    market = FakeMarketProvider()
    peers = FakePeerProvider()
    result = assemble_pipeline_inputs(
        universe=_universe(),
        current_date=date(2026, 6, 1),
        providers=PipelineInputProviders(
            earnings=earnings,
            market_data=market,
            peers=peers,
            news=FakeNewsProvider(),
        ),
        strategy_settings=StrategySettings(earnings_window_days=1, peer_result_window_days=21),
        assembly_settings=PipelineInputAssemblySettings(runup_trading_days=21),
        fetched_at=datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc),
    )

    assert [event.ticker for event in result.upcoming_events] == ["NTNX"]
    assert [peer.ticker for peer in result.peer_results] == ["NTAP", "PSTG"]
    assert "MSFT" not in [peer.ticker for peer in result.peer_results]
    assert result.peer_results[0].price_reaction_pct == 4.0
    assert result.peer_results[1].price_reaction_pct == 6.0
    assert result.target_market_data["NTNX"].pre_earnings_runup_pct == 10.0
    assert result.target_market_data["NTNX"].has_conflicting_news is True
    assert result.indicator_snapshots["NTNX"].ticker == "NTNX"
    assert result.options_chains == {"NTNX": []}
    assert result.provider_errors == []
    assert sorted(market.calls) == ["NTAP", "NTNX", "PSTG"]
    assert peers.calls == ["NTNX"]


def test_assemble_pipeline_inputs_collects_provider_errors_without_crashing() -> None:
    result = assemble_pipeline_inputs(
        universe=_universe(),
        current_date=date(2026, 6, 1),
        providers=PipelineInputProviders(
            earnings=FakeEarningsProvider(),
            market_data=FailingMarketProvider(),
            peers=None,
            news=None,
        ),
        strategy_settings=StrategySettings(earnings_window_days=1, peer_result_window_days=21),
        fetched_at=datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc),
    )

    assert result.upcoming_events[0].ticker == "NTNX"
    assert result.target_market_data == {}
    assert result.options_chains == {"NTNX": []}
    assert {error.symbol for error in result.provider_errors} == {"NTAP", "NTNX", "PSTG"}
    assert result.skipped_targets == ["NTNX"]
