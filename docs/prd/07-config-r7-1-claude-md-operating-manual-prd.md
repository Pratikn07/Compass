# PRD: R7.1 CLAUDE.md Operating Manual

## Ownership

Owner: Ours

Source: Gemini (cross-checked by ChatGPT) — both identified a spec-grade `CLAUDE.md` as the single most important lesson from real autonomous-trading builds.

Drafting support: Claude

## Objective

Create `CLAUDE.md` at the repository root: a strict, spec-grade operating manual that governs how any AI agent (Claude, Claude Code, or a sub-agent) is permitted to reason about and act on the `prescient` system.

`CLAUDE.md` is the written constitution of the system. It is the human-authored, version-controlled statement of the hard rules every agent session must obey: what the system is, what an agent may never do, the standing risk caps, and the absolute rule that the system must never trade live money without the code-owned rails in place.

It is documentation that constrains behavior. It does not replace the deterministic enforcement in `prescient.risk` or `prescient.broker` — it states the same boundaries in prose so that an agent reading the repo cannot claim ignorance, and so a human operator has one authoritative page describing how the system is allowed to behave.

## Background

`prescient` is an autonomous earnings read-through trading system built on the principle that **code decides the rails; Claude decides only within them**. The dangerous boundary is already enforced in code:

- `prescient.signal` — deterministic candidate detection (no LLM).
- `prescient.analyst` — Claude as advisory judgment only (R2.5).
- `prescient.risk` — pure-code risk gatekeeper Claude cannot override (R3.1–R3.8).
- `prescient.broker` — execution adapters gated by `ExecutionMode` (R5.1–R5.6).

The execution mode is defined in code today:

```python
# src/prescient/risk/models.py
class ExecutionMode(StrEnum):
    PAPER = "paper"
    PROPOSE_ONLY = "propose_only"   # safe default
    LIVE = "live"
```

and there is a visible startup banner (`print_execution_mode_banner` in `src/prescient/broker/execution_guard.py`) that loudly announces `LIVE` / `PAPER` / `PROPOSE-ONLY`.

What is missing is the **prose layer**. There is no `CLAUDE.md`. An agent opening this repository has no single authoritative file telling it the rules of engagement before it touches anything. Both external reviews (Gemini, ChatGPT) flagged this as the core lesson from real builds: write the strict spec *first*, in a file the agent reads every session, so it operates inside stated boundaries rather than improvising.

`CLAUDE.md` closes that gap. It is the human-readable mirror of the code-owned rails.

```text
CLAUDE.md (prose rules, this PRD)
  mirrors -> prescient.risk        (code-owned caps, R3.x)
  mirrors -> prescient.analyst     (Claude advisory only, R2.5)
  mirrors -> prescient.broker      (ExecutionMode gating, R5.x)
```

## Definitions

### Operating Manual

`CLAUDE.md` is the operating manual: a single Markdown file at the repository root, loaded automatically by Claude Code at the start of every session, stating the non-negotiable rules for working in this repository.

### Hard Rule

A hard rule is a constraint that no agent may violate, rationalize around, or treat as advisory. Hard rules in `CLAUDE.md` must mirror a boundary that is also enforced in code. `CLAUDE.md` never grants a capability the code does not already permit.

### Risk Cap Reference

A risk cap reference is a prose statement of a standing risk limit (per-trade loss cap, daily loss stop, account tier, max losing trades per day) whose authoritative value lives in `prescient.risk`. `CLAUDE.md` states the current value for human readability and explicitly names code as the source of truth.

### Live-Trading Rule

The live-trading rule is the single most important hard rule: the system must never place real-money (`ExecutionMode.LIVE`) trades unless the code-owned risk rails are present and passing, and a human has deliberately authorized live mode. An agent must never enable, request, or assume `LIVE` mode on its own.

## Requirement

The repository must contain a root `CLAUDE.md` operating manual that:

- States what `prescient` is and the one-line design principle (code owns the rails; Claude advises within them).
- Enumerates the hard rules every agent session must obey.
- States the standing risk caps and names `prescient.risk` as their source of truth.
- States the live-trading rule prominently and unambiguously.
- Mirrors — and never contradicts — the boundaries already enforced in `prescient.risk`, `prescient.analyst`, and `prescient.broker`.
- Is human-authored, version-controlled, and concise enough to be read in full at the start of a session.

## User Value

This protects the user from the failure mode where an agent, lacking stated boundaries, improvises beyond intent — the exact risk FINRA flagged for agentic trading.

It provides:

- One authoritative page describing how the system is allowed to behave.
- A written rulebook every agent reads before acting, removing "I didn't know" as a failure path.
- A prose mirror of the code rails, so prose and code reinforce each other.
- A deliberate, human-gated path to live trading.
- An onboarding document for any human operator.

## Functional Requirements

### R7.1.1 File Location And Format

`CLAUDE.md` must exist at the repository root (`/CLAUDE.md`).

It must be valid Markdown, readable as plain text, and self-contained (no external fetch required to understand the rules).

### R7.1.2 System Statement

`CLAUDE.md` must open with a concise statement of:

- What `prescient` is: an autonomous earnings read-through options trading system.
- The core design principle: **deterministic code owns the rails; Claude is advisory and decides only within them.**
- The layered architecture boundary: `signal` (code) → `analyst` (Claude advisory) → `risk` (code gate) → `broker` (gated execution).

### R7.1.3 Hard Rules Section

`CLAUDE.md` must contain a clearly marked **Hard Rules** section. At minimum it must state that an agent must never:

- Enable, request, or assume `ExecutionMode.LIVE`. Live mode is a human-only decision.
- Place, size, approve, or authorize a trade. Sizing and approval are pure code (R3.x).
- Override, weaken, or bypass the risk gatekeeper or its rejection reasons (R3.1.5).
- Increase any risk cap, or edit risk values in code to "make a trade work."
- Treat its own analysis as permission to execute. Claude output is advisory metadata only (R2.5).
- Commit secrets, credentials, or `.env` contents.
- Run the system live without the rails present and passing.

Each hard rule must reference the code layer that enforces it, so the prose and code stay traceable.

### R7.1.4 Risk Caps Section

`CLAUDE.md` must state the standing risk caps for human readability, and must explicitly name `prescient.risk` as the authoritative source of truth. At minimum:

- Per-trade max loss cap (currently `0.03` / 3% absolute ceiling; tier default `0.01`).
- Supported account tier (currently $10k–$25k, R3.8).
- Daily realized loss stop (currently `0.05` / 5%).
- Max losing trades per day (currently `2`).

The section must state: *these values are mirrored from code; if prose and code disagree, code wins, and the prose must be corrected.*

### R7.1.5 Live-Trading Rule (Never Trade Live Without Rails)

`CLAUDE.md` must contain a prominent, unambiguous rule stating:

- The default and only agent-assumable mode is `PROPOSE_ONLY`.
- `PAPER` is for validation on virtual money.
- `LIVE` (real money) requires: (a) the code-owned risk rails present and passing, and (b) explicit, deliberate human authorization.
- An agent must never set, request, infer, or default to `LIVE`.
- The phased path is: `propose_only` → `paper` → (human-authorized) `live`.

### R7.1.6 Prose Must Not Exceed Code

`CLAUDE.md` must never describe a capability, permission, or cap looser than what code enforces. The prose is a subset of (or equal to) the code-owned boundaries. If a rule appears in `CLAUDE.md`, an equal-or-stricter boundary must exist in code.

### R7.1.7 Agent Session Contract

`CLAUDE.md` must state the session contract: an agent working in this repository acknowledges these rules apply to every action it takes, including refactors, tests, and "quick fixes." The rules are not suspended for convenience.

### R7.1.8 Maintenance Rule

`CLAUDE.md` must include a short maintenance note: when a risk cap or execution rule changes in code, `CLAUDE.md` must be updated in the same change. Drift between prose and code is a defect.

## Non-Functional Requirements

### Safety

The manual's default posture is restrictive: anything not explicitly permitted, and not enforced as safe by code, is disallowed.

### Truthfulness

Every rule in `CLAUDE.md` must correspond to a real, currently-enforced code boundary. No aspirational rules describing enforcement that does not exist.

### Readability

The manual must be concise and skimmable — readable in full at session start without fatigue. Hard rules and the live-trading rule must be visually prominent.

### Maintainability

`CLAUDE.md` references code as the source of truth for values, minimizing duplication drift. It states *which* file owns each number rather than re-deriving it.

## Out Of Scope

R7.1 does not implement:

- A central `config/settings.yaml` or config loader (separate R7 follow-up).
- Any change to `ExecutionMode`, the risk gatekeeper, or broker gating logic.
- A live-mode confirmation tripwire mechanism in code (separate follow-up; `CLAUDE.md` states the rule, code enforces it elsewhere).
- Expansion of `config/themes.yaml` (R7.2).
- Progressive MCP tool discovery (R7.3).
- Per-environment or per-operator overrides.

`CLAUDE.md` is prose governance only. It states boundaries; it does not add new enforcement code.

## Acceptance Criteria

- `CLAUDE.md` exists at the repository root and is valid, self-contained Markdown.
- It states what `prescient` is and the "code owns the rails; Claude advises" principle (R7.1.2).
- It contains a clearly marked Hard Rules section, each rule referencing its enforcing code layer (R7.1.3).
- It states the standing risk caps and names `prescient.risk` as source of truth (R7.1.4).
- It contains a prominent live-trading rule: never `LIVE` without rails present/passing and human authorization (R7.1.5).
- Every stated rule corresponds to an equal-or-stricter boundary already enforced in code (R7.1.6).
- It states the per-session contract (R7.1.7) and the prose/code maintenance rule (R7.1.8).
- No rule in `CLAUDE.md` grants a capability or cap looser than code enforces.
- The values quoted (3% ceiling, 1% tier default, $10k–$25k tier, 5% daily stop, 2 losing trades/day, `propose_only` default) match the current values in `src/prescient/risk/models.py`.

## Current Implementation Notes

The repository currently has **no** `CLAUDE.md`.

The code boundaries `CLAUDE.md` will mirror already exist:

- `ExecutionMode` (`PAPER` / `PROPOSE_ONLY` / `LIVE`) in `src/prescient/risk/models.py`, default `PROPOSE_ONLY`.
- `print_execution_mode_banner` in `src/prescient/broker/execution_guard.py` (loud LIVE/PAPER/PROPOSE-ONLY banner).
- Risk caps in `src/prescient/risk/models.py`: `absolute_trade_loss_pct_ceiling = 0.03`, `tier_default_trade_loss_pct = 0.01`, `supported_max_equity = 25_000`, `max_daily_realized_loss_pct = 0.05`, `max_losing_trades_per_day = 2`.
- `claude_override_attempted` rejection reason already enforced by the risk gatekeeper (R3.1.5).

R7.1 only adds the prose mirror. It must quote these exact values and name these files.

## Product FAQ

> Does `CLAUDE.md` enforce anything by itself?

No. Enforcement is in code (`prescient.risk`, `prescient.broker`). `CLAUDE.md` is the prose statement of those same rules so an agent operates knowingly inside them.

> If `CLAUDE.md` and the code disagree on a cap, which wins?

Code always wins. `CLAUDE.md` must then be corrected — drift is a defect (R7.1.8).

> Can an agent edit `CLAUDE.md` to relax a rule?

An agent must not loosen a hard rule. `CLAUDE.md` rules are a subset of code-enforced boundaries (R7.1.6); relaxing prose does not relax code, and attempting to do so to enable a trade violates the Hard Rules section itself.

> Can an agent switch the system to live mode if it's confident in a trade?

No. `LIVE` is a human-only decision requiring rails present and passing (R7.1.5). Confidence is not authorization.

> Why duplicate risk values in prose if code is the source of truth?

For human readability and for the agent's session-start context. The duplication is explicitly labeled as a mirror, with code named as authoritative, and kept in sync by the maintenance rule (R7.1.8).

> Is this the same as the config settings file?

No. A central `config/settings.yaml` and loader is a separate R7 follow-up. R7.1 is governance prose only.
