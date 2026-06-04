"""R7.1 — CLAUDE.md operating manual.

These tests treat CLAUDE.md as the prose mirror of the code-owned rails.
The drift-guard tests read the authoritative values from ``prescient.risk`` so
that changing a code default without updating CLAUDE.md fails the suite
(enforces R7.1.6 "prose must not exceed code" and R7.1.8 "drift is a defect").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prescient.risk import (
    AccountSizePolicySettings,
    DailyHaltSettings,
    ExecutionMode,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


@pytest.fixture(scope="module")
def manual_text() -> str:
    assert CLAUDE_MD.exists(), f"CLAUDE.md must exist at repo root: {CLAUDE_MD}"
    return CLAUDE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def manual_lower(manual_text: str) -> str:
    return manual_text.lower()


# ── R7.1.1 Existence / format ──────────────────────────────────────────────


def test_claude_md_exists_at_repo_root() -> None:
    assert CLAUDE_MD.exists(), "CLAUDE.md must exist at the repository root"


def test_claude_md_is_non_empty_markdown(manual_text: str) -> None:
    assert manual_text.strip(), "CLAUDE.md must not be empty"
    assert "#" in manual_text, "CLAUDE.md must be Markdown with headings"


# ── R7.1.2–R7.1.8 Required sections ────────────────────────────────────────


@pytest.mark.parametrize(
    "needle",
    [
        "system statement",
        "hard rules",
        "risk caps",
        "live-trading rule",
        "session contract",
        "maintenance rule",
    ],
)
def test_required_sections_present(manual_lower: str, needle: str) -> None:
    assert needle in manual_lower, f"CLAUDE.md must contain a '{needle}' section"


# ── R7.1.2 System statement ────────────────────────────────────────────────


def test_system_statement_describes_principle(manual_lower: str) -> None:
    # "code owns the rails; Claude advises within them"
    assert "rails" in manual_lower
    assert "advis" in manual_lower  # advisory / advises
    # the layered boundary
    for layer in ("signal", "analyst", "risk", "broker"):
        assert layer in manual_lower, f"system statement must name the '{layer}' layer"


# ── R7.1.3 Hard rules content ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "needle",
    [
        "never",  # the never-do framing
        "advisory",  # Claude is advisory only (R2.5)
        "claude_override_attempted",  # references the enforcing reason (R3.1.5)
    ],
)
def test_hard_rules_content(manual_lower: str, needle: str) -> None:
    assert needle in manual_lower, f"Hard Rules must mention '{needle}'"


# ── R7.1.4 Risk caps + source of truth (drift guard) ───────────────────────


def test_risk_caps_match_code(manual_text: str) -> None:
    account = AccountSizePolicySettings()
    halt = DailyHaltSettings()

    # Per-trade ceiling 0.03 -> 3%
    assert "3%" in manual_text, "must quote the 3% absolute per-trade ceiling"
    assert account.absolute_trade_loss_pct_ceiling == 0.03
    # Tier default 0.01 -> 1%
    assert "1%" in manual_text, "must quote the 1% tier default per-trade cap"
    assert account.tier_default_trade_loss_pct == 0.01
    # Daily realized loss stop 0.05 -> 5%
    assert "5%" in manual_text, "must quote the 5% daily realized loss stop"
    assert halt.max_daily_realized_loss_pct == 0.05
    # Max losing trades per day == 2
    assert halt.max_losing_trades_per_day == 2
    assert "2" in manual_text


def test_account_tier_matches_code(manual_text: str) -> None:
    account = AccountSizePolicySettings()
    assert account.supported_min_equity == 10_000.0
    assert account.supported_max_equity == 25_000.0
    # Accept "$10,000" or "$10k" style; require both bounds present in some form.
    assert ("$10,000" in manual_text) or ("$10k" in manual_text.lower())
    assert ("$25,000" in manual_text) or ("$25k" in manual_text.lower())


def test_names_risk_module_as_source_of_truth(manual_lower: str) -> None:
    assert ("prescient.risk" in manual_lower) or ("risk/models.py" in manual_lower), (
        "CLAUDE.md must name prescient.risk / risk/models.py as the authoritative "
        "source of truth for risk values (R7.1.4)"
    )


# ── R7.1.5 Live-trading rule ───────────────────────────────────────────────


def test_execution_modes_documented(manual_lower: str) -> None:
    for mode in ExecutionMode:
        assert mode.value in manual_lower, f"CLAUDE.md must document the '{mode.value}' mode"


def test_propose_only_is_default(manual_lower: str) -> None:
    assert "propose_only" in manual_lower
    assert "default" in manual_lower


def test_live_requires_human_authorization(manual_lower: str) -> None:
    assert "live" in manual_lower
    assert "human" in manual_lower
    # never auto-enable live
    assert "never" in manual_lower


# ── R7.1.6 Prose must not exceed code ──────────────────────────────────────


def test_prose_does_not_loosen_ceiling(manual_text: str) -> None:
    """The manual must not quote a per-trade cap looser than the code ceiling."""
    account = AccountSizePolicySettings()
    assert account.absolute_trade_loss_pct_ceiling == 0.03
    # Guard against accidentally documenting a looser cap.
    for looser in ("4%", "5% per trade", "10% per trade"):
        assert looser not in manual_text, f"CLAUDE.md must not loosen per-trade cap to {looser}"
