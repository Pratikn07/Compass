from __future__ import annotations

from pathlib import Path


def test_loads_committed_universe_and_rule() -> None:
    from prescient.edge.universe import load_edge_universe

    universe = load_edge_universe(Path("config/edge_universe.yaml"))
    assert len(universe.tickers) >= 20
    assert "MU" in universe.tickers
    assert universe.tickers == [t.upper() for t in universe.tickers]
    # tickers unique
    assert len(universe.tickers) == len(set(universe.tickers))
    # rule metadata present
    assert universe.rule.min_market_cap_usd > 0
    assert universe.rule.min_option_open_interest > 0
    assert universe.rule.min_years_history >= 1


def test_universe_rejects_empty(tmp_path) -> None:
    import pytest

    from prescient.edge.universe import load_edge_universe

    bad = tmp_path / "u.yaml"
    bad.write_text("tickers: []\nrule: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_edge_universe(bad)
