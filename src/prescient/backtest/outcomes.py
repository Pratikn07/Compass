from __future__ import annotations

from datetime import date

from prescient.backtest.models import (
    BacktestOutcome,
    BacktestTradeExpression,
    HistoricalOptionQuote,
    TradePnlOutcome,
    UnderlyingFollowThroughOutcome,
)


def calculate_underlying_followthrough(
    *,
    ticker: str,
    entry_price: float | None,
    exit_price: float | None,
    evaluation_start: date,
    evaluation_end: date,
    positive_threshold_pct: float = 1.0,
    negative_threshold_pct: float = -1.0,
    expected_direction: str = "bullish",
) -> UnderlyingFollowThroughOutcome:
    if not _is_positive_number(entry_price) or not _is_positive_number(exit_price):
        return UnderlyingFollowThroughOutcome(
            ticker=ticker,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            entry_reference_price=entry_price,
            exit_reference_price=exit_price,
            return_pct=None,
            expected_direction=expected_direction,
            outcome=BacktestOutcome.NOT_EVALUABLE,
            reason="missing_or_invalid_underlying_price",
        )

    raw_return_pct = ((float(exit_price) - float(entry_price)) / float(entry_price)) * 100
    return_pct = raw_return_pct if expected_direction != "bearish" else -raw_return_pct

    if return_pct >= positive_threshold_pct:
        outcome = BacktestOutcome.WIN
    elif return_pct <= negative_threshold_pct:
        outcome = BacktestOutcome.LOSS
    else:
        outcome = BacktestOutcome.FLAT

    return UnderlyingFollowThroughOutcome(
        ticker=ticker,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        entry_reference_price=float(entry_price),
        exit_reference_price=float(exit_price),
        return_pct=return_pct,
        expected_direction=expected_direction,
        outcome=outcome,
    )


def calculate_stock_trade_pnl(
    *,
    ticker: str,
    expression: BacktestTradeExpression | str,
    quantity: float,
    entry_price: float | None,
    exit_price: float | None,
    fees: float = 0.0,
) -> TradePnlOutcome:
    normalized_expression = BacktestTradeExpression.normalize(expression)
    if (
        normalized_expression != BacktestTradeExpression.STOCK
        or quantity <= 0
        or not _is_positive_number(entry_price)
        or not _is_positive_number(exit_price)
    ):
        return _not_evaluable_trade(
            ticker=ticker,
            expression=normalized_expression,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            fees=fees,
            reason="missing_or_invalid_stock_trade_input",
        )

    gross_pnl = (float(exit_price) - float(entry_price)) * quantity
    net_pnl = gross_pnl - fees
    risk = float(entry_price) * quantity
    return TradePnlOutcome(
        ticker=ticker,
        expression=normalized_expression,
        quantity=quantity,
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        gross_pnl=gross_pnl,
        fees=fees,
        net_pnl=net_pnl,
        return_on_risk_pct=(net_pnl / risk) * 100 if risk > 0 else None,
        outcome=_outcome_from_pnl(net_pnl),
    )


def calculate_option_trade_pnl(
    *,
    ticker: str,
    quantity: float,
    entry_quote: HistoricalOptionQuote | None,
    exit_quote: HistoricalOptionQuote | None,
    fees: float = 0.0,
) -> TradePnlOutcome:
    entry_mid = _option_midpoint(entry_quote)
    exit_mid = _option_midpoint(exit_quote)
    if quantity <= 0 or entry_mid is None or exit_mid is None:
        return _not_evaluable_trade(
            ticker=ticker,
            expression=BacktestTradeExpression.CALL_OPTION,
            quantity=quantity,
            entry_price=entry_mid,
            exit_price=exit_mid,
            fees=fees,
            reason="missing_or_invalid_option_quote",
        )

    gross_pnl = (exit_mid - entry_mid) * quantity * 100
    net_pnl = gross_pnl - fees
    risk = entry_mid * quantity * 100
    return TradePnlOutcome(
        ticker=ticker,
        expression=BacktestTradeExpression.CALL_OPTION,
        quantity=quantity,
        entry_price=entry_mid,
        exit_price=exit_mid,
        gross_pnl=gross_pnl,
        fees=fees,
        net_pnl=net_pnl,
        return_on_risk_pct=(net_pnl / risk) * 100 if risk > 0 else None,
        outcome=_outcome_from_pnl(net_pnl),
    )


def _option_midpoint(quote: HistoricalOptionQuote | None) -> float | None:
    if (
        quote is None
        or not _is_positive_number(quote.bid)
        or not _is_positive_number(quote.ask)
        or quote.bid is None
        or quote.ask is None
        or quote.ask < quote.bid
    ):
        return None
    return (float(quote.bid) + float(quote.ask)) / 2


def _not_evaluable_trade(
    *,
    ticker: str,
    expression: BacktestTradeExpression,
    quantity: float,
    entry_price: float | None,
    exit_price: float | None,
    fees: float,
    reason: str,
) -> TradePnlOutcome:
    return TradePnlOutcome(
        ticker=ticker,
        expression=expression,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        gross_pnl=None,
        fees=fees,
        net_pnl=None,
        return_on_risk_pct=None,
        outcome=BacktestOutcome.NOT_EVALUABLE,
        reason=reason,
        not_evaluable_reason=reason,
    )


def _outcome_from_pnl(net_pnl: float) -> BacktestOutcome:
    if net_pnl > 0:
        return BacktestOutcome.WIN
    if net_pnl < 0:
        return BacktestOutcome.LOSS
    return BacktestOutcome.FLAT


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_positive_number(value: object) -> bool:
    return _is_number(value) and float(value) > 0
