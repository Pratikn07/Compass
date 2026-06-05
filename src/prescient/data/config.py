"""Provider configuration seam.

A single, typed way to read all data-provider credentials from the environment and
ask which providers are available. Construction never raises on missing keys — a
provider with no credential is simply *unavailable*, a decision left to the caller.

Secret values never appear in repr/logs.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

# Logical provider name -> the ProviderConfig field that gates its availability.
_PROVIDER_FIELDS: dict[str, str] = {
    "finnhub": "finnhub_api_key",
    "fmp": "fmp_api_key",
    "alphavantage": "alphavantage_api_key",
    "sec_edgar": "sec_edgar_user_agent",
}

# Providers needing more than one credential get a custom availability rule below.
_MULTI_CREDENTIAL_PROVIDERS = ("alpaca",)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finnhub_api_key: str | None = None
    fmp_api_key: str | None = None
    alphavantage_api_key: str | None = None
    sec_edgar_user_agent: str | None = None
    alpaca_api_key_id: str | None = None
    alpaca_api_secret_key: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ProviderConfig":
        return cls(
            finnhub_api_key=_clean(env.get("FINNHUB_API_KEY")),
            fmp_api_key=_clean(env.get("FMP_API_KEY")),
            alphavantage_api_key=_clean(env.get("ALPHAVANTAGE_API_KEY")),
            sec_edgar_user_agent=_clean(env.get("SEC_EDGAR_USER_AGENT")),
            alpaca_api_key_id=_clean(env.get("ALPACA_API_KEY_ID")),
            alpaca_api_secret_key=_clean(env.get("ALPACA_API_SECRET_KEY")),
        )

    def has(self, provider: str) -> bool:
        """True when the named provider has all required credentials."""
        if provider == "alpaca":
            return (
                self.alpaca_api_key_id is not None
                and self.alpaca_api_secret_key is not None
            )
        field = self._field_for(provider)
        return getattr(self, field) is not None

    def missing_for(self, providers: list[str]) -> list[str]:
        """Names of providers (from the given list) whose credential is absent."""
        return [p for p in providers if not self.has(p)]

    @staticmethod
    def _field_for(provider: str) -> str:
        try:
            return _PROVIDER_FIELDS[provider]
        except KeyError:
            known = sorted([*_PROVIDER_FIELDS, *_MULTI_CREDENTIAL_PROVIDERS])
            raise ValueError(
                f"Unknown provider {provider!r}; known: {known}"
            ) from None

    def __repr__(self) -> str:
        # Never leak secret values; report only which providers are configured.
        all_providers = [*_PROVIDER_FIELDS, *_MULTI_CREDENTIAL_PROVIDERS]
        configured = [p for p in all_providers if self.has(p)]
        return f"ProviderConfig(configured={configured})"

    __str__ = __repr__
