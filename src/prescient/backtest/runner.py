from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta

from prescient.backtest.models import (
    BacktestDataset,
    BacktestOutcome,
    BacktestRunRequest,
    BacktestRunResult,
    BacktestSetupResult,
    BacktestSummary,
    BacktestTradeExpression,
    HistoricalOptionQuote,
    HistoricalPricePoint,
    TradePnlOutcome,
)
from prescient.backtest.outcomes import (
    calculate_option_trade_pnl,
    calculate_stock_trade_pnl,
    calculate_underlying_followthrough,
)
from prescient.signal.core import evaluate_core_strategy
from prescient.signal.models import (
    EarningsCalendarEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategyDecision,
    StrategySettings,
    StrategyStatus,
)


_SUPPORTED_STRATEGY_TYPE = "bullish_earnings_readthrough"


def run_peer_readthrough_backtest(
    request: BacktestRunRequest,
    dataset: BacktestDataset,
) -> BacktestRunResult:
    warnings: list[str] = []

    if dataset.setup_results:
        setups = _bounded_setup_results(request, dataset.setup_results)
        return _result(request=request, setups=setups, warnings=warnings)

    if request.strategy_type != _SUPPORTED_STRATEGY_TYPE:
        warnings.append(f"unsupported_strategy_type:{request.strategy_type}")
        return _result(request=request, setups=[], warnings=warnings)

    if dataset.universe is None:
        warnings.append("missing_strategy_universe")
        return _result(request=request, setups=[], warnings=warnings)

    settings = dataset.settings
    price_index = _price_index(dataset.prices)
    quote_index = _option_quote_index(dataset.option_quotes)
    events = _bounded_events(request, dataset.upcoming_events)

    setups: list[BacktestSetupResult] = []
    for event in events:
        if event.earnings_date is None:
            warnings.append(f"missing_earnings_date:{event.ticker}")
            continue

        current_date = event.earnings_date - timedelta(days=settings.earnings_window_days)
        peer_results = _eligible_peer_results(
            peer_results=dataset.peer_results,
            target_event=event,
        )
        decisions = evaluate_core_strategy(
            universe=dataset.universe,
            upcoming_events=[event],
            peer_results=peer_results,
            target_market_data=dataset.target_market_data,
            options_chains=dataset.options_chains,
            current_date=current_date,
            settings=settings,
        )

        for index, decision in enumerate(decisions):
            if (
                decision.status == StrategyStatus.REJECTED_WITH_REASON
                and not request.include_rejected_candidates
            ):
                continue
            setups.append(
                _setup_result(
                    request=request,
                    event=event,
                    decision=decision,
                    decision_index=index,
                    settings=settings,
                    price_index=price_index,
                    quote_index=quote_index,
                    options_chains=dataset.options_chains,
                )
            )

    return _result(request=request, setups=setups, warnings=warnings)


def _result(
    *,
    request: BacktestRunRequest,
    setups: list[BacktestSetupResult],
    warnings: list[str],
) -> BacktestRunResult:
    summary = BacktestSummary.from_setups(setups, request=request, warnings=warnings)
    result_warnings = [*warnings, *summary.warnings]
    return BacktestRunResult(
        run_id=request.run_id,
        request=request,
        setups=setups,
        summary=summary,
        warnings=result_warnings,
    )


def _bounded_setup_results(
    request: BacktestRunRequest,
    setups: list[BacktestSetupResult],
) -> list[BacktestSetupResult]:
    bounded = [
        setup
        for setup in setups
        if request.start_date <= setup.entry_date <= request.end_date
    ]
    if request.max_events is not None:
        return bounded[: request.max_events]
    return bounded


def _bounded_events(
    request: BacktestRunRequest,
    events: list[EarningsCalendarEvent],
) -> list[EarningsCalendarEvent]:
    filtered = [
        event
        for event in events
        if event.earnings_date is not None
        and request.start_date <= event.earnings_date <= request.end_date
    ]
    if request.max_events is not None:
        return filtered[: request.max_events]
    return filtered


def _eligible_peer_results(
    *,
    peer_results: list[PeerResult],
    target_event: EarningsCalendarEvent,
) -> list[PeerResult]:
    if target_event.earnings_date is None:
        return []
    return [
        peer
        for peer in peer_results
        if peer.ticker != target_event.ticker
        and peer.earnings_event.earnings_date < target_event.earnings_date
    ]


def _setup_result(
    *,
    request: BacktestRunRequest,
    event: EarningsCalendarEvent,
    decision: StrategyDecision,
    decision_index: int,
    settings: StrategySettings,
    price_index: Mapping[tuple[str, date], HistoricalPricePoint],
    quote_index: Mapping[
        tuple[str, BacktestTradeExpression, date, date],
        HistoricalOptionQuote,
    ],
    options_chains: Mapping[str, list[OptionContractSnapshot]],
) -> BacktestSetupResult:
    entry_date = event.earnings_date
    if entry_date is None:
        raise ValueError("Backtest setup requires an earnings date.")

    exit_date = entry_date + timedelta(days=request.evaluation_horizon_days)
    target = decision.audit.target
    entry_price = _close_price(price_index, target, entry_date)
    exit_price = _close_price(price_index, target, exit_date)
    underlying = calculate_underlying_followthrough(
        ticker=target,
        entry_price=entry_price,
        exit_price=exit_price,
        evaluation_start=entry_date,
        evaluation_end=exit_date,
        positive_threshold_pct=request.positive_followthrough_threshold_pct,
        negative_threshold_pct=request.negative_followthrough_threshold_pct,
    )

    recommended_expression = _recommended_expression(decision)
    trade_pnl = _trade_pnl(
        request=request,
        target=target,
        expression=recommended_expression,
        entry_date=entry_date,
        exit_date=exit_date,
        entry_price=entry_price,
        exit_price=exit_price,
        quote_index=quote_index,
        options_chains=options_chains,
        settings=settings,
    )
    allocated_capital = _allocated_capital(
        expression=recommended_expression,
        entry_price=entry_price,
        trade_pnl=trade_pnl,
    )

    candidate = decision.candidate
    return BacktestSetupResult(
        setup_id=f"{request.run_id}:{target}:{entry_date.isoformat()}:{decision_index}",
        target=target,
        ticker=target,
        theme=candidate.theme if candidate is not None else decision.audit.theme,
        earnings_date=candidate.earnings_date if candidate is not None else entry_date,
        entry_date=entry_date,
        exit_date=exit_date,
        strategy_status=decision.status,
        recommended_expression=recommended_expression,
        expression=recommended_expression or BacktestTradeExpression.STOCK,
        allocated_capital=allocated_capital,
        underlying_entry_price=entry_price,
        underlying_exit_price=exit_price,
        underlying_outcome=underlying,
        trade_pnl=trade_pnl,
        reported_peers=candidate.reported_peers if candidate is not None else [],
        rejection_reasons=[reason.value for reason in decision.rejection_reasons],
        warnings=_setup_warnings(underlying, trade_pnl),
    )


def _recommended_expression(
    decision: StrategyDecision,
) -> BacktestTradeExpression | None:
    if decision.candidate is None:
        return None
    try:
        return BacktestTradeExpression.normalize(decision.candidate.recommended_expression)
    except ValueError:
        return None


def _trade_pnl(
    *,
    request: BacktestRunRequest,
    target: str,
    expression: BacktestTradeExpression | None,
    entry_date: date,
    exit_date: date,
    entry_price: float | None,
    exit_price: float | None,
    quote_index: Mapping[
        tuple[str, BacktestTradeExpression, date, date],
        HistoricalOptionQuote,
    ],
    options_chains: Mapping[str, list[OptionContractSnapshot]],
    settings: StrategySettings,
) -> TradePnlOutcome | None:
    if not request.include_trade_pnl or expression is None:
        return None

    if expression == BacktestTradeExpression.STOCK:
        return calculate_stock_trade_pnl(
            ticker=target,
            expression=expression,
            quantity=1,
            entry_price=entry_price,
            exit_price=exit_price,
        )

    selected_option = _selected_call_option(
        target=target,
        entry_date=entry_date,
        chain=options_chains.get(target, []),
        settings=settings,
    )
    if selected_option is None:
        return calculate_option_trade_pnl(
            ticker=target,
            quantity=1,
            entry_quote=None,
            exit_quote=None,
        )

    entry_quote = quote_index.get(
        (
            target,
            BacktestTradeExpression.CALL_OPTION,
            selected_option.expiration_date,
            entry_date,
        )
    )
    exit_quote = quote_index.get(
        (
            target,
            BacktestTradeExpression.CALL_OPTION,
            selected_option.expiration_date,
            exit_date,
        )
    )
    return calculate_option_trade_pnl(
        ticker=target,
        quantity=1,
        entry_quote=entry_quote,
        exit_quote=exit_quote,
    )


def _selected_call_option(
    *,
    target: str,
    entry_date: date,
    chain: list[OptionContractSnapshot],
    settings: StrategySettings,
) -> OptionContractSnapshot | None:
    max_expiration = entry_date + timedelta(
        days=settings.max_option_expiration_days_after_earnings
    )
    for option in chain:
        if (
            option.ticker == target
            and option.option_type == "CALL"
            and entry_date <= option.expiration_date <= max_expiration
            and _has_liquid_option_quote(option, settings)
        ):
            return option
    return None


def _has_liquid_option_quote(
    option: OptionContractSnapshot,
    settings: StrategySettings,
) -> bool:
    if (
        option.bid is None
        or option.ask is None
        or option.open_interest is None
        or option.bid <= 0
        or option.ask <= 0
        or option.ask < option.bid
        or option.open_interest < settings.min_option_open_interest
    ):
        return False
    midpoint = (option.bid + option.ask) / 2
    spread_pct = ((option.ask - option.bid) / midpoint) * 100
    return spread_pct <= settings.max_options_bid_ask_spread_pct


def _allocated_capital(
    *,
    expression: BacktestTradeExpression | None,
    entry_price: float | None,
    trade_pnl: TradePnlOutcome | None,
) -> float:
    if expression == BacktestTradeExpression.CALL_OPTION and trade_pnl is not None:
        return trade_pnl.entry_price * 100 if trade_pnl.entry_price is not None else 0.0
    return float(entry_price) if isinstance(entry_price, int | float) else 0.0


def _setup_warnings(
    underlying: object,
    trade_pnl: TradePnlOutcome | None,
) -> list[str]:
    warnings: list[str] = []
    if (
        hasattr(underlying, "outcome")
        and underlying.outcome == BacktestOutcome.NOT_EVALUABLE
    ):
        warnings.append("underlying_not_evaluable")
    if trade_pnl is not None and trade_pnl.outcome == BacktestOutcome.NOT_EVALUABLE:
        warnings.append(trade_pnl.not_evaluable_reason or "trade_not_evaluable")
    return warnings


def _price_index(
    prices: list[HistoricalPricePoint],
) -> dict[tuple[str, date], HistoricalPricePoint]:
    return {(price.ticker, price.trading_date): price for price in prices}


def _option_quote_index(
    quotes: list[HistoricalOptionQuote],
) -> dict[tuple[str, BacktestTradeExpression, date, date], HistoricalOptionQuote]:
    return {
        (
            quote.ticker,
            quote.option_type,
            quote.expiration_date,
            quote.trading_date,
        ): quote
        for quote in quotes
    }


def _close_price(
    price_index: Mapping[tuple[str, date], HistoricalPricePoint],
    ticker: str,
    trading_date: date,
) -> float | None:
    point = price_index.get((ticker, trading_date))
    return point.close if point is not None else None
