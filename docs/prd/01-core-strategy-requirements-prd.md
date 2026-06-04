# PRD: 1. Core Strategy Requirements

## Objective

Build the core strategy engine for `prescient`: an earnings read-through system that identifies companies reporting soon, checks whether related peers have already reported strong or weak results, and produces a structured trade thesis.

The strategy should answer:

> Based on recent peer earnings, guidance, sector momentum, news, and price behavior, is this upcoming earnings report a high-quality setup worth analyzing?

This section covers only the strategy logic. Broker execution, account risk limits, journaling, and alerts are handled in later PRD sections.

## 1.1 Strategy Thesis

The system will focus on peer read-through earnings plays.

A peer read-through happens when multiple companies in the same theme or sector report earnings before a target company, and their results suggest a likely positive or negative signal for the target.

Example:

- Theme: `AI_STORAGE`
- Peers already reported: `NTAP`, `PSTG`, `WDC`, `STX`
- Shared driver: enterprise AI storage demand
- If peers beat revenue or EPS and guide up, the target company reporting tomorrow may have a bullish setup.

The app must convert this idea into deterministic, testable logic.

## 1.2 Supported Strategy Types

MVP supports one primary strategy:

**Bullish earnings read-through**

The system looks for companies reporting tomorrow or soon where:

- Multiple peers in the same theme already reported.
- Peer results were positive.
- Peer guidance or management commentary supports the same demand driver.
- The target stock has acceptable liquidity and price behavior.
- News or sentiment does not contradict the thesis.

Future strategy types may include:

- Bearish read-throughs.
- Post-earnings drift.
- Analyst upgrade momentum.
- Sector basket trades.
- Mean reversion.

These are out of scope for the first version.

## 1.3 Strategy Universe

The strategy must operate on themed groups defined by the user, not the entire market.

Example themes:

```yaml
AI_STORAGE:
  tickers: [NTAP, PSTG, WDC, STX, NTNX]
  drivers:
    - AI data center demand
    - enterprise storage growth
    - cloud infrastructure spend

SEMICONDUCTORS:
  tickers: [NVDA, AMD, AVGO, MRVL, MU]
  drivers:
    - AI accelerator demand
    - data center capex
    - memory pricing
```

Requirements:

- Each theme must have a name.
- Each theme must include target tickers.
- Each theme may include key demand drivers.
- The system must only generate candidates from configured themes.
- The system must not auto-trade random stocks outside the configured universe.

## 1.4 Earnings Candidate Detection

The system must scan the earnings calendar and find target companies that report within a configured window.

Default window:

```yaml
earnings_window_days: 1
```

Candidate requirements:

- Target company reports within the configured window.
- Target belongs to at least one user-defined theme.
- At least `N` peers in the same theme have already reported this earnings cycle.
- Peer reports must be recent enough to matter.

Default thresholds:

```yaml
min_reported_peers: 3
peer_result_window_days: 21
```

The system must reject a candidate if there are not enough recent peer results.

## 1.5 Peer Result Scoring

Each reported peer must be scored using deterministic rules.

Inputs:

- EPS estimate vs actual.
- Revenue estimate vs actual.
- Guidance, if available.
- Stock reaction after earnings.
- Management commentary or news summary.
- Sector or theme relevance.

Default scoring:

```text
+1 EPS beat
+1 revenue beat
+1 positive guidance
+1 stock reaction positive after report
+1 commentary confirms theme driver

-1 EPS miss
-1 revenue miss
-1 negative guidance
-1 stock reaction negative after report
-1 commentary contradicts theme driver
```

The system must calculate:

- Individual peer score.
- Average peer score.
- Count of positive peers.
- Count of negative peers.
- Confidence level of the peer signal.

A candidate should pass the peer read-through filter only if:

```yaml
min_positive_peer_ratio: 0.67
min_average_peer_score: 2.0
```

## 1.6 Target Company Filters

Before Claude analyzes a candidate, deterministic filters must check whether the target is tradable.

Required filters:

- Target has upcoming earnings.
- Target is in a configured theme.
- Enough peers have reported.
- Target has sufficient average volume.
- Target is not extremely illiquid.
- Target does not have conflicting major news.
- Target has no recent event that invalidates peer comparison, such as merger, accounting issue, or regulatory shock.

For options strategies, the system must also check:

- Options chain exists.
- Bid/ask spread is acceptable.
- Open interest is acceptable.
- Expiration exists near the earnings event.

If options are not available or fail liquidity checks, the strategy may fall back to a stock expression if enabled.

## 1.7 Strategy Output

The core strategy must produce a structured candidate brief.

Example output:

```json
{
  "target": "PSTG",
  "theme": "AI_STORAGE",
  "earnings_date": "2026-06-03",
  "report_time": "AMC",
  "direction": "bullish",
  "peer_signal_score": 3.4,
  "positive_peer_ratio": 0.8,
  "reported_peers": ["NTAP", "WDC", "STX", "NTNX"],
  "main_thesis": "Recent peer earnings suggest strong AI storage demand.",
  "supporting_evidence": [
    "3 of 4 peers beat revenue estimates",
    "2 peers raised guidance",
    "Peer commentary mentioned AI-driven storage growth"
  ],
  "contradictions": [
    "Target stock already rallied 12% into earnings"
  ],
  "recommended_expression": "CALL_OPTION_OR_STOCK",
  "strategy_status": "candidate_ready_for_analyst"
}
```

The core strategy must not place trades directly.

It only produces:

- `NO_TRADE`
- `CANDIDATE_READY_FOR_ANALYST`
- `REJECTED_WITH_REASON`

## 1.8 Claude's Role in Strategy

Claude may be used only after deterministic filters pass.

Claude's job:

- Read the candidate brief.
- Summarize the thesis.
- Identify missing context.
- Check for contradictions.
- Produce go/no-go reasoning.
- Suggest a trade expression.

Claude must not:

- Override risk limits.
- Invent missing financial data.
- Choose position size.
- Place trades directly from raw reasoning.
- Trade on a single headline.
- Trade a ticker outside the configured themes.

Claude output must be structured and machine-readable.

## 1.9 Rejection Requirements

Every rejected candidate must include a clear reason.

Example reasons:

- `INSUFFICIENT_PEERS_REPORTED`
- `PEER_SIGNAL_TOO_WEAK`
- `CONFLICTING_NEWS`
- `TARGET_ALREADY_OVEREXTENDED`
- `OPTIONS_TOO_ILLIQUID`
- `EARNINGS_DATE_UNCERTAIN`
- `MISSING_DATA`
- `THEME_NOT_CONFIGURED`

Rejected candidates must still be logged for later review.

## 1.10 Success Criteria

The core strategy is successful when:

- It can scan configured themes and identify upcoming earnings candidates.
- It correctly links targets to reported peers.
- It scores peer read-through signals deterministically.
- It rejects weak setups with explicit reasons.
- It creates structured candidate briefs for strong setups.
- The same input data produces the same strategy result every time.
- The strategy can be tested without any broker connection or real money.

MVP acceptance tests:

- Given 5 AI-storage peers where 4 beat and guided up, the system creates a bullish candidate.
- Given only 1 reported peer, the system rejects the candidate.
- Given mixed peer results, the system rejects or lowers confidence.
- Given missing earnings data, the system does not hallucinate and rejects with `MISSING_DATA`.
- Given illiquid options, the system does not recommend an options trade.
