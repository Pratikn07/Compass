# Technical PRD: 1. Core Strategy Requirements

## Purpose

Define the technical design for the `prescient` core strategy engine. This engine turns configured themes, earnings calendar data, peer earnings results, market data, and news signals into deterministic strategy decisions.

The strategy engine must be independent from broker execution. It must never place orders, size positions, or access live account funds.

## Scope

In scope:

- Theme-based strategy universe loading.
- Upcoming earnings candidate detection.
- Peer earnings result collection and scoring.
- Target tradability filters.
- Candidate brief generation.
- Rejection reason generation.
- Unit-testable deterministic strategy behavior.

Out of scope:

- Broker execution.
- Position sizing.
- Account-level risk enforcement.
- Claude prompt implementation.
- Alerts and notifications.
- Database journaling.
- Backtest engine.
- UI or dashboard.

## Module Ownership

The core strategy implementation belongs under:

```text
src/prescient/signal/
```

Recommended files:

```text
src/prescient/signal/
├── candidate.py
├── peer_readthrough.py
├── technical_filter.py
└── models.py
```

Supporting config and data models may live under:

```text
config/
├── settings.yaml
└── themes.yaml

src/prescient/data/models.py
```

## Architecture

The strategy engine sits between the read-only data adapters and the Claude analyst.

```text
data adapters
  -> core strategy engine
    -> candidate brief
      -> Claude analyst
```

The strategy engine must be deterministic:

- Same input produces same output.
- No LLM calls inside `signal/`.
- No broker calls inside `signal/`.
- No network calls inside pure scoring functions.
- No hidden state that changes scoring behavior across runs.

## Configuration Contract

### settings.yaml

Required strategy settings:

```yaml
strategy:
  earnings_window_days: 1
  peer_result_window_days: 21
  min_reported_peers: 3
  min_positive_peer_ratio: 0.67
  min_average_peer_score: 2.0
  positive_price_reaction_pct: 3.0
  negative_price_reaction_pct: -3.0
  min_avg_daily_volume: 1000000
  max_target_runup_pct: 15.0
  allow_stock_fallback: true
```

These values must be loaded from config, validated, and passed into the strategy engine explicitly.

### themes.yaml

Theme structure:

```yaml
themes:
  AI_STORAGE:
    tickers: [NTAP, PSTG, WDC, STX, NTNX]
    drivers:
      - AI data center demand
      - enterprise storage growth
      - cloud infrastructure spend
```

Validation requirements:

- `themes` must be present.
- Each theme must have at least 2 tickers.
- Theme names must be unique.
- Tickers must be uppercase strings.
- Duplicate tickers inside a theme should be rejected.
- A ticker may appear in multiple themes, but each candidate decision must preserve the theme that generated it.

## Data Contracts

The strategy layer should operate on typed models, preferably Pydantic models.

### ThemeConfig

```python
class ThemeConfig(BaseModel):
    name: str
    tickers: list[str]
    drivers: list[str] = []
```

### EarningsEvent

```python
class EarningsEvent(BaseModel):
    ticker: str
    earnings_date: date
    report_time: Literal["BMO", "AMC", "UNKNOWN"]
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
```

### PeerResult

```python
class PeerResult(BaseModel):
    ticker: str
    earnings_event: EarningsEvent
    price_reaction_pct: float | None = None
    guidance_signal: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    theme_driver_signal: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    source_urls: list[str] = []
```

### PeerScore

```python
class PeerScore(BaseModel):
    ticker: str
    score: int
    positive_factors: list[str]
    negative_factors: list[str]
    missing_factors: list[str]
```

### CandidateBrief

```python
class CandidateBrief(BaseModel):
    target: str
    theme: str
    earnings_date: date
    report_time: Literal["BMO", "AMC", "UNKNOWN"]
    direction: Literal["bullish"]
    peer_signal_score: float
    positive_peer_ratio: float
    reported_peers: list[str]
    peer_scores: list[PeerScore]
    supporting_evidence: list[str]
    contradictions: list[str]
    recommended_expression: Literal["CALL_OPTION", "STOCK", "NONE"]
    strategy_status: Literal["candidate_ready_for_analyst"]
```

### StrategyDecision

```python
class StrategyDecision(BaseModel):
    status: Literal["no_trade", "candidate_ready_for_analyst", "rejected"]
    candidate: CandidateBrief | None = None
    rejection_reasons: list[RejectionReason] = []
```

### RejectionReason

Use an enum:

```python
class RejectionReason(StrEnum):
    THEME_NOT_CONFIGURED = "theme_not_configured"
    EARNINGS_DATE_UNCERTAIN = "earnings_date_uncertain"
    INSUFFICIENT_PEERS_REPORTED = "insufficient_peers_reported"
    PEER_SIGNAL_TOO_WEAK = "peer_signal_too_weak"
    CONFLICTING_NEWS = "conflicting_news"
    TARGET_ALREADY_OVEREXTENDED = "target_already_overextended"
    TARGET_TOO_ILLIQUID = "target_too_illiquid"
    OPTIONS_TOO_ILLIQUID = "options_too_illiquid"
    MISSING_DATA = "missing_data"
```

## Core Pipeline

### 1. Find Upcoming Targets

Input:

- Theme config.
- Earnings calendar events.
- Current date.
- `earnings_window_days`.

Output:

- Target tickers reporting within the configured window.

Rules:

- Include only tickers from configured themes.
- Reject events with unknown or missing earnings date.
- Preserve theme context for each target.

### 2. Collect Reported Peers

Input:

- Target ticker.
- Theme config.
- Earnings event history.
- `peer_result_window_days`.

Output:

- Peer results for companies in the same theme that already reported recently.

Rules:

- Exclude the target ticker from peers.
- Include only peers with completed earnings events.
- Include only events inside the configured recency window.
- If fewer than `min_reported_peers` are available, reject the target.

### 3. Score Peer Results

Function:

```python
score_peer_result(peer: PeerResult, settings: StrategySettings) -> PeerScore
```

Scoring rules:

- `+1` if EPS actual is greater than EPS estimate.
- `-1` if EPS actual is less than EPS estimate.
- Missing EPS data adds no points and records `eps_missing`.
- `+1` if revenue actual is greater than revenue estimate.
- `-1` if revenue actual is less than revenue estimate.
- Missing revenue data adds no points and records `revenue_missing`.
- `+1` for positive guidance.
- `-1` for negative guidance.
- `+1` if price reaction is greater than or equal to `positive_price_reaction_pct`.
- `-1` if price reaction is less than or equal to `negative_price_reaction_pct`.
- `+1` if theme driver signal is positive.
- `-1` if theme driver signal is negative.

Guidance and theme driver signals must come from structured upstream data. The strategy layer must not parse free-form transcripts or ask Claude to interpret them.

### 4. Aggregate Peer Signal

Function:

```python
aggregate_peer_scores(scores: list[PeerScore]) -> PeerSignal
```

The aggregate must calculate:

- `average_peer_score`
- `positive_peer_count`
- `negative_peer_count`
- `positive_peer_ratio`
- `missing_data_count`

Pass conditions:

- `positive_peer_ratio >= min_positive_peer_ratio`
- `average_peer_score >= min_average_peer_score`

If either condition fails, reject with `PEER_SIGNAL_TOO_WEAK`.

### 5. Run Target Filters

Target filters run after peer signal passes.

Required checks:

- Average daily volume must be greater than or equal to `min_avg_daily_volume`.
- Target run-up before earnings must be less than or equal to `max_target_runup_pct`.
- Conflicting news flag must be false.
- Options liquidity must pass if the preferred expression is `CALL_OPTION`.

If options fail but `allow_stock_fallback` is true, set `recommended_expression` to `STOCK`.

If options fail and stock fallback is false, reject with `OPTIONS_TOO_ILLIQUID`.

### 6. Build Candidate Brief

The candidate brief must include:

- Target ticker.
- Theme.
- Earnings date and report time.
- Direction.
- Aggregate peer score.
- Positive peer ratio.
- Reported peer list.
- Peer score details.
- Supporting evidence.
- Contradictions.
- Recommended expression.
- Strategy status.

The brief must be serializable to JSON and safe to pass to the Claude analyst.

## Determinism Requirements

The following functions must be pure and unit-testable:

- `score_peer_result`
- `aggregate_peer_scores`
- `find_reported_peers`
- `evaluate_peer_readthrough`
- `build_candidate_brief`

They must not:

- Read environment variables.
- Call HTTP APIs.
- Call Claude.
- Call broker adapters.
- Write to disk.
- Depend on system time unless `current_date` is passed explicitly.

## Error Handling

Missing data must never be guessed.

Rules:

- Missing earnings date rejects with `EARNINGS_DATE_UNCERTAIN`.
- Missing peer earnings data can either reduce confidence or reject with `MISSING_DATA`, depending on whether enough complete peers remain.
- Missing EPS or revenue values for one peer should not automatically reject the entire candidate.
- Missing data should be recorded in `missing_factors`.
- If every peer has incomplete financial results, reject with `MISSING_DATA`.

## Observability Contract

The strategy engine must return enough structured information for the journal layer to log decisions later.

Every strategy result must include:

- Decision status.
- Candidate ticker.
- Theme.
- Rejection reasons, if any.
- Peer scores used.
- Thresholds used.
- Data completeness notes.

The strategy engine itself should not write journal records in MVP. It returns structured output to the caller.

## Testing Requirements

Tests belong under:

```text
tests/test_peer_readthrough.py
tests/test_strategy_candidate.py
tests/test_target_filters.py
```

Required test cases:

- Creates bullish candidate when 4 of 5 peers beat and guide up.
- Rejects when fewer than `min_reported_peers` have reported.
- Rejects when positive peer ratio is below threshold.
- Rejects when average peer score is below threshold.
- Records missing EPS and revenue without hallucinating values.
- Rejects when all peer result data is missing.
- Rejects target outside configured theme.
- Rejects target with uncertain earnings date.
- Falls back to `STOCK` when options fail and stock fallback is enabled.
- Rejects with `OPTIONS_TOO_ILLIQUID` when options fail and stock fallback is disabled.
- Produces identical output for identical input.

## Acceptance Criteria

This technical PRD is complete when implementation can satisfy:

- Core strategy can run with mocked data only.
- No broker credentials are required.
- No Claude API key is required.
- Strategy output is JSON-serializable.
- All scoring and rejection logic is covered by unit tests.
- Strategy code can be reused by both future backtest and live scheduler flows.

## Implementation Order Recommendation

1. Define Pydantic models and enums.
2. Define strategy settings and theme validation.
3. Implement peer scoring.
4. Implement peer aggregation.
5. Implement candidate detection.
6. Implement target filters.
7. Implement candidate brief construction.
8. Add unit tests for every rejection path.

The first implementation milestone should stop before Claude, brokers, or live data adapters.
