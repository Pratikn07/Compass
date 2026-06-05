# PRD: R5A Provider Readiness & Contract Audit

## Ownership

- **Layer:** `prescient.data` (read-only provider adapters) + a new provider-config seam.
- **Phase:** A of the Live Provider Data roadmap (`05-live-data-phase-roadmap.md`).
- **Depends on:** the existing adapters (`finnhub.py`, `fmp.py`, `alpha_vantage.py`,
  `sec_edgar.py`). Blocks Phase B (input assembly).

## Objective

Make the existing data adapters **runnable against the live APIs** and produce a
**contract audit** that maps, per provider, what the adapter returns today versus
what Phase B's input-assembly layer will need.

R5A answers:

```text
Do our already-built adapters actually work against the live provider APIs right now,
with real keys — and where does their real output fall short of what the pipeline needs?
```

This phase writes **no pipeline-assembly code**. It (1) establishes a single, tested
way to construct each adapter from configuration/keys, (2) verifies each adapter against
the live API with a small set of real calls, and (3) records the gaps as a checked-in
audit that Phase B is built against. The point is to surface provider reality (shape
drift, missing fields, rate limits, auth quirks) **before** building the assembly layer
on top of assumptions.

## Background

The adapters are substantial and real (Finnhub ~958 lines, FMP ~482, AlphaVantage ~471,
SEC EDGAR ~324) with injectable HTTP transports. But:

- Each adapter is constructed ad hoc (constructor takes `api_key` / `user_agent`
  directly). There is **no central, tested seam** that builds all providers from
  environment configuration — so "run them for real" currently has no single entry.
- They have **never been exercised against the live APIs** in this project (tests use
  injected fake transports). Provider response shapes drift; free-tier limits and auth
  behaviors are unverified.
- Phase B must map adapter output → pipeline input types (`EarningsCalendarEvent`,
  `PeerResult`, `TargetMarketData`, indicators). That mapping can only be designed
  correctly once we know what the adapters **actually** return live.

Providers and credentials:

| Provider | Env var | Free tier | Notes |
|---|---|---|---|
| Finnhub | `FINNHUB_API_KEY` | yes | earnings calendar, estimates/actuals |
| FMP | `FMP_API_KEY` | yes | stock peers |
| AlphaVantage | `ALPHAVANTAGE_API_KEY` | yes (25 req/day) | news sentiment; tight limit |
| SEC EDGAR | `SEC_EDGAR_USER_AGENT` (no key) | n/a | requires descriptive User-Agent |

This phase stays read-only, Claude-free, broker-free, propose-only — same rails as the
rest of the system. Live calls happen only in an explicitly-invoked verification script,
never in the unit-test suite or the pipeline.

## Functional Requirements

### R5A.1 Provider Configuration Seam

Add a single, typed configuration object and factory that constructs each adapter from
environment configuration, mirroring the existing `*.from_env` patterns
(`SupabaseStorageAdapter.from_env`, `SupabaseModeStateStore.from_env`).

```python
# prescient/data/config.py
from collections.abc import Mapping

class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    finnhub_api_key: str | None = None
    fmp_api_key: str | None = None
    alphavantage_api_key: str | None = None
    sec_edgar_user_agent: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ProviderConfig": ...

    def missing_for(self, providers: list[str]) -> list[str]:
        """Return the names of providers whose required credential is absent."""
```

- Construction must **not** raise when a key is missing; it records absence so callers
  can decide (a per-provider "available?" check). A provider with no credential is
  *unavailable*, not an error at construction time.
- No secret values may appear in `__repr__`, logs, or error messages (reuse the existing
  secret-safe error patterns in `prescient.data`).

### R5A.2 Adapter Construction Helpers

Provide small factory helpers that build each existing adapter from a `ProviderConfig`
(+ an optional injected HTTP client for tests), without changing adapter internals:

```python
def build_finnhub_adapter(config, http_client=None) -> FinnhubEarningsAdapter | None
def build_fmp_adapter(config, http_client=None) -> FmpStockPeersAdapter | None
def build_alpha_vantage_adapter(config, http_client=None) -> AlphaVantageNewsSentimentAdapter | None
def build_sec_edgar_adapter(config, http_client=None) -> SecEdgarFundamentalsAdapter | None
```

- Each returns `None` when its credential is absent (caller treats provider as
  unavailable). This is the seam Phase B/D will use.

### R5A.3 Live Verification Script (network, explicit-only)

Add a script `scripts/verify_providers.py` (NOT a pytest test) that, given real env
keys, makes a **small bounded** set of live calls per provider and prints a structured
PASS/FAIL per provider with the observed response shape.

- Bounded: at most a handful of calls total (respect AlphaVantage's 25/day limit — at
  most 1–2 calls there).
- Read-only. No writes to Supabase, no pipeline run, no broker.
- On provider error, prints the normalized `DataProviderError` (secret-safe), never a
  raw traceback with the key.
- Exit non-zero if any *configured* provider fails its smoke call (missing-key providers
  are reported as "skipped", not failed).

### R5A.4 Contract Audit Document

Produce `docs/prd/05-live-data-provider-contract-audit.md` capturing, per provider:

- The live call(s) made and a redacted/representative sample of the real response.
- The adapter's normalized output type and fields actually populated.
- **The gap to Phase B inputs:** which pipeline-input fields (`EarningsCalendarEvent`,
  `PeerResult.*`, `TargetMarketData.*`, indicators) the provider can fill, which it
  cannot, and which require derivation or a different provider.
- Rate-limit / auth observations relevant to a daily cron.
- An explicit callout that **options-chain data has no provider** (defers to Phase C).

This document is the authoritative input to Phase B's design.

### R5A.5 No Pipeline or Assembly Code

This phase must not add or modify input-assembly logic, the pipeline, the cron, or the
seed module. It only adds: the config seam (R5A.1), construction helpers (R5A.2), the
verification script (R5A.3), and the audit doc (R5A.4).

### R5A.6 Secret Handling

- Keys are read from environment only; never committed. `.env.example` already lists the
  names; no real values enter git.
- The verification script reads from the process env (local `.env` or exported vars).
- For eventual cron use, keys will live in Railway service env (Phase D) — out of scope
  here beyond noting it.

## Acceptance Criteria

1. `ProviderConfig.from_env` + the four `build_*_adapter` helpers exist, are unit-tested
   with **injected fake transports** (no live calls in the suite), and return `None`
   for missing credentials.
2. Constructing config/adapters never raises on missing keys and never leaks secrets.
3. `scripts/verify_providers.py` runs against real keys, makes bounded live calls, and
   prints per-provider PASS / FAIL / SKIPPED with observed shapes; exits non-zero on a
   configured-provider failure.
4. `docs/prd/05-live-data-provider-contract-audit.md` exists and, for each of Finnhub /
   FMP / AlphaVantage / SEC EDGAR, documents real output vs. Phase B input needs and the
   identified gaps (including the options-chain gap).
5. Full existing backend suite stays green; `ruff check .` clean.
6. No changes to pipeline, cron, seed, or assembly code.

## Non-Goals

- Building the input-assembly layer (Phase B).
- Sourcing options-chain data (Phase C).
- The live cron / orchestration (Phase D).
- Caching, retries, rate-limit budgeting (Phase E).
- Adding new providers beyond the four already present.
- Any write to Supabase or any broker/Claude interaction.

## Open Questions

1. **AlphaVantage's 25/day free limit** may be too tight for a daily multi-ticker cron —
   the audit should note whether news sentiment is viable on free tier or needs a paid
   tier / different cadence. (Decision deferred to Phase B/D, flagged here.)
2. **SEC EDGAR User-Agent**: confirm the exact descriptive string format SEC requires
   (they can block generic agents). The verification script must use a real one.
3. Whether `financial_datasets.py` / `daloopa.py` should be part of the live path or
   remain alternates — the audit notes their status but Phase A does not wire them.

## Product FAQ

**Q: Why audit before building assembly?** Because the adapters have never run live;
their real output shape is unverified. Designing Phase B's mapping on assumptions is the
exact "smooth over provider reality" trap. The audit makes provider reality explicit and
checked-in.

**Q: Why no live calls in the test suite?** Live calls are nondeterministic, rate-limited,
and need secrets — they would make CI flaky and slow. The suite uses injected fakes; the
explicit `verify_providers.py` script is the one place real calls happen, run by a human.

**Q: Does this phase change anything users see?** No. It's readiness + documentation. The
dashboard still shows the seeded decision until Phases B–D replace it with live data.
