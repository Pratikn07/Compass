from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class AuthSettings:
    owner_id: UUID
    supabase_url: str
    api_token_sha256: str | None = None
    supabase_publishable_key: str | None = None


@dataclass(frozen=True)
class AuthContext:
    owner_id: UUID
    auth_method: Literal["api_token", "supabase_jwt"]


ClaimsVerifier = Callable[[str], Mapping[str, object]]


class SupabaseClaimsVerifier:
    def __init__(self, *, supabase_url: str, publishable_key: str) -> None:
        from supabase import create_client

        self._client = create_client(supabase_url, publishable_key)

    def __call__(self, token: str) -> Mapping[str, object]:
        response = self._client.auth.get_claims(token)
        if response is None:
            raise AuthError("invalid credentials")
        return response.claims


def get_auth_settings() -> AuthSettings:
    owner_id = os.environ.get("COMPASS_OWNER_USER_ID", "").strip()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not owner_id or not supabase_url or not publishable_key:
        raise RuntimeError("Compass authentication is not configured")
    return AuthSettings(
        owner_id=UUID(owner_id),
        supabase_url=supabase_url,
        api_token_sha256=os.environ.get("COMPASS_API_TOKEN_SHA256") or None,
        supabase_publishable_key=publishable_key,
    )


def get_claims_verifier(
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> ClaimsVerifier:
    if settings.supabase_publishable_key is None:
        raise RuntimeError("Supabase publishable key is not configured")
    return SupabaseClaimsVerifier(
        supabase_url=settings.supabase_url,
        publishable_key=settings.supabase_publishable_key,
    )


def authenticate(
    *,
    authorization: str | None,
    api_token: str | None,
    settings: AuthSettings,
    verify_claims: ClaimsVerifier,
) -> AuthContext:
    if authorization is not None:
        scheme, separator, token = authorization.partition(" ")
        if scheme != "Bearer" or separator != " " or not token:
            raise AuthError("invalid credentials")
        try:
            claims = verify_claims(token)
        except Exception as exc:
            raise AuthError("invalid credentials") from exc

        audience = claims.get("aud")
        audience_matches = audience == "authenticated" or (
            isinstance(audience, list) and "authenticated" in audience
        )
        expected_issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        if (
            claims.get("sub") != str(settings.owner_id)
            or claims.get("iss") != expected_issuer
            or not audience_matches
            or claims.get("role") != "authenticated"
            or claims.get("is_anonymous") is not False
        ):
            raise AuthError("invalid credentials")
        return AuthContext(owner_id=settings.owner_id, auth_method="supabase_jwt")

    if api_token is not None and settings.api_token_sha256 is not None:
        supplied_hash = hashlib.sha256(api_token.encode()).hexdigest()
        if hmac.compare_digest(supplied_hash, settings.api_token_sha256):
            return AuthContext(owner_id=settings.owner_id, auth_method="api_token")

    raise AuthError("invalid credentials")


def require_owner(
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    verify_claims: Annotated[ClaimsVerifier, Depends(get_claims_verifier)],
) -> AuthContext:
    try:
        return authenticate(
            authorization=request.headers.get("Authorization"),
            api_token=request.headers.get("X-Compass-Key"),
            settings=settings,
            verify_claims=verify_claims,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from exc
