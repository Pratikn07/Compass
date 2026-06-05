from __future__ import annotations

import pytest

from prescient.data.config import ProviderConfig


def test_from_env_reads_all_credentials() -> None:
    config = ProviderConfig.from_env(
        {
            "FINNHUB_API_KEY": "fk",
            "FMP_API_KEY": "fmpk",
            "ALPHAVANTAGE_API_KEY": "avk",
            "SEC_EDGAR_USER_AGENT": "prescient research test@example.com",
        }
    )
    assert config.finnhub_api_key == "fk"
    assert config.fmp_api_key == "fmpk"
    assert config.alphavantage_api_key == "avk"
    assert config.sec_edgar_user_agent == "prescient research test@example.com"


def test_from_env_missing_keys_are_none_not_error() -> None:
    config = ProviderConfig.from_env({})
    assert config.finnhub_api_key is None
    assert config.fmp_api_key is None
    assert config.alphavantage_api_key is None
    assert config.sec_edgar_user_agent is None


def test_from_env_blank_values_normalize_to_none() -> None:
    config = ProviderConfig.from_env(
        {"FINNHUB_API_KEY": "   ", "FMP_API_KEY": ""}
    )
    assert config.finnhub_api_key is None
    assert config.fmp_api_key is None


def test_missing_for_reports_absent_providers() -> None:
    config = ProviderConfig.from_env({"FINNHUB_API_KEY": "fk"})
    missing = config.missing_for(["finnhub", "fmp", "alphavantage", "sec_edgar"])
    assert "finnhub" not in missing
    assert set(missing) == {"fmp", "alphavantage", "sec_edgar"}


def test_missing_for_unknown_provider_raises() -> None:
    config = ProviderConfig.from_env({})
    with pytest.raises(ValueError):
        config.missing_for(["not_a_provider"])


def test_repr_does_not_leak_secrets() -> None:
    config = ProviderConfig.from_env(
        {"FINNHUB_API_KEY": "super-secret-key"}
    )
    assert "super-secret-key" not in repr(config)


def test_alpaca_requires_both_key_and_secret() -> None:
    # Alpaca is available only when BOTH the key id and secret are present.
    both = ProviderConfig.from_env(
        {"ALPACA_API_KEY_ID": "kid", "ALPACA_API_SECRET_KEY": "secret"}
    )
    assert both.has("alpaca") is True
    assert both.alpaca_api_key_id == "kid"
    assert both.alpaca_api_secret_key == "secret"

    only_key = ProviderConfig.from_env({"ALPACA_API_KEY_ID": "kid"})
    assert only_key.has("alpaca") is False

    only_secret = ProviderConfig.from_env({"ALPACA_API_SECRET_KEY": "secret"})
    assert only_secret.has("alpaca") is False


def test_alpaca_secret_not_leaked_in_repr() -> None:
    config = ProviderConfig.from_env(
        {"ALPACA_API_KEY_ID": "kid", "ALPACA_API_SECRET_KEY": "top-secret-alpaca"}
    )
    assert "top-secret-alpaca" not in repr(config)
    assert "kid" not in repr(config)
