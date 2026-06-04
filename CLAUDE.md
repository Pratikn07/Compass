# CLAUDE.md — prescient Operating Manual

This file is the **operating manual** for any AI agent (Claude, Claude Code, or a
sub-agent) working in this repository. Claude Code loads it at the start of every
session. Read it in full before taking any action.

It is **prose governance**. It enforces nothing by itself — enforcement lives in
`prescient.risk` and `prescient.broker`. This file states those same boundaries in
plain language so an agent operates knowingly inside them and a human has one
authoritative page describing how the system is allowed to behave.

---

## System Statement

`prescient` is an autonomous **earnings read-through options trading system**. It
watches earnings across themed sectors, detects peer "read-through" setups (when
several peers in a theme have already beaten and guided up, the next name to report
becomes a candidate), asks Claude for advisory judgment, enforces hard risk limits in
code, and places trades through a swappable broker adapter.

**Core design principle: deterministic code owns the rails; Claude is advisory and
decides only within them.**

The architecture is a one-directional boundary:

```
signal (code)  ->  analyst (Claude, advisory)  ->  risk (code gate)  ->  broker (gated execution)
```

- **`prescient.signal`** — deterministic candidate detection. No LLM.
- **`prescient.analyst`** — Claude judgment, **advisory only** (R2.5).
- **`prescient.risk`** — pure-code risk gatekeeper Claude cannot override (R3.x).
- **`prescient.broker`** — execution adapters, gated by `ExecutionMode` (R5.x).

Claude advises. Code decides the rails. Code pulls the trigger.

---

## Hard Rules

These are non-negotiable. An agent must **never** rationalize around them, including
during refactors, tests, or "quick fixes." Each rule mirrors a boundary enforced in
code.

1. **Never enable, request, assume, or default to `live` (real-money) mode.** Live
   mode is a human-only decision. *(Enforced by `ExecutionMode`; default is
   `propose_only`.)*
2. **Never place, size, approve, or authorize a trade.** Position sizing and approval
   are pure code. *(Enforced by `prescient.risk`, R3.x.)*
3. **Never override, weaken, or bypass the risk gatekeeper or its rejection reasons.**
   Any attempt by Claude/analyst output to size, approve, or execute is blocked with
   `claude_override_attempted`. *(Enforced by R3.1.5.)*
4. **Never increase a risk cap, and never edit risk values in code to "make a trade
   work."** The caps below are ceilings, not suggestions.
5. **Never treat your own analysis as permission to execute.** Claude output is
   **advisory** metadata only. *(R2.5.)*
6. **Never commit secrets, credentials, or `.env` contents.**
7. **Never run the system live without the rails present and passing.**

If a rule here and the code ever disagree, **the code wins** and this file is the
thing that gets corrected.

---

## Risk Caps

These are the standing risk limits. The values are **mirrored from
`src/prescient/risk/models.py`** (`prescient.risk`), which is the authoritative
**source of truth**. If this prose and the code disagree, the code wins and this
section must be corrected (see Maintenance Rule).

| Limit | Current value | Code owner |
|---|---|---|
| Absolute per-trade loss ceiling | **3%** of account equity | `AccountSizePolicySettings.absolute_trade_loss_pct_ceiling = 0.03` |
| Tier default per-trade loss cap | **1%** of account equity | `AccountSizePolicySettings.tier_default_trade_loss_pct = 0.01` |
| Supported account tier | **$10,000 – $25,000** | `AccountSizePolicySettings.supported_min_equity` / `supported_max_equity` |
| Daily realized loss stop | **5%** of account equity | `DailyHaltSettings.max_daily_realized_loss_pct = 0.05` |
| Max losing trades per day | **2** | `DailyHaltSettings.max_losing_trades_per_day = 2` |

No trade may exceed the per-trade ceiling. Trading halts for the day when the daily
loss stop or the max-losing-trades limit is hit. An agent must never propose a
configuration that loosens any of these.

---

## Live-Trading Rule

**Never trade live without the rails.** This is the most important rule in this file.

There are three execution modes (`ExecutionMode` in `prescient.risk`):

- **`propose_only`** — the **default** and the only mode an agent may assume. No orders
  are placed; the system only proposes.
- **`paper`** — validation on a virtual sandbox. No real money.
- **`live`** — real money. Allowed **only** when **both** are true:
  1. the code-owned risk rails are present and **passing**, and
  2. a human has **deliberately authorized** live mode.

An agent must **never** set, request, infer, or default to `live`. Confidence in a
trade is **not** authorization.

The phased path to real money is, in order:

```
propose_only  ->  paper  ->  (human-authorized)  live
```

---

## Session Contract

By working in this repository, an agent acknowledges that every rule in this file
applies to **every action it takes** — including refactors, test changes, dependency
bumps, and "quick fixes." The rules are not suspended for convenience, speed, or a
seemingly-good trade. When in doubt, stay in `propose_only` and ask a human.

---

## Maintenance Rule

This file is a **mirror** of code-owned boundaries. When a risk cap, execution rule,
or account tier changes in `src/prescient/risk/models.py`, **this file must be updated
in the same change.** Drift between this prose and the code is a **defect**.

A drift-guard test (`tests/test_r7_1_claude_md_operating_manual.py`) reads the
authoritative values from `prescient.risk` and fails if this file falls out of sync —
so keeping it current is enforced, not optional.
