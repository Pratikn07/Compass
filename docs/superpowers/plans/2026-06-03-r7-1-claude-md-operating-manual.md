# R7.1 CLAUDE.md Operating Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a root `CLAUDE.md` operating manual that is the human-readable mirror of the code-owned rails, and add a drift-guard test that proves the prose never contradicts the risk values enforced in `prescient.risk`.

**Architecture:** `CLAUDE.md` is prose governance — it states what `prescient` is, the hard rules, the standing risk caps, and the "never trade live without rails" rule. It enforces nothing by itself; enforcement stays in `prescient.risk` and `prescient.broker`. Because the PRD requires prose to never exceed or drift from code (R7.1.6, R7.1.8), the verification is a real test that parses `CLAUDE.md` and asserts the quoted values equal the current code defaults.

**Tech Stack:** Markdown, Python, Pydantic v2, pytest, uv, ruff.

---

## Source PRD

Use this PRD as source of truth:

`/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/07-config-r7-1-claude-md-operating-manual-prd.md`

## File Structure

Create:

- `/Users/pratik.nandoskar/Documents/working/prescient/CLAUDE.md`
  - The operating manual. Sections: System Statement, Hard Rules, Risk Caps, Live-Trading Rule, Session Contract, Maintenance Rule.
- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r7_1_claude_md_operating_manual.py`
  - Drift-guard + structure tests covering R7.1 acceptance criteria.

Modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/README.md`
  - Add a short R7.1 note pointing to `CLAUDE.md` as the operating manual.

Do not modify:

- `prescient.risk` (source of truth for caps — `CLAUDE.md` mirrors it, never the reverse)
- `prescient.signal`
- `prescient.analyst`
- `prescient.broker`
- `prescient.runtime`
- `prescient.scheduler`
- `prescient.events`
- `ExecutionMode`, the risk gatekeeper, or any enforcement code

## Authoritative Values To Mirror

`CLAUDE.md` must quote these exact current values. The drift-guard test reads them from code, not from a hardcoded copy.

| Concept | Code source | Current value |
|---|---|---|
| Execution mode enum + default | `ExecutionMode` in `src/prescient/risk/models.py:95` | `paper` / `propose_only` / `live`; default `propose_only` |
| Absolute per-trade loss ceiling | `AccountSizePolicySettings.absolute_trade_loss_pct_ceiling` | `0.03` (3%) |
| Tier default per-trade loss cap | `AccountSizePolicySettings.tier_default_trade_loss_pct` | `0.01` (1%) |
| Supported account tier | `AccountSizePolicySettings.supported_min_equity` / `supported_max_equity` | `$10,000` – `$25,000` |
| Daily realized loss stop | `DailyHaltSettings.max_daily_realized_loss_pct` | `0.05` (5%) |
| Max losing trades per day | `DailyHaltSettings.max_losing_trades_per_day` | `2` |

## Tasks

### Task 1: Add R7.1 Tests (failing first)

- [ ] Create `tests/test_r7_1_claude_md_operating_manual.py`.
- [ ] Add a helper that resolves the repo-root `CLAUDE.md` path and reads its text.
- [ ] **Existence/format** — assert `CLAUDE.md` exists at repo root and is non-empty Markdown.
- [ ] **Structure (R7.1.2–R7.1.7)** — assert presence of required section headings: System Statement, Hard Rules, Risk Caps, Live-Trading Rule, Session Contract, Maintenance Rule.
- [ ] **Hard Rules content (R7.1.3)** — assert the Hard Rules section names: never enable/assume `live`, never place/size/approve a trade, never override the risk gatekeeper, never increase a risk cap, Claude is advisory only.
- [ ] **Drift guard (R7.1.4, R7.1.6, R7.1.8)** — import `AccountSizePolicySettings`, `DailyHaltSettings`, and `ExecutionMode` from `prescient.risk`; assert the document text contains the current values (`3%`/`0.03`, `1%`/`0.01`, `$10,000`, `$25,000`, `5%`/`0.05`, `2`, and the three mode names with `propose_only` as default). The test must read these from the models, so changing a code default without updating `CLAUDE.md` fails the test.
- [ ] **Live-trading rule (R7.1.5)** — assert the doc states `propose_only` is the default/only agent-assumable mode and that `live` requires human authorization plus rails passing.
- [ ] **Source-of-truth statement (R7.1.4)** — assert the doc explicitly names `prescient.risk` (or `risk/models.py`) as authoritative for the values.
- [ ] Run:
  ```bash
  uv run pytest tests/test_r7_1_claude_md_operating_manual.py -q
  ```
  Expected: fail (no `CLAUDE.md` yet).

### Task 2: Write CLAUDE.md

- [ ] Create `/CLAUDE.md` with these sections, in order:
  - **System Statement** (R7.1.2): what `prescient` is; the "code owns the rails; Claude advises within them" principle; the `signal → analyst → risk → broker` boundary.
  - **Hard Rules** (R7.1.3): the never-do list, each rule referencing its enforcing layer (e.g. "sizing/approval — pure code, R3.x"; "advisory only — R2.5"; "override blocked — R3.1.5 `claude_override_attempted`").
  - **Risk Caps** (R7.1.4): the table of standing caps with current values, plus the explicit line "values mirrored from `src/prescient/risk/models.py`; if prose and code disagree, code wins."
  - **Live-Trading Rule** (R7.1.5): `propose_only` default; `paper` for validation; `live` requires rails passing + deliberate human authorization; phased path `propose_only → paper → live`; agent must never set/request/infer `live`.
  - **Session Contract** (R7.1.7): rules apply to every action including refactors, tests, and quick fixes.
  - **Maintenance Rule** (R7.1.8): a cap/mode change in code must update `CLAUDE.md` in the same change; drift is a defect.
- [ ] Ensure no rule grants a capability looser than code enforces (R7.1.6).
- [ ] Run:
  ```bash
  uv run pytest tests/test_r7_1_claude_md_operating_manual.py -q
  ```
  Expected: pass.

### Task 3: Documentation And Verification

- [ ] Update `README.md` with a short R7.1 note: `CLAUDE.md` is the operating manual / prose mirror of the risk rails; code remains the source of truth.
- [ ] Run:
  ```bash
  uv run pytest -q
  uv run ruff check .
  ```
  Expected: full suite green and Ruff clean.

## Acceptance Checklist

- [ ] `CLAUDE.md` exists at repo root, valid self-contained Markdown.
- [ ] System Statement, Hard Rules, Risk Caps, Live-Trading Rule, Session Contract, and Maintenance Rule sections all present.
- [ ] Hard Rules reference their enforcing code layers.
- [ ] Quoted values (`propose_only` default, 3% ceiling, 1% tier default, $10k–$25k, 5% daily stop, 2 losing trades/day) match `src/prescient/risk/models.py`.
- [ ] Doc names `prescient.risk` as source of truth.
- [ ] Live-trading rule states never `live` without rails + human authorization.
- [ ] Drift-guard test reads values from code and fails if `CLAUDE.md` falls out of sync.
- [ ] Full pytest suite green; Ruff clean.

## Assumptions

- `CLAUDE.md` is prose governance only; it adds no enforcement code (R7.1 Out of Scope).
- `prescient.risk` is the single source of truth for all quoted values; `CLAUDE.md` mirrors it and is corrected on drift, never the reverse.
- The drift-guard test asserts the *current* code values appear in the prose; it does not re-implement risk logic.
- The account tier mirrored is $10k–$25k per R3.8 / current code (`supported_max_equity = 25_000`), not the original $2–5k brainstorm figure. Reconciling that figure is a separate R3.8 concern, out of scope here.
- No change to `ExecutionMode`, the risk gatekeeper, broker gating, `config/themes.yaml`, or any MCP layer.
- The manual stays concise enough to read in full at session start.
