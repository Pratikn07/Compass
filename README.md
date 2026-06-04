# prescient

Backend engine for deterministic earnings read-through research.

This project starts with Part 1.1 of the core strategy PRD: building a pure,
testable strategy thesis layer. This layer does not call Claude, fetch live data,
place trades, or connect to brokers.

## Tech Stack

Prescient's consolidated R10 stack is Python >=3.11 with `uv` as the canonical
dependency manager and command runner. Use `uv run pytest -q` for the full test
suite and `uv run ruff check .` for lint verification.

SQLite is the default local durable store for MVP journals, scheduler run state,
caches, and repeatable fixtures. Supabase and JSONL remain supported behind
storage interfaces when explicitly configured.

Claude Code is the preferred agentic development and operator-assist surface,
but importable application packages must not require Claude Code to execute.
MCP connectors belong at workflow edges such as docs, ticketing, reporting, and
operator notifications; connector output must be normalized before entering
decision code.

Scheduled jobs should be cron-compatible, bounded, and propose-only by default.
Cron wrappers must not run infinite polling loops or bypass risk gates, broker
source-of-truth checks, kill switches, daily halts, or preflight checks.

## Operating manual (CLAUDE.md)

[`CLAUDE.md`](CLAUDE.md) is the operating manual — the prose mirror of the
code-owned rails (R7.1). It states the hard rules, the standing risk caps, and the
"never trade live without rails" rule that every agent session must obey.
`prescient.risk` remains the authoritative source of truth for all risk values; a
drift-guard test fails the build if `CLAUDE.md` falls out of sync with the code.

## Deterministic signal engine

The code-owned deterministic signal engine lives under `prescient.signal`. Its
public hot-path entrypoint is `evaluate_core_strategy`, which turns structured
snapshots of the strategy universe, earnings calendar, peer results, target
market data, and options chains into JSON-serializable `StrategyDecision`
objects.

This path is Claude-free: it does not call the analyst layer, broker adapters,
runtime orchestration, or live data providers. Scheduled runs and future
event-driven triggers should reuse `evaluate_core_strategy` instead of
duplicating peer scoring, target filters, rejection handling, or candidate brief
construction.

Technical indicators such as RSI, MACD, and VWAP enter the strategy as compact
provider/server-precomputed snapshots. Raw OHLCV or candle history is not sent to
Claude for indicator calculation.

## Risk gate

The code-owned risk layer lives under `prescient.risk`. R3.2 exposes
`evaluate_trade_risk`, a deterministic per-trade maximum-loss cap gate that
defaults to 3% of account equity and returns structured rejection reasons or
review flags. Claude, sub-agents, broker adapters, runtime orchestration, and
live account state do not size trades or override this risk decision.

R3.4 exposes `evaluate_daily_halt`, a deterministic daily realized-loss and loss
count halt. It blocks new risk after the configured daily loss stop or losing
trade count is reached while still allowing exits, reductions, cancellations,
and risk-reducing actions.

R3.8 exposes `evaluate_account_size_policy`, a deterministic account-size policy
gate for the supported `$10k-$25k` tier. The tier recommendation is a 1%
per-trade risk cap, while 3% remains the absolute review-required ceiling.
Broker-specific day-trade, PDT, and intraday-margin enforcement is deferred to
future broker/account adapters.

## Learning loop

The cold-path learning layer lives under `prescient.learning`. R6.2 exposes
`run_morning_learning_loop`, which reads prior JSONL journal records, classifies
realized outcomes, and returns bounded parameter proposals for review or safe
overlay generation. It does not run inside the hot path, call brokers, fetch
market data, or let LLM output change deterministic settings.

## Backtest replay and analytics

The cold-path backtest and analytics layers live under `prescient.backtest` and
`prescient.analytics`. R9.1 exposes `run_peer_readthrough_backtest`, which
replays historical peer-read-through fixtures through the deterministic signal
engine and measures target follow-through plus stock or explicit quote-based
call-option P&L. R9.3 adds win rate, max drawdown, Sharpe ratio, total return,
and matched target buy-and-hold comparison. These layers do not fetch live data,
place orders, call brokers, change live settings, or approximate option outcomes
from underlying moves.

## Supported strategy types

The MVP has one executable strategy type:

- `bullish_earnings_readthrough` — active. Builds a deterministic bullish thesis
  when enough same-theme peers have already reported positive earnings or
  theme-driver evidence.

The PRD also names future strategy types, but they are intentionally planned
metadata only and are rejected if requested:

- `bearish_earnings_readthrough`
- `post_earnings_drift`
- `analyst_upgrade_momentum`
- `sector_basket`
- `mean_reversion`
