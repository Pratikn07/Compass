from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from prescient.backtest import (
    BacktestDataset,
    BacktestOutcome,
    BacktestRunRequest,
    BacktestTradeExpression,
    HistoricalOptionQuote,
    HistoricalPricePoint,
    run_peer_readthrough_backtest,
)
from prescient.backtest.outcomes import (
    calculate_option_trade_pnl,
    calculate_stock_trade_pnl,
    calculate_underlying_followthrough,
)
from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)


def test_r9_1_prd_exists_and_names_backtest_scope() -> None:
    prd = Path("docs/prd/09-backtest-r9-1-peer-readthrough-edge-prd.md")

    assert prd.exists()
    contents = prd.read_text(encoding="utf-8")
    assert "R9.1 Backtest the Peer-Read-Through Edge" in contents
    assert "option quotes are missing" in contents
    assert "No live Finnhub, broker, Supabase, or market-data calls." in contents


def test_backtest_request_defaults_are_bounded_and_bullish() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-fixture",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        max_events=50,
    )

    assert request.strategy_type == "bullish_earnings_readthrough"
    assert request.evaluation_horizon_days == 1
    assert request.include_rejected_candidates is True
    assert request.include_trade_pnl is True
    assert request.max_events == 50


def test_fixture_models_normalize_tickers_and_serialize() -> None:
    price = HistoricalPricePoint(
        ticker="ntnx",
        trading_date=date(2025, 6, 2),
        close=50.0,
    )
    quote = HistoricalOptionQuote(
        ticker="ntnx",
        option_type="call",
        expiration_date=date(2025, 6, 20),
        trading_date=date(2025, 6, 2),
        bid=1.0,
        ask=1.2,
    )
    dataset = BacktestDataset(prices=[price], option_quotes=[quote])

    assert dataset.prices[0].ticker == "NTNX"
    assert dataset.option_quotes[0].option_type == BacktestTradeExpression.CALL_OPTION
    assert dataset.model_dump(mode="json")["prices"][0]["trading_date"] == "2025-06-02"


def test_underlying_followthrough_wins_loses_flats_and_missing_data() -> None:
    assert (
        calculate_underlying_followthrough(
            ticker="NTNX",
            entry_price=50.0,
            exit_price=52.0,
            evaluation_start=date(2025, 6, 2),
            evaluation_end=date(2025, 6, 3),
        ).outcome
        == BacktestOutcome.WIN
    )

    flat = calculate_underlying_followthrough(
        ticker="NTNX",
        entry_price=50.0,
        exit_price=49.75,
        evaluation_start=date(2025, 6, 2),
        evaluation_end=date(2025, 6, 3),
    )
    assert flat.outcome == BacktestOutcome.FLAT
    assert flat.return_pct == pytest.approx(-0.5)

    assert (
        calculate_underlying_followthrough(
            ticker="NTNX",
            entry_price=50.0,
            exit_price=48.0,
            evaluation_start=date(2025, 6, 2),
            evaluation_end=date(2025, 6, 3),
        ).outcome
        == BacktestOutcome.LOSS
    )

    missing = calculate_underlying_followthrough(
        ticker="NTNX",
        entry_price=None,
        exit_price=52.0,
        evaluation_start=date(2025, 6, 2),
        evaluation_end=date(2025, 6, 3),
    )
    assert missing.outcome == BacktestOutcome.NOT_EVALUABLE
    assert missing.return_pct is None


def test_stock_trade_pnl_uses_entry_exit_quantity_and_fees() -> None:
    outcome = calculate_stock_trade_pnl(
        ticker="NTNX",
        expression=BacktestTradeExpression.STOCK,
        quantity=10,
        entry_price=50.0,
        exit_price=52.0,
        fees=1.0,
    )

    assert outcome.expression == BacktestTradeExpression.STOCK
    assert outcome.gross_pnl == pytest.approx(20.0)
    assert outcome.net_pnl == pytest.approx(19.0)
    assert outcome.return_on_risk_pct == pytest.approx(3.8)
    assert outcome.outcome == BacktestOutcome.WIN


def test_option_trade_pnl_requires_explicit_entry_and_exit_quotes() -> None:
    entry_quote = HistoricalOptionQuote(
        ticker="NTNX",
        option_type="call",
        expiration_date=date(2025, 6, 20),
        trading_date=date(2025, 6, 2),
        bid=1.0,
        ask=1.2,
    )
    exit_quote = HistoricalOptionQuote(
        ticker="NTNX",
        option_type="CALL_OPTION",
        expiration_date=date(2025, 6, 20),
        trading_date=date(2025, 6, 3),
        bid=1.7,
        ask=1.9,
    )

    outcome = calculate_option_trade_pnl(
        ticker="ntnx",
        quantity=1,
        entry_quote=entry_quote,
        exit_quote=exit_quote,
    )

    assert outcome.expression == BacktestTradeExpression.CALL_OPTION
    assert outcome.entry_price == pytest.approx(1.1)
    assert outcome.exit_price == pytest.approx(1.8)
    assert outcome.gross_pnl == pytest.approx(70.0)
    assert outcome.net_pnl == pytest.approx(70.0)
    assert outcome.outcome == BacktestOutcome.WIN

    missing = calculate_option_trade_pnl(
        ticker="NTNX",
        quantity=1,
        entry_quote=entry_quote,
        exit_quote=None,
    )
    assert missing.outcome == BacktestOutcome.NOT_EVALUABLE
    assert missing.net_pnl is None


def test_backtest_runner_replays_candidate_and_summarizes_outcomes() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-candidate",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
        max_events=10,
    )
    dataset = _candidate_dataset()

    result = run_peer_readthrough_backtest(request, dataset)

    assert result.request == request
    assert len(result.setups) == 1
    setup = result.setups[0]
    assert setup.target == "NTNX"
    assert setup.theme == "AI_STORAGE"
    assert setup.strategy_status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert setup.recommended_expression == BacktestTradeExpression.CALL_OPTION
    assert setup.underlying_outcome is not None
    assert setup.underlying_outcome.outcome == BacktestOutcome.WIN
    assert setup.underlying_outcome.return_pct == pytest.approx(4.0)
    assert setup.trade_pnl is not None
    assert setup.trade_pnl.outcome == BacktestOutcome.WIN
    assert setup.trade_pnl.gross_pnl == pytest.approx(70.0)
    assert result.summary.total_setups == 1
    assert result.summary.candidate_ready_count == 1
    assert result.summary.underlying_win_count == 1
    assert result.summary.trade_win_count == 1
    assert result.summary.by_theme == {"AI_STORAGE": 1}
    assert result.summary.by_ticker == {"NTNX": 1}
    assert result.summary.by_expression == {"CALL_OPTION": 1}


def test_backtest_runner_keeps_rejected_candidates_when_requested() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-rejected",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
        include_rejected_candidates=True,
    )
    dataset = _candidate_dataset(peer_tickers=["NTAP"])

    result = run_peer_readthrough_backtest(request, dataset)

    assert len(result.setups) == 1
    setup = result.setups[0]
    assert setup.strategy_status == StrategyStatus.REJECTED_WITH_REASON
    assert setup.rejection_reasons == ["insufficient_peers_reported"]
    assert setup.trade_pnl is None
    assert setup.underlying_outcome is not None
    assert result.summary.rejected_count == 1


def test_backtest_runner_marks_option_trade_not_evaluable_without_quotes() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-missing-option-quotes",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
    )
    dataset = _candidate_dataset(option_quotes=[])

    result = run_peer_readthrough_backtest(request, dataset)

    setup = result.setups[0]
    assert setup.strategy_status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert setup.recommended_expression == BacktestTradeExpression.CALL_OPTION
    assert setup.trade_pnl is not None
    assert setup.trade_pnl.outcome == BacktestOutcome.NOT_EVALUABLE
    assert setup.trade_pnl.net_pnl is None
    assert result.summary.trade_not_evaluable_count == 1


def test_backtest_runner_filters_window_and_respects_max_events() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-bounds",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
        max_events=1,
    )
    dataset = _candidate_dataset(
        upcoming_events=[
            _target_event("NTNX", date(2025, 6, 3)),
            _target_event("DELL", date(2025, 6, 5)),
            _target_event("NTNX", date(2025, 7, 3)),
        ],
    )

    result = run_peer_readthrough_backtest(request, dataset)

    assert result.summary.total_setups == 1
    assert result.setups[0].target == "NTNX"


def test_backtest_result_serialization_excludes_sensitive_terms() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-serialization",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
    )

    serialized = json.dumps(
        run_peer_readthrough_backtest(request, _candidate_dataset()).model_dump(
            mode="json"
        )
    )

    forbidden_terms = [
        "authorization",
        "bearer",
        "secret",
        "token",
        "prompt",
        "broker_account",
        "account_id",
        "raw_payload",
    ]
    assert not any(term in serialized.lower() for term in forbidden_terms)


def _candidate_dataset(
    *,
    peer_tickers: list[str] | None = None,
    upcoming_events: list[EarningsCalendarEvent] | None = None,
    option_quotes: list[HistoricalOptionQuote] | None = None,
) -> BacktestDataset:
    target_date = date(2025, 6, 3)
    option_expiration = date(2025, 6, 13)
    peers = peer_tickers or ["NTAP", "PSTG", "WDC"]
    return BacktestDataset(
        universe=_universe(),
        upcoming_events=upcoming_events or [_target_event("NTNX", target_date)],
        peer_results=[_positive_peer(ticker) for ticker in peers],
        target_market_data={
            "NTNX": TargetMarketData(
                ticker="NTNX",
                avg_daily_volume=2_000_000,
                pre_earnings_runup_pct=4.0,
            ),
            "DELL": TargetMarketData(
                ticker="DELL",
                avg_daily_volume=4_000_000,
                pre_earnings_runup_pct=2.0,
            ),
        },
        options_chains={
            "NTNX": [
                OptionContractSnapshot(
                    ticker="NTNX",
                    option_type="CALL",
                    expiration_date=option_expiration,
                    bid=1.0,
                    ask=1.15,
                    open_interest=250,
                )
            ],
            "DELL": [
                OptionContractSnapshot(
                    ticker="DELL",
                    option_type="CALL",
                    expiration_date=date(2025, 6, 13),
                    bid=2.0,
                    ask=2.2,
                    open_interest=400,
                )
            ],
        },
        prices=[
            HistoricalPricePoint(
                ticker="NTNX",
                trading_date=target_date,
                close=50.0,
            ),
            HistoricalPricePoint(
                ticker="NTNX",
                trading_date=date(2025, 6, 4),
                close=52.0,
            ),
            HistoricalPricePoint(
                ticker="DELL",
                trading_date=date(2025, 6, 5),
                close=100.0,
            ),
            HistoricalPricePoint(
                ticker="DELL",
                trading_date=date(2025, 6, 6),
                close=101.0,
            ),
        ],
        option_quotes=_default_option_quotes(target_date, option_expiration)
        if option_quotes is None
        else option_quotes,
    )


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG", "WDC", "DELL"],
                drivers=["AI data center storage demand"],
            )
        ]
    )


def _target_event(ticker: str, earnings_date: date) -> EarningsCalendarEvent:
    return EarningsCalendarEvent(
        ticker=ticker,
        earnings_date=earnings_date,
        report_time="AMC",
    )


def _positive_peer(ticker: str) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2025, 5, 29),
            report_time="AMC",
            eps_estimate=1.0,
            eps_actual=1.2,
            revenue_estimate=1_000.0,
            revenue_actual=1_100.0,
        ),
        price_reaction_pct=4.0,
        guidance_signal="positive",
        theme_driver_signal="positive",
    )


def _default_option_quotes(
    entry_date: date,
    expiration_date: date,
) -> list[HistoricalOptionQuote]:
    return [
        HistoricalOptionQuote(
            ticker="NTNX",
            option_type="call",
            expiration_date=expiration_date,
            trading_date=entry_date,
            bid=1.0,
            ask=1.2,
        ),
        HistoricalOptionQuote(
            ticker="NTNX",
            option_type="call",
            expiration_date=expiration_date,
            trading_date=date(2025, 6, 4),
            bid=1.7,
            ask=1.9,
        ),
    ]
