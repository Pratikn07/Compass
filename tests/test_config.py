from vanta import config


def test_universe_contains_target_and_peers():
    symbols = {t.symbol for t in config.UNIVERSE}
    assert "MU" in symbols
    assert {"WDC", "SNDK", "NVDA", "AMD", "AVGO"} <= symbols


def test_target_ticker_is_mu():
    assert config.TARGET == "MU"


def test_each_ticker_has_theme_and_role():
    for t in config.UNIVERSE:
        assert t.symbol
        assert t.theme == "AI Memory"
        assert t.role in {"target", "rival", "demand_driver"}


def test_mu_role_is_target():
    mu = next(t for t in config.UNIVERSE if t.symbol == "MU")
    assert mu.role == "target"


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "abc123")
    assert config.require_env("FINNHUB_API_KEY") == "abc123"


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="MISSING_KEY"):
        config.require_env("MISSING_KEY")
