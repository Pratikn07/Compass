"""Universe must match the rulebook's Appendix A, and membership filtering
must be point-in-time correct (rulebook §4)."""
from datetime import date

from compass.universe import (
    BENCHMARKS,
    ETFS,
    MEMBERS,
    THEMES,
    active_members,
    all_tickers,
)


def test_counts_match_appendix_a():
    assert len(THEMES) == 10
    assert len(MEMBERS) == 74
    assert len(ETFS) == 8
    assert len(BENCHMARKS) == 3


def test_no_duplicate_tickers():
    tickers = all_tickers()
    assert len(tickers) == len(set(tickers)) == 85


def test_every_member_belongs_to_a_known_theme():
    slugs = {t.slug for t in THEMES}
    assert all(m.theme_slug in slugs for m in MEMBERS)


def test_primary_etf_themes_match_appendix():
    primaries = {t.slug: t.etf_ticker for t in THEMES if t.etf_is_primary}
    assert primaries == {
        "ai-chips": "SMH",
        "cloud-software": "IGV",
        "cybersecurity": "CIBR",
        "healthcare-glp1": "XLV",
        "airlines-travel": "JETS",
        "banks-payments": "XLF",
        "energy": "XLE",
        "big-box-retail": "XLY",
    }
    basket_only = {t.slug for t in THEMES if t.etf_ticker is None}
    assert basket_only == {"ai-memory-storage", "data-centers-power"}


def test_every_member_has_justification():
    assert all(m.justification.strip() for m in MEMBERS)


def test_point_in_time_membership_excludes_not_yet_joined():
    # SNDK joined ai-memory-storage 2025-02; it must be invisible before that.
    before = {m.ticker for m in active_members("ai-memory-storage", date(2024, 6, 1))}
    after = {m.ticker for m in active_members("ai-memory-storage", date(2025, 6, 1))}
    assert "SNDK" not in before
    assert "SNDK" in after
    assert "MU" in before  # backdated member visible throughout


def test_membership_boundary_is_inclusive_on_since():
    members_on_join_day = {
        m.ticker for m in active_members("ai-chips", date(2023, 9, 1))
    }
    assert "ARM" in members_on_join_day
    day_before = {m.ticker for m in active_members("ai-chips", date(2023, 8, 31))}
    assert "ARM" not in day_before
