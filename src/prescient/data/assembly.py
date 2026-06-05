from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from prescient.data.models import (
    DataProviderError,
    EarningsCalendarResult,
    EarningsCalendarSnapshot,
    HistoricalPriceCandle,
    HistoricalPriceResult,
    NewsSentimentResult,
    PeerListResult,
    PeerListSnapshot,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    IndicatorFreshness,
    MacdState,
    OptionContractSnapshot,
    PeerResult,
    PriceVsVwapState,
    StrategySettings,
    StrategyUniverse,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)

ReportTime = Literal["BMO", "AMC", "UNKNOWN"]


class EarningsCalendarProvider(Protocol):
    def get_earnings_calendar(
        self,
        date_from: date,
        date_to: date,
        tickers: Sequence[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> EarningsCalendarResult:
        ...


class StockPeersProvider(Protocol):
    def get_stock_peers(
        self,
        ticker: str,
        *,
        fetched_at: datetime | None = None,
    ) -> PeerListResult:
        ...


class HistoricalMarketDataProvider(Protocol):
    def get_historical_prices(
        self,
        ticker: str,
        date_from: date,
        date_to: date,
        fetched_at: datetime | None = None,
    ) -> HistoricalPriceResult:
        ...


class NewsProvider(Protocol):
    def get_news_sentiment(
        self,
        *,
        tickers: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        time_from: str | None = None,
        time_to: str | None = None,
        sort: str | None = None,
        limit: int | None = None,
        fetched_at: datetime | None = None,
    ) -> NewsSentimentResult:
        ...


@dataclass(frozen=True)
class PipelineInputProviders:
    earnings: EarningsCalendarProvider
    market_data: HistoricalMarketDataProvider
    peers: StockPeersProvider | None = None
    news: NewsProvider | None = None


class PipelineInputAssemblySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runup_trading_days: int = 21
    avg_volume_trading_days: int = 30
    price_history_padding_days: int = 70
    vwap_band_pct: float = 0.5
    news_min_relevance: float = 0.35
    news_bearish_score: float = -0.35
    news_limit: int = 10


@dataclass(frozen=True)
class PipelineInputAssemblyResult:
    universe: StrategyUniverse
    current_date: date
    upcoming_events: list[EarningsCalendarEvent]
    peer_results: list[PeerResult]
    target_market_data: dict[str, TargetMarketData]
    options_chains: dict[str, list[OptionContractSnapshot]]
    indicator_snapshots: dict[str, TechnicalIndicatorSnapshot]
    provider_errors: list[DataProviderError] = field(default_factory=list)
    skipped_targets: list[str] = field(default_factory=list)
    peer_list_snapshots: list[PeerListSnapshot] = field(default_factory=list)
    provider_snapshots: list[dict[str, Any]] = field(default_factory=list)


_DEFAULT_STRATEGY_SETTINGS = StrategySettings()
_DEFAULT_ASSEMBLY_SETTINGS = PipelineInputAssemblySettings()


def assemble_pipeline_inputs(
    *,
    universe: StrategyUniverse,
    current_date: date,
    providers: PipelineInputProviders,
    strategy_settings: StrategySettings = _DEFAULT_STRATEGY_SETTINGS,
    assembly_settings: PipelineInputAssemblySettings = _DEFAULT_ASSEMBLY_SETTINGS,
    fetched_at: datetime | None = None,
) -> PipelineInputAssemblyResult:
    tickers = universe.all_tickers()
    upcoming_result = providers.earnings.get_earnings_calendar(
        current_date,
        current_date + timedelta(days=strategy_settings.earnings_window_days),
        tickers=tickers,
        fetched_at=fetched_at,
    )
    completed_result = providers.earnings.get_earnings_calendar(
        current_date - timedelta(days=strategy_settings.peer_result_window_days),
        current_date,
        tickers=tickers,
        fetched_at=fetched_at,
    )

    provider_errors: list[DataProviderError] = [
        *upcoming_result.errors,
        *completed_result.errors,
    ]
    upcoming_events = _upcoming_events_from_snapshots(
        upcoming_result.snapshots,
        universe=universe,
        current_date=current_date,
        strategy_settings=strategy_settings,
    )
    completed_events = _completed_events_from_snapshots(
        completed_result.snapshots,
        universe=universe,
        current_date=current_date,
        strategy_settings=strategy_settings,
    )

    peer_list_snapshots, peer_list_errors = _fetch_peer_diagnostics(
        providers.peers,
        upcoming_events,
        fetched_at=fetched_at,
    )
    provider_errors.extend(peer_list_errors)

    market_cache: dict[str, HistoricalPriceResult] = {}
    target_market_data: dict[str, TargetMarketData] = {}
    indicator_snapshots: dict[str, TechnicalIndicatorSnapshot] = {}
    skipped_targets: set[str] = set()

    for event in upcoming_events:
        market_result = _market_result_for(
            event.ticker,
            providers=providers,
            market_cache=market_cache,
            current_date=current_date,
            strategy_settings=strategy_settings,
            assembly_settings=assembly_settings,
            fetched_at=fetched_at,
        )
        provider_errors.extend(market_result.errors)
        if market_result.candles:
            news_result = _news_result_for(
                event.ticker,
                providers=providers,
                assembly_settings=assembly_settings,
                fetched_at=fetched_at,
            )
            if news_result is not None:
                provider_errors.extend(news_result.errors)
            target_market_data[event.ticker] = derive_target_market_data(
                ticker=event.ticker,
                candles=market_result.candles,
                news_result=news_result,
                settings=assembly_settings,
            )
            indicator_snapshots[event.ticker] = derive_indicator_snapshot(
                ticker=event.ticker,
                candles=market_result.candles,
                as_of=current_date,
                settings=assembly_settings,
            )
        else:
            skipped_targets.add(event.ticker)

    peer_results: list[PeerResult] = []
    for event in completed_events:
        market_result = _market_result_for(
            event.ticker,
            providers=providers,
            market_cache=market_cache,
            current_date=current_date,
            strategy_settings=strategy_settings,
            assembly_settings=assembly_settings,
            fetched_at=fetched_at,
        )
        provider_errors.extend(market_result.errors)
        peer_results.append(
            PeerResult(
                ticker=event.ticker,
                earnings_event=event,
                price_reaction_pct=derive_price_reaction_pct(
                    candles=market_result.candles,
                    earnings_date=event.earnings_date,
                    report_time=event.report_time,
                ),
                guidance_signal="unknown",
                theme_driver_signal="unknown",
            )
        )

    return PipelineInputAssemblyResult(
        universe=universe,
        current_date=current_date,
        upcoming_events=upcoming_events,
        peer_results=peer_results,
        target_market_data=target_market_data,
        options_chains={event.ticker: [] for event in upcoming_events},
        indicator_snapshots=indicator_snapshots,
        provider_errors=_dedupe_provider_errors(provider_errors),
        skipped_targets=sorted(skipped_targets),
        peer_list_snapshots=peer_list_snapshots,
        provider_snapshots=[],
    )


def derive_target_market_data(
    *,
    ticker: str,
    candles: Sequence[HistoricalPriceCandle],
    news_result: NewsSentimentResult | None = None,
    settings: PipelineInputAssemblySettings = _DEFAULT_ASSEMBLY_SETTINGS,
) -> TargetMarketData:
    ordered = _ordered_candles(candles)
    return TargetMarketData(
        ticker=ticker,
        avg_daily_volume=_average_volume(
            ordered,
            trading_days=settings.avg_volume_trading_days,
        ),
        pre_earnings_runup_pct=_runup_pct(
            ordered,
            trading_days=settings.runup_trading_days,
        ),
        has_conflicting_news=_has_conflicting_news(
            ticker=ticker,
            news_result=news_result,
            settings=settings,
        ),
    )


def derive_price_reaction_pct(
    *,
    candles: Sequence[HistoricalPriceCandle],
    earnings_date: date,
    report_time: str,
) -> float | None:
    ordered = _ordered_candles(candles)
    previous = _last_candle_before(ordered, earnings_date)
    if previous is None or previous.close == 0:
        return None

    normalized_time = report_time.strip().upper()
    reaction_candle = (
        _first_candle_on_or_after(ordered, earnings_date)
        if normalized_time == "BMO"
        else _first_candle_after(ordered, earnings_date)
    )
    if reaction_candle is None:
        return None
    return round(((reaction_candle.close - previous.close) / previous.close) * 100, 4)


def derive_indicator_snapshot(
    *,
    ticker: str,
    candles: Sequence[HistoricalPriceCandle],
    as_of: date,
    settings: PipelineInputAssemblySettings = _DEFAULT_ASSEMBLY_SETTINGS,
) -> TechnicalIndicatorSnapshot:
    ordered = _ordered_candles(candles)
    closes = [candle.close for candle in ordered]
    latest = ordered[-1] if ordered else None

    rsi_14 = _rsi_14(closes)
    macd_line, macd_signal, macd_histogram = _macd(closes)
    vwap = latest.vwap if latest is not None else None
    price_vs_vwap = _price_vs_vwap(
        latest.close if latest is not None else None,
        vwap,
        band_pct=settings.vwap_band_pct,
    )

    missing_fields: list[str] = []
    values = {
        "rsi_14": rsi_14,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_histogram": macd_histogram,
        "vwap": vwap,
    }
    for field_name, value in values.items():
        if value is None:
            missing_fields.append(field_name)

    return TechnicalIndicatorSnapshot(
        ticker=ticker,
        as_of=as_of,
        rsi_14=rsi_14,
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
        macd_state=_macd_state(macd_line, macd_signal),
        vwap=vwap,
        price_vs_vwap=price_vs_vwap,
        missing_fields=missing_fields,
        source="fmp",
        freshness=_freshness(latest.trading_date if latest is not None else None, as_of),
    )


def _upcoming_events_from_snapshots(
    snapshots: Sequence[EarningsCalendarSnapshot],
    *,
    universe: StrategyUniverse,
    current_date: date,
    strategy_settings: StrategySettings,
) -> list[EarningsCalendarEvent]:
    window_end = current_date + timedelta(days=strategy_settings.earnings_window_days)
    events: list[EarningsCalendarEvent] = []
    seen: set[str] = set()
    for snapshot in snapshots:
        if snapshot.ticker in seen or not universe.contains_ticker(snapshot.ticker):
            continue
        if snapshot.earnings_date is None or not current_date <= snapshot.earnings_date <= window_end:
            continue
        if snapshot.eps_actual is not None or snapshot.revenue_actual is not None:
            continue
        seen.add(snapshot.ticker)
        events.append(
            EarningsCalendarEvent(
                ticker=snapshot.ticker,
                earnings_date=snapshot.earnings_date,
                report_time=_report_time(snapshot.report_time),
                eps_estimate=snapshot.eps_estimate,
                revenue_estimate=snapshot.revenue_estimate,
                source_citations=snapshot.source_citations,
            )
        )
    return events


def _completed_events_from_snapshots(
    snapshots: Sequence[EarningsCalendarSnapshot],
    *,
    universe: StrategyUniverse,
    current_date: date,
    strategy_settings: StrategySettings,
) -> list[EarningsEvent]:
    earliest = current_date - timedelta(days=strategy_settings.peer_result_window_days)
    events: list[EarningsEvent] = []
    seen: set[str] = set()
    for snapshot in snapshots:
        if snapshot.ticker in seen or not universe.contains_ticker(snapshot.ticker):
            continue
        if snapshot.earnings_date is None or not earliest <= snapshot.earnings_date <= current_date:
            continue
        if snapshot.eps_actual is None and snapshot.revenue_actual is None:
            continue
        seen.add(snapshot.ticker)
        events.append(
            EarningsEvent(
                ticker=snapshot.ticker,
                earnings_date=snapshot.earnings_date,
                report_time=_report_time(snapshot.report_time),
                eps_estimate=snapshot.eps_estimate,
                eps_actual=snapshot.eps_actual,
                revenue_estimate=snapshot.revenue_estimate,
                revenue_actual=snapshot.revenue_actual,
                source_citations=snapshot.source_citations,
            )
        )
    return events


def _fetch_peer_diagnostics(
    provider: StockPeersProvider | None,
    upcoming_events: Sequence[EarningsCalendarEvent],
    *,
    fetched_at: datetime | None,
) -> tuple[list[PeerListSnapshot], list[DataProviderError]]:
    if provider is None:
        return [], []
    snapshots: list[PeerListSnapshot] = []
    errors: list[DataProviderError] = []
    for event in upcoming_events:
        result = provider.get_stock_peers(event.ticker, fetched_at=fetched_at)
        snapshots.extend(result.snapshots)
        errors.extend(result.errors)
    return snapshots, errors


def _market_result_for(
    ticker: str,
    *,
    providers: PipelineInputProviders,
    market_cache: dict[str, HistoricalPriceResult],
    current_date: date,
    strategy_settings: StrategySettings,
    assembly_settings: PipelineInputAssemblySettings,
    fetched_at: datetime | None,
) -> HistoricalPriceResult:
    normalized = ticker.strip().upper()
    if normalized not in market_cache:
        lookback_days = (
            strategy_settings.peer_result_window_days
            + assembly_settings.runup_trading_days
            + assembly_settings.avg_volume_trading_days
            + assembly_settings.price_history_padding_days
        )
        market_cache[normalized] = providers.market_data.get_historical_prices(
            normalized,
            date_from=current_date - timedelta(days=lookback_days),
            date_to=current_date + timedelta(days=5),
            fetched_at=fetched_at,
        )
    return market_cache[normalized]


def _news_result_for(
    ticker: str,
    *,
    providers: PipelineInputProviders,
    assembly_settings: PipelineInputAssemblySettings,
    fetched_at: datetime | None,
) -> NewsSentimentResult | None:
    if providers.news is None:
        return None
    return providers.news.get_news_sentiment(
        tickers=[ticker],
        limit=assembly_settings.news_limit,
        fetched_at=fetched_at,
    )


def _average_volume(
    candles: Sequence[HistoricalPriceCandle],
    *,
    trading_days: int,
) -> int | None:
    values = [candle.volume for candle in candles[-trading_days:] if candle.volume is not None]
    if not values:
        return None
    return round(sum(values) / len(values))


def _runup_pct(
    candles: Sequence[HistoricalPriceCandle],
    *,
    trading_days: int,
) -> float | None:
    if len(candles) <= trading_days:
        return None
    previous = candles[-trading_days - 1]
    latest = candles[-1]
    if previous.close == 0:
        return None
    return round(((latest.close - previous.close) / previous.close) * 100, 4)


def _has_conflicting_news(
    *,
    ticker: str,
    news_result: NewsSentimentResult | None,
    settings: PipelineInputAssemblySettings,
) -> bool:
    if news_result is None or news_result.errors:
        return False
    normalized = ticker.strip().upper()
    for snapshot in news_result.snapshots:
        for article in snapshot.articles:
            for sentiment in article.ticker_sentiment:
                if sentiment.ticker != normalized:
                    continue
                relevance = sentiment.relevance_score
                if relevance is None or relevance < settings.news_min_relevance:
                    continue
                if sentiment.sentiment_score is not None:
                    if sentiment.sentiment_score <= settings.news_bearish_score:
                        return True
                elif (sentiment.sentiment_label or "").strip().lower() == "bearish":
                    return True
    return False


def _ordered_candles(
    candles: Sequence[HistoricalPriceCandle],
) -> list[HistoricalPriceCandle]:
    return sorted(candles, key=lambda candle: candle.trading_date)


def _last_candle_before(
    candles: Sequence[HistoricalPriceCandle],
    trading_date: date,
) -> HistoricalPriceCandle | None:
    previous = [candle for candle in candles if candle.trading_date < trading_date]
    return previous[-1] if previous else None


def _first_candle_on_or_after(
    candles: Sequence[HistoricalPriceCandle],
    trading_date: date,
) -> HistoricalPriceCandle | None:
    for candle in candles:
        if candle.trading_date >= trading_date:
            return candle
    return None


def _first_candle_after(
    candles: Sequence[HistoricalPriceCandle],
    trading_date: date,
) -> HistoricalPriceCandle | None:
    for candle in candles:
        if candle.trading_date > trading_date:
            return candle
    return None


def _rsi_14(closes: Sequence[float]) -> float | None:
    if len(closes) < 15:
        return None
    changes = [closes[idx] - closes[idx - 1] for idx in range(len(closes) - 14, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [abs(min(change, 0.0)) for change in changes]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    relative_strength = avg_gain / avg_loss
    return round(100 - (100 / (1 + relative_strength)), 4)


def _macd(closes: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    if len(closes) < 35:
        return None, None, None
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd_values = [
        fast - slow
        for fast, slow in zip(ema_12, ema_26, strict=True)
        if fast is not None and slow is not None
    ]
    if len(macd_values) < 9:
        return None, None, None
    signal_values = _ema(macd_values, 9)
    macd_line = macd_values[-1]
    macd_signal = signal_values[-1]
    if macd_signal is None:
        return None, None, None
    macd_histogram = macd_line - macd_signal
    return round(macd_line, 4), round(macd_signal, 4), round(macd_histogram, 4)


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None for _ in values]
    multiplier = 2 / (period + 1)
    results: list[float | None] = [None for _ in range(period - 1)]
    current = sum(values[:period]) / period
    results.append(current)
    for value in values[period:]:
        current = (value - current) * multiplier + current
        results.append(current)
    return results


def _price_vs_vwap(
    close: float | None,
    vwap: float | None,
    *,
    band_pct: float,
) -> PriceVsVwapState:
    if close is None or vwap is None or vwap == 0:
        return PriceVsVwapState.UNKNOWN
    diff_pct = ((close - vwap) / vwap) * 100
    if diff_pct > band_pct:
        return PriceVsVwapState.ABOVE
    if diff_pct < -band_pct:
        return PriceVsVwapState.BELOW
    return PriceVsVwapState.NEAR


def _macd_state(
    macd_line: float | None,
    macd_signal: float | None,
) -> MacdState:
    if macd_line is None or macd_signal is None:
        return MacdState.UNKNOWN
    if macd_line > macd_signal:
        return MacdState.BULLISH
    if macd_line < macd_signal:
        return MacdState.BEARISH
    return MacdState.NEUTRAL


def _freshness(
    latest_date: date | None,
    as_of: date,
) -> IndicatorFreshness:
    if latest_date is None:
        return IndicatorFreshness.UNKNOWN
    return (
        IndicatorFreshness.CURRENT
        if 0 <= (as_of - latest_date).days <= 3
        else IndicatorFreshness.STALE
    )


def _report_time(value: str) -> ReportTime:
    normalized = value.strip().upper()
    if normalized in {"BMO", "AMC"}:
        return normalized  # type: ignore[return-value]
    return "UNKNOWN"


def _dedupe_provider_errors(
    errors: Sequence[DataProviderError],
) -> list[DataProviderError]:
    deduped: list[DataProviderError] = []
    seen: set[tuple[str, str, str | None, str | None, int | None]] = set()
    for error in errors:
        key = (
            error.provider.value,
            error.error_type.value,
            error.endpoint,
            error.symbol,
            error.status_code,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(error)
    return deduped
