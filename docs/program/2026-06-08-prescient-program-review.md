# Prescient — Program Review & Learnings Log

**Author:** Program lead (acting PM)
**Date:** 2026-06-08
**Audience:** The owner/operator (you), and any future engineer or agent who picks this up cold.
**Status:** Living document. This is the narrative record — what we set out to do, what we
actually did, what we learned, and what the evidence says as of today.

> **One-line summary:** We set out to predict earnings moves and buy options to profit. We
> built an honest, disprove-first backtest harness instead of a trading bot — and the harness
> has so far told us, on your own data and for $0, that **all three retail earnings-options
> approaches we tested do not beat a coin flip after honest costs.** That is the product
> working exactly as designed: it is an idea-killer that protects your money before you risk it.

---

## 1. Why this project exists (the real goal)

The goal was never "build a dashboard" or "ship a trading system." Stripped to its core, the
goal you stated was:

> *"I want to make money — not on index funds, but on options on companies, because I have
> seen them go up and down and people profiting strongly."*

Specifically: **predict whether a company's stock will spike (up or down) around its earnings,
ahead of the report, so we can buy calls or puts and profit.**

And — this is the most important sentence in the whole program — you set the governing rule
yourself:

> *"Yes — evidence overrides the feeling."*

That single decision is what turned this from a gambling app into a research program. It means:
**if a strategy can't beat a coin flip on historical data after IV crush and costs, it does not
get traded with real money, regardless of how good it feels.** Everything below is built to
honor that deal.

You also repeatedly, explicitly asked to be challenged:

> *"You also don't have to get influenced by me. I don't know, so I am relying on you. I want
> you to be critical of it so that our app idea is benefiting."*

So this document is critical where it needs to be. That is the job.

---

## 2. The original idea, and where it was wrong

### 2.1 The starting thesis: peer read-through

The original app (the `docs/prd/` set — ~40 PRDs) was built around a specific, intuitive thesis:

> If 4 AI-storage companies report strong earnings, the 5th one has a high chance (you floated
> "80%") of also doing well — so we put a directional options bet on the 5th before it reports.

This is the **peer read-through** idea. Mechanically: a candidate "fires" when ≥3 same-theme
peers report within the trailing 21 days *before* the target reports, and we read their results
through to the target.

### 2.2 The criticisms we surfaced (and you accepted)

Acting as the critic you asked for, we found real holes in the raw thesis:

1. **The "80%" was invented.** There was no evidence behind it. Correlation in *fundamentals*
   (peers in a sector tend to do well together) is real, but it does not cleanly translate to a
   *tradable, directional, pre-earnings* edge.

2. **Direction ≠ profit.** Even if you correctly guess the company does "well," the option can
   still lose money. Why? **IV crush.** Options are priced with an implied move baked in. If the
   stock moves *less* than that implied move — even in the right direction — your option loses
   value the moment earnings are out. You have to beat the *implied* move, not just the
   direction.

3. **You were unknowingly blending two different bets.** "Predict the spike" and "the option
   will pay" are not the same trade. We had to separate them.

You accepted all three. That reframing — **"beat the implied move," not "guess the
direction"** — became the spine of everything we built next.

### 2.3 The pivot you proposed later (the IV-ramp insight)

Partway through, you made a genuinely sharp observation:

> *"Options are higher when the earnings date is next day. So why can't we predict if a company
> is going to spike about a few days before — so the options haven't gone up yet?"*

This was actually two ideas tangled together, and separating them mattered:

- **Idea A — directional prediction, moved earlier.** Harder, not easier. There is *less*
  information 7 days out, not more. Moving the prediction earlier doesn't make you smarter; it
  makes you blinder.
- **Idea B — the volatility/IV-ramp play.** Buy options cheap ~1 week out, **sell them the day
  before the report** (never hold through), harvesting the rise in implied volatility as fear
  builds — and dodging IV crush entirely because you're already out. This is **direction-free.**

Idea B is the better-grounded one, and it became its own tested strategy (see §6.3). The honest
warning attached to it: it's the most famous "free lunch" in earnings options, which means
market makers have probably already priced the ramp into the entry premium. If so, the
double bid/ask spread plus theta eat it. We tested it rather than assumed it.

---

## 3. The strategic decision: build an idea-killer, not a bot

The single most consequential call in this whole program was **what to build first.**

The tempting path was to build the trading system (signal → analyst → risk → broker → dashboard)
and "see if it makes money live." We rejected that. Live trading an unproven thesis with real
money is exactly what loses small accounts.

Instead we inverted it: **build the thing that tries to kill the idea before it can cost you
money.** A backtest harness whose explicit job is to *disprove* the edge. If the edge survives a
deliberately hostile, honest test, *then* — and only then — does it earn the right to paper
trading, and much later, real money.

This is why the system is structured as a **disprove-first measurement harness**, and why it is
**propose-only forever** at the code level (it physically cannot place, size, authorize, or
recommend a trade — that's enforced in `prescient.risk` and mirrored in `CLAUDE.md`).

The phased path to real money — and we are at the very first gate — is:

```
backtest (disprove)  ->  paper  ->  (human-authorized)  live
```

We have not left the first box.

---

## 4. How we decomposed the work

A "whole app rethink" is too big for one spec, so we decomposed it into sub-projects, each with
its own spec → plan → implementation cycle:

| # | Sub-project | Status | What it does |
|---|---|---|---|
| 1 | **Edge measurement backtest harness** | ✅ Done | Scores predictions vs the options-implied move, with a brutal survival gate |
| 2 | **Live-data assembly** | ✅ Done | Assembles real earnings + bars + peer signals into the harness, $0 free tier |
| 3 | **Historical-options reader** | ✅ Done | Fetches as-of ATM CALL+PUT straddles for past earnings so the implied move is computable |
| 4 | **Prediction / blending engine** | ⏸ Deferred | Only worth building if a strategy survives |
| 5 | **Dashboard** | ⏸ Deferred | Only worth building if there's a real edge to display |

Plus two **strategy experiments** layered on top of the finished harness:

| Experiment | Status | Verdict |
|---|---|---|
| **Short-vol defined-risk** (sell straddle, hold through) | ✅ Built & run | `survived=False` |
| **Pre-earnings vol-ramp** (buy early, sell before report) | ✅ Built & run 2026-06-10 | `survived=False` |

The discipline: **sub-projects 4 and 5 are deliberately not built.** Building a prediction engine
and a dashboard for an edge that doesn't exist would be the classic small-account mistake —
polishing the cockpit of a plane that can't fly. We hold them until evidence justifies them.

---

## 5. What we actually built (the engineering record)

Branch: `feat/edge-backtest-harness` — **86 commits, 110 test files, lint clean, suite green.**

### 5.1 The harness core (`src/prescient/edge/`)

The scoring engine is deliberately frozen and pure (no I/O, no LLM, fully unit-tested):

- **`models.py`** — frozen Pydantic v2 types: `EventContext`, `Prediction`, `EventScore`,
  `OptionQuote`, etc.
- **`implied_move.py`** — computes the options-implied move from the ATM straddle (call + put).
  This is the bar every strategy must beat.
- **`realized_move.py`** — the *only* allowed look-forward: what the stock actually did
  post-report. Isolated on purpose so no-lookahead violations are obvious.
- **`option_pnl.py`** — the honest P&L models, including an IV-crush model and a loss floor at
  −100% (you can't lose more than the premium). Now holds three P&L models: buy-through,
  capped-short-straddle, and (spec'd) vol-ramp.
- **`strategy.py`** — the strategies and baselines: `ReactionAwarePeerStrategy` (the real
  thesis), plus `CoinFlipStrategy` and `AlwaysUpStrategy` as the bars to beat. Coin-flip is
  deterministic (seeded by hash) so runs are reproducible.
- **`scorer.py`** — scores one event: direction correct? beat the implied move? option P&L?
- **`scorecard.py`** — aggregates across events; reports **median *and* mean** return (mean
  alone hides tail losses), plus a `SampleSizeVerdict` (TOO_FEW etc.) so we never over-read a
  thin sample.
- **`runner.py`** — the **survival gate**, the heart of the idea-killer. A strategy only
  `survives` if it: has both baselines present, beats both by a real margin, has a *positive*
  average return, and is not flagged TOO_FEW. We hardened this three times after finding it
  could flatter a weak strategy.

### 5.2 The data layer (`src/prescient/edge/data/`)

Assembles real, point-in-time inputs from **free** sources only:

- **`earnings_history.py`** — `AlphaVantageEarningsHistoryAdapter`. The earnings spine: ~30
  years of report dates + EPS estimate/actual/surprise, one call per ticker, free.
- **`bars_loader.py`** — batched Alpaca daily bars (2016→now).
- **`option_loader.py`** — per-event historical ATM straddle fetch.
- **`peer_signals.py`** — the pure, no-lookahead peer builder. A peer only counts if its report
  landed *strictly before* the target's as-of date and within the trailing 21 days. This is the
  central correctness guard of the whole data layer.
- **`assembler.py`** — orchestrates everything into `(EventContexts, PointInTimeDataset)` with a
  coverage/error summary.
- **`cache.py`** — on-disk fetch-once JSON cache (sha256-keyed, no secrets) so re-runs are free.

### 5.3 The historical-options reader (sub-project 3)

- **`alpaca_market.py` → `get_historical_atm_straddle(...)`** — pure logic, injected reader,
  picks the ATM strike nearest the underlying, pairs the same-strike PUT, prices each leg at bar
  close. Returns `[]` on any miss (skip-not-guess).
- **`live_data/alpaca_readers.py` → `build_historical_option_reader(...)`** — the only
  SDK-bound piece; lists expired contracts and pulls their daily bars.

Verified live: MU's 2024-06-25 straddle priced at ~12.8% implied move. The data exists on the
free tier.

### 5.4 The runnable command

- **`scripts/run_edge_backtest.py`** — wires Alpha Vantage earnings + Alpaca bars + the
  historical straddle reader + assembler + runner, and prints a side-by-side scorecard
  (strategy / evaluable / direction% / beat% / avg return% / median return% / survived) with a
  coverage summary. `--limit N` runs a cheap smoke test before the full run.

---

## 6. The evidence so far (what the harness has told us)

This is the part that matters. Three approaches tested; **all three failed the survival gate.**

### 6.1 Buy-the-straddle, hold through earnings (the original peer thesis)

- **Directional accuracy:** ~30–33% (worse than a coin flip).
- **The killer:** IV crush ate the rare correct calls. Returns were **outlier-driven** — a
  couple of lucky events carried the mean while the median bled.
- **A real, documented finding fell out of it:** in ~70% of events (28/40), the stock moved
  **less** than the options-implied move. The market was pricing in *more* drama than actually
  happened.
- **Verdict:** `survived=False`.

### 6.2 Sell volatility, defined-risk, hold through earnings (short-vol)

The 28/40 finding above pointed at the opposite trade: if the stock usually moves less than
implied, maybe *selling* the straddle wins. So we built the only version a small account could
actually run: a **defined-risk (capped-loss), unhedged, sell-and-hold** short straddle.

- **Result:** **−79.5% average, −100% median.** Killed by fat tails — the occasional huge move
  blew through the cap and wiped out many quarters of small wins.
- **Important honesty caveat (in the spec):** this tests the *retail, unhedged* version. Funds
  capture the volatility risk premium via continuous delta-hedging across hundreds of names
  (LTCM-style), which a small account cannot do. So "does not survive" means *"this version you
  could actually run loses,"* not *"the premium doesn't exist."*
- **Verdict:** `survived=False`.

### 6.3 Buy early, sell before the report (the vol-ramp play — Idea B)

Both tests above share one trait: they **entered near the report and held through the event** —
exactly where IV crush lives and where direction must be guessed. Your IV-ramp insight describes
something genuinely untested: **buy the ATM straddle ~5 trading days out, sell it the day before
earnings, never hold through.** It can't eat IV crush (it's closed before the event) and it
never predicts direction (you own both legs).

- **Status:** ✅ Implemented and run 2026-06-10 (spec:
  `docs/superpowers/specs/2026-06-07-pre-earnings-vol-ramp-design.md`, plan:
  `docs/superpowers/plans/2026-06-10-pre-earnings-vol-ramp.md`). Strike-locked honesty:
  the ATM straddle is chosen at entry and the SAME contracts are priced at exit (we never
  model a position we didn't hold). Entry = 5 trading days before the report; exit = the
  day before; the P&L crosses the bid/ask spread twice (5% per side ⇒ ~10% round trip).
- **Result (2024-06-10 → 2026-06-10, 25-name universe):** **67 evaluable events
  (`suggestive` sample): average return −7.0%, median −12.5%. `survived=False`** — it did
  not even beat zero, let alone zero + the 2-point margin.
- **The economically beautiful detail:** the median loss (−12.5%) is almost exactly the
  modeled round-trip spread cost (~10%) plus a little theta. In other words, the
  pre-earnings vol ramp **exists but is fully priced in** — the typical trade harvested
  the ramp and handed it straight to the market maker as the spread. The honest prior was
  correct.
- **Survival bar for this one is different (and documented):** since it takes no event risk and
  no directional risk, the correct thing to beat is **doing nothing** (a zero return), not the
  drift-inflated coin-flip/always-up baselines (which rode the bull market by holding through).
  This is *additive* — every existing strategy keeps the strict beat-the-baselines bar, and a
  regression test pins the prior verdicts.

### 6.4 The honest read across all three

> For a small account, buying earnings options (any direction), selling earnings options
> (defined-risk), and timing the vol ramp (buy early, sell before the report) have **all
> three** failed to produce an edge that survives honest costs on your own historical data.
> The loop is closed: every way to be long or short earnings volatility — through the event
> or around it — loses after spreads and theta at retail scale.

That is not a disappointing result. **That is the product working.** It cost $0 and it has
stopped you from funding three losing strategies with real money. (2026-06-10 scorecard:
buy-through +0.1% avg / −100% median; short-vol −83.3% avg / −100% median; vol-ramp −7.0%
avg / −12.5% median — none survived.)

---

## 7. The biggest lessons (the part worth re-reading)

1. **"Evidence overrides the feeling" is the whole game.** The moment you committed to that,
   every "but it feels like it should work" got routed through the harness instead of through
   your bank account. Protect this rule above all others.

2. **Direction is not profit.** The implied move is the real opponent. A strategy that's right
   about direction 60% of the time can still lose money if it never beats what options already
   price in. Every future idea must be scored against the implied move, not against a coin flip
   on direction.

3. **Means lie; tails kill.** The short-vol −79.5%/−100% split is the lesson in one number.
   Always look at the median and the worst case, never just the average. A strategy that makes
   $100 ninety times and loses $10,000 once is a losing strategy that *looks* like a winner on
   average.

4. **Probe before you build.** Repeatedly, a 10-minute throwaway probe saved days. We confirmed
   Alpaca's data depth, found Alpha Vantage's free 30-year earnings history, and verified
   expired-contract option bars exist — each before committing to a design. **Verify before you
   pay** turned a planned paid FMP dependency into a $0 free one.

5. **Free first; make paid spend prove itself.** We hit FMP's 402 Payment Required and, instead
   of paying, searched and found the free Alpha Vantage path. The standing rule: paid data must
   earn its keep in the backtest first; favor one-time/evidence purchases over recurring
   subscriptions.

6. **No-lookahead is sacred, and it's easy to break by accident.** The peer filter
   (`report_date < as_of_date`), the as-of anchor walking back to the last real trading day (so
   Monday/holiday reporters aren't dropped or, worse, fed future data), and isolating the
   realized move as the *only* look-forward — these are the difference between a real backtest
   and a fantasy. A backtest with lookahead will "prove" any edge you want.

7. **Build the idea-killer before the money-spender.** Deferring the prediction engine and the
   dashboard wasn't laziness — it was discipline. They're worthless without an edge, and
   building them first would have created sunk-cost pressure to trade a losing system.

8. **Model costs pessimistically.** Bid/ask spreads and theta are where backtests that "look
   beautiful" die in real trading. The vol-ramp P&L crosses the spread twice on purpose. When in
   doubt, make the cost assumption hurt.

---

## 8. Operating constraints (carried forward, non-negotiable)

These are governance rules from `CLAUDE.md` and your direct instructions. Any future agent or
engineer must honor them:

- **Propose-only forever.** The system never places, sizes, authorizes, or recommends a trade.
  Default `ExecutionMode` is `propose_only`; `live` is a human-only decision that requires the
  risk rails present and passing.
- **Never commit secrets.** `.env` is gitignored; keys are never pasted to the assistant.
- **Never `git add -A`.** Add only specific named files. Do **not** touch `AGENTS.md` or
  `supabase/migrations/` (untracked pre-existing files from another workstream).
- **Free data only as the default.** Paid spend must prove itself in the backtest first.
- **The risk caps are ceilings, not suggestions** (3% per-trade absolute ceiling, 5% daily loss
  stop, 2 losing trades/day, $10k–$25k tier). Code is the source of truth; `CLAUDE.md` mirrors
  it, and a drift-guard test enforces the mirror.

---

## 9. Where we are, and the honest options ahead

**Where we are (updated 2026-06-10):** A complete, green, $0 disprove-first pipeline exists
end-to-end, and the loop is now **closed**: all three earnings-options approaches —
buy-through, sell-through, and buy-early-sell-before (vol-ramp) — failed the survival gate
on your own data. **No real money has been or will be risked without passing the gate.**

**The honest options from here:**

1. ~~Run the last test (vol-ramp).~~ **Done 2026-06-10: `survived=False`** (67 events,
   −7.0% avg, −12.5% median — the ramp exists but is fully priced in; the spread eats it).

2. **Accept the verdict and stop.** The evidence now says retail earnings-options has no
   survivable edge in any of the three frames we could test. The most valuable thing the
   system can do is tell you that and save your capital. That is a legitimate, successful
   outcome — arguably *the* outcome the program was built to deliver honestly.

3. **Change the game, not the tactic.** All three vol approaches failed, so the lesson is
   that the *event-timing* frame itself is the problem, not the specific trade. A different
   program (longer-horizon, systematic trend/momentum, or non-options) would be a new
   brainstorm, not a tweak. *(My recommendation for any future trading work.)*

4. **Broaden the universe / lengthen the sample.** The samples (67–73 evaluable events on
   25 liquid names) are `suggestive`, not `strong`. Worth doing only if a strategy had shown
   a pulse — none did, and all three failed in the *direction* the costs predict, so a larger
   sample is very unlikely to flip any verdict.

What we will **not** do: build the prediction engine or dashboard, or move toward paper/live
trading, until a strategy actually survives. The deal holds: **evidence overrides the feeling.**

---

## 10. Appendix — key artifacts

**Specs (`docs/superpowers/specs/`):**
- `2026-06-05-edge-measurement-backtest-harness-design.md` — sub-project 1
- `2026-06-05-edge-live-data-assembly-design.md` — sub-project 2
- `2026-06-05-historical-options-reader-design.md` — sub-project 3
- `2026-06-06-short-vol-defined-risk-design.md` — short-vol experiment
- `2026-06-07-pre-earnings-vol-ramp-design.md` — vol-ramp experiment (awaiting review)

**Code:**
- `src/prescient/edge/` — frozen scoring core
- `src/prescient/edge/data/` — free-tier data assembly
- `src/prescient/data/alpaca_market.py`, `src/prescient/live_data/alpaca_readers.py` —
  historical-options reader
- `scripts/run_edge_backtest.py` — the runnable backtest
- `config/edge_universe.yaml` — 25 liquid optionable names

**Governance:**
- `CLAUDE.md` — operating manual (propose-only, risk caps, hard rules)

**To run the first/next real backtest:**
```bash
# Add free key once:
echo 'ALPHAVANTAGE_API_KEY=YOUR_KEY_HERE' >> .env
# Smoke test:
uv run python scripts/run_edge_backtest.py --limit 20
```

---

*This document is the program's memory. Update it whenever a strategy is tested, a verdict
lands, or the direction changes. The next person — human or agent — should be able to read this
one file and understand exactly where we are and why.*
