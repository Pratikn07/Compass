"""Bounded, read-only live verification of the data-provider adapters.

NOT a pytest test. Run manually with real keys in the environment:

    FINNHUB_API_KEY=... FMP_API_KEY=... ALPHAVANTAGE_API_KEY=... \
    SEC_EDGAR_USER_AGENT="prescient research you@example.com" \
    uv run python scripts/verify_providers.py

Makes a SMALL number of live calls per configured provider and prints
PASS / FAIL / SKIPPED with the observed response shape. Providers without a
credential are SKIPPED (not failed). Exits non-zero if any *configured* provider
fails its smoke call. Respects AlphaVantage's tight free limit (1 call).

Read-only: no Supabase writes, no pipeline run, no broker, no Claude.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from prescient.data.config import ProviderConfig
from prescient.data.providers import (
    build_alpha_vantage_adapter,
    build_finnhub_adapter,
    build_fmp_adapter,
    build_sec_edgar_adapter,
)

# Stable public test inputs.
_APPLE_CIK = 320193
_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIPPED"


def _report(provider: str, status: str, detail: str) -> None:
    print(f"[{status:7}] {provider:14} {detail}")


def _summarize_errors(errors: list[object]) -> str:
    # DataProviderError is secret-safe by construction; show its message/type only.
    parts = []
    for err in errors[:3]:
        etype = getattr(err, "error_type", None)
        msg = getattr(err, "message", str(err))
        parts.append(f"{getattr(etype, 'value', etype)}: {msg}")
    return "; ".join(parts)


def _check_result(provider: str, result: object) -> bool:
    errors = list(getattr(result, "errors", []))
    snapshots = list(getattr(result, "snapshots", []))
    if errors:
        _report(provider, _FAIL, _summarize_errors(errors))
        return False
    _report(provider, _PASS, f"{len(snapshots)} snapshot(s) returned")
    return True


def verify(config: ProviderConfig) -> int:
    any_failed = False

    # --- Finnhub: earnings calendar for a short forward window ---
    finnhub = build_finnhub_adapter(config)
    if finnhub is None:
        _report("finnhub", _SKIP, "FINNHUB_API_KEY not set")
    else:
        try:
            today = date.fromisoformat(os.environ.get("VERIFY_DATE", "") or _today())
            result = finnhub.get_earnings_calendar(today, today + timedelta(days=7))
            any_failed |= not _check_result("finnhub", result)
        except Exception as exc:  # network/transport-level failure
            _report("finnhub", _FAIL, f"exception: {type(exc).__name__}")
            any_failed = True

    # --- FMP: stock peers for one ticker ---
    fmp = build_fmp_adapter(config)
    if fmp is None:
        _report("fmp", _SKIP, "FMP_API_KEY not set")
    else:
        try:
            any_failed |= not _check_result("fmp", fmp.get_stock_peers("AAPL"))
        except Exception as exc:
            _report("fmp", _FAIL, f"exception: {type(exc).__name__}")
            any_failed = True

    # --- AlphaVantage: ONE news-sentiment call (free tier is 25/day) ---
    alpha = build_alpha_vantage_adapter(config)
    if alpha is None:
        _report("alphavantage", _SKIP, "ALPHAVANTAGE_API_KEY not set")
    else:
        try:
            result = alpha.get_news_sentiment(tickers=["AAPL"], limit=1)
            any_failed |= not _check_result("alphavantage", result)
        except Exception as exc:
            _report("alphavantage", _FAIL, f"exception: {type(exc).__name__}")
            any_failed = True

    # --- SEC EDGAR: company facts for a stable CIK (Apple) ---
    sec = build_sec_edgar_adapter(config)
    if sec is None:
        _report("sec_edgar", _SKIP, "SEC_EDGAR_USER_AGENT not set")
    else:
        try:
            result = sec.get_company_facts(_APPLE_CIK, ticker="AAPL")
            errors = list(getattr(result, "errors", []))
            if errors:
                _report("sec_edgar", _FAIL, _summarize_errors(errors))
                any_failed = True
            else:
                _report("sec_edgar", _PASS, "company facts returned")
        except Exception as exc:
            _report("sec_edgar", _FAIL, f"exception: {type(exc).__name__}")
            any_failed = True

    return 1 if any_failed else 0


def _today() -> str:
    # Avoid importing date.today at module import for testability; cron passes
    # VERIFY_DATE or we use the real today here at call time.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()


def main() -> int:
    config = ProviderConfig.from_env(os.environ)
    print(f"Provider verification — {config}")
    print("-" * 60)
    code = verify(config)
    print("-" * 60)
    print("DONE" if code == 0 else "ONE OR MORE CONFIGURED PROVIDERS FAILED")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
