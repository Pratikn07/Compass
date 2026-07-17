from __future__ import annotations

import hashlib
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from compass.api.auth import (
    AuthContext,
    AuthError,
    AuthSettings,
    SupabaseClaimsVerifier,
    authenticate,
    get_auth_settings,
    get_claims_verifier,
    require_owner,
)

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")


def settings(*, token: str | None = None) -> AuthSettings:
    return AuthSettings(
        owner_id=OWNER_ID,
        supabase_url="https://example.supabase.co",
        api_token_sha256=hashlib.sha256(token.encode()).hexdigest() if token else None,
    )


def test_personal_token_authentication_returns_owner_context() -> None:
    context = authenticate(
        authorization=None,
        api_token="personal-secret",
        settings=settings(token="personal-secret"),
        verify_claims=lambda _token: pytest.fail("JWT verifier should not run"),
    )

    assert context.owner_id == OWNER_ID
    assert context.auth_method == "api_token"


def test_personal_token_authentication_rejects_wrong_token() -> None:
    with pytest.raises(AuthError, match="invalid credentials"):
        authenticate(
            authorization=None,
            api_token="wrong",
            settings=settings(token="personal-secret"),
            verify_claims=lambda _token: {},
        )


def test_supabase_jwt_requires_matching_verified_claims() -> None:
    context = authenticate(
        authorization="Bearer signed-user-token",
        api_token=None,
        settings=settings(),
        verify_claims=lambda token: {
            "sub": str(OWNER_ID),
            "iss": "https://example.supabase.co/auth/v1",
            "aud": "authenticated",
            "role": "authenticated",
            "is_anonymous": False,
            "token": token,
        },
    )

    assert context.owner_id == OWNER_ID
    assert context.auth_method == "supabase_jwt"


def test_supabase_claims_verifier_reads_sdk_typed_dict(monkeypatch) -> None:
    claims = {
        "sub": str(OWNER_ID),
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "is_anonymous": False,
    }

    class FakeAuth:
        def get_claims(self, token: str) -> dict[str, object]:
            assert token == "signed-user-token"
            return {"claims": claims, "headers": {}, "signature": b""}

    class FakeClient:
        auth = FakeAuth()

    monkeypatch.setattr("supabase.create_client", lambda *_args: FakeClient())

    verifier = SupabaseClaimsVerifier(
        supabase_url="https://example.supabase.co",
        publishable_key="sb_publishable_example",
    )

    assert verifier("signed-user-token") == claims


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sub", "22222222-2222-4222-8222-222222222222"),
        ("iss", "https://attacker.example/auth/v1"),
        ("aud", "anon"),
        ("role", "anon"),
        ("is_anonymous", True),
    ],
)
def test_supabase_jwt_rejects_wrong_identity_or_scope(claim: str, value: object) -> None:
    claims = {
        "sub": str(OWNER_ID),
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "is_anonymous": False,
    }
    claims[claim] = value

    with pytest.raises(AuthError, match="invalid credentials"):
        authenticate(
            authorization="Bearer signed-user-token",
            api_token=None,
            settings=settings(),
            verify_claims=lambda _token: claims,
        )


def test_authentication_requires_exact_bearer_scheme() -> None:
    with pytest.raises(AuthError, match="invalid credentials"):
        authenticate(
            authorization="Basic abc123",
            api_token=None,
            settings=settings(),
            verify_claims=lambda _token: {},
        )


def dependency_test_client(
    *,
    configured: AuthSettings,
    verifier=lambda _token: {},
) -> TestClient:
    test_app = FastAPI()

    @test_app.get("/private")
    def private(
        context: Annotated[AuthContext, Depends(require_owner)],
    ) -> dict[str, str]:
        return {"owner_id": str(context.owner_id), "method": context.auth_method}

    test_app.dependency_overrides[get_auth_settings] = lambda: configured
    test_app.dependency_overrides[get_claims_verifier] = lambda: verifier
    return TestClient(test_app)


def test_fastapi_dependency_requires_credentials() -> None:
    response = dependency_test_client(configured=settings(token="secret")).get("/private")

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_fastapi_dependency_accepts_personal_token_header() -> None:
    response = dependency_test_client(configured=settings(token="secret")).get(
        "/private", headers={"X-Compass-Key": "secret"}
    )

    assert response.status_code == 200
    assert response.json() == {"owner_id": str(OWNER_ID), "method": "api_token"}
