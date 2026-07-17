from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderError:
    provider: str
    error_type: str
    message: str
    status_code: int | None = None


@dataclass(frozen=True)
class ProviderResult:
    items: list[dict] = field(default_factory=list)
    errors: list[ProviderError] = field(default_factory=list)


def missing_configuration(provider: str) -> ProviderResult:
    return ProviderResult(
        errors=[
            ProviderError(
                provider=provider,
                error_type="missing_configuration",
                message=f"{provider} is not configured.",
            )
        ]
    )


def request_error(provider: str) -> ProviderResult:
    return ProviderResult(
        errors=[
            ProviderError(
                provider=provider,
                error_type="provider_unavailable",
                message=f"{provider} data is temporarily unavailable.",
            )
        ]
    )


def status_error(provider: str, status_code: int) -> ProviderResult:
    error_type = {
        401: "unauthorized",
        403: "unauthorized",
        404: "not_found",
        429: "rate_limited",
    }.get(status_code, "provider_unavailable")
    return ProviderResult(
        errors=[
            ProviderError(
                provider=provider,
                error_type=error_type,
                message=f"{provider} returned an unsuccessful response.",
                status_code=status_code,
            )
        ]
    )
