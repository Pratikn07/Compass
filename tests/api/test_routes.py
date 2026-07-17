from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from compass.api.auth import AuthSettings, get_auth_settings, get_claims_verifier
from compass.api.dependencies import get_repository
from compass.api.main import app

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")


class ApiRepository:
    def __init__(self) -> None:
        self.acknowledged = False

    def ping(self) -> None:
        return None

    def detailed_health(self) -> dict:
        return {"status": "healthy", "latest_price_date": "2026-07-16"}

    def list_themes(self) -> list[dict]:
        return [{"slug": "ai-chips", "name": "AI chips", "state": {"trend_on": True}}]

    def theme_detail(self, slug: str, *, days: int) -> dict | None:
        if slug != "ai-chips":
            return None
        return {"slug": slug, "members": [], "state_history": [], "days": days}

    def recommendations_today(self) -> dict:
        return {
            "d": "2026-07-16",
            "recommendations": [
                {"decision_id": "decision-1", "action": "none", "acknowledged_at": None}
            ],
        }

    def journal(self, *, days: int) -> dict:
        return {"days": days, "decisions": [], "overrides": []}

    def list_rule_changes(self) -> list[dict]:
        return []

    def create_override(self, *, what: str, reason: str) -> dict:
        return {"id": 1, "what": what, "reason": reason}

    def acknowledge_decision(self, decision_id: str, *, acknowledged_at: str) -> dict | None:
        if decision_id != "decision-1":
            return None
        self.acknowledged = True
        return {"decision_id": decision_id, "acknowledged_at": acknowledged_at}

    def create_rule_change(self, row: dict) -> dict:
        return {"id": 1, **row}

    def latest_backtest(self) -> dict | None:
        return {"learning_report_id": "report-1", "report_type": "edge_backtest"}

    def list_decisions(self, *, limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
        return ([{"decision_id": "decision-1", "limit": limit, "cursor": cursor}], None)

    def decision_detail(self, decision_id: str) -> dict | None:
        if decision_id != "decision-1":
            return None
        return {"decision": {"decision_id": decision_id}, "journal": []}

    def list_runs(self, *, limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
        return ([{"run_id": "nightly:2026-07-16", "limit": limit, "cursor": cursor}], None)

    def provider_health(self) -> dict:
        return {"providers": [], "recent_errors": []}

    def system_health(self) -> list[dict]:
        return [{"component": "database", "status": "healthy"}]


@pytest.fixture
def repository() -> ApiRepository:
    return ApiRepository()


@pytest.fixture
def client(repository: ApiRepository):
    token = "personal-secret"
    configured = AuthSettings(
        owner_id=OWNER_ID,
        supabase_url="https://example.supabase.co",
        api_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
    )
    claims = {
        "sub": str(OWNER_ID),
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "role": "authenticated",
        "is_anonymous": False,
    }
    app.dependency_overrides.clear()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_auth_settings] = lambda: configured
    app.dependency_overrides[get_claims_verifier] = lambda: (lambda _token: claims)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def api_token_headers() -> dict[str, str]:
    return {"X-Compass-Key": "personal-secret"}


def test_data_and_detailed_health_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/v1/themes").status_code == 401
    assert client.get("/v1/health").status_code == 401
    assert client.get("/v1/live").status_code == 200
    assert client.get("/v1/ready").status_code == 200


def test_personal_token_and_supabase_jwt_can_read_advisor_routes(client: TestClient) -> None:
    token_response = client.get("/v1/themes", headers=api_token_headers())
    jwt_response = client.get(
        "/v1/themes", headers={"Authorization": "Bearer signed-user-token"}
    )

    assert token_response.status_code == 200
    assert token_response.json()[0]["slug"] == "ai-chips"
    assert jwt_response.status_code == 200


def test_advisor_routes_preserve_compass_contracts(client: TestClient) -> None:
    headers = api_token_headers()

    assert client.get("/v1/themes/nope", headers=headers).status_code == 404
    assert client.get("/v1/recommendations/today", headers=headers).json()["d"] == "2026-07-16"
    assert client.get("/v1/journal?days=30", headers=headers).json()["days"] == 30
    assert client.get("/v1/rule-changes", headers=headers).json() == []


def test_governance_writes_validate_and_remain_idempotent(
    client: TestClient, repository: ApiRepository
) -> None:
    headers = api_token_headers()
    blank = client.post("/v1/overrides", headers=headers, json={"what": "sold", "reason": ""})
    created = client.post(
        "/v1/overrides",
        headers=headers,
        json={"what": "sold", "reason": "changed my mind"},
    )
    ack = client.post("/v1/recommendations/decision-1/ack", headers=headers)
    missing = client.post("/v1/recommendations/missing/ack", headers=headers)

    assert blank.status_code == 422
    assert created.status_code == 201
    assert ack.status_code == 200
    assert repository.acknowledged is True
    assert missing.status_code == 404


def test_rule_change_cooling_off_clock_is_server_owned(client: TestClient) -> None:
    response = client.post(
        "/v1/rule-changes",
        headers=api_token_headers(),
        json={"change": {"sma_n": 150}},
    )

    proposed = datetime.fromisoformat(response.json()["proposed_at"])
    effective = datetime.fromisoformat(response.json()["effective_at"])
    assert response.status_code == 201
    assert effective - proposed >= timedelta(hours=48)
    assert proposed.tzinfo == UTC


def test_research_and_operations_routes_use_paginated_contract(client: TestClient) -> None:
    headers = api_token_headers()

    backtest = client.get("/v1/backtests/latest", headers=headers).json()
    decisions = client.get("/v1/decisions?limit=25", headers=headers).json()
    detail = client.get("/v1/decisions/decision-1", headers=headers).json()
    runs = client.get("/v1/runs?limit=10", headers=headers).json()
    providers = client.get("/v1/providers/health", headers=headers).json()
    health = client.get("/v1/system-health", headers=headers).json()

    assert backtest["report_type"] == "edge_backtest"
    assert decisions == {
        "items": [{"decision_id": "decision-1", "limit": 25, "cursor": None}],
        "next_cursor": None,
    }
    assert detail["decision"]["decision_id"] == "decision-1"
    assert runs["items"][0]["run_id"].startswith("nightly:")
    assert providers == {"providers": [], "recent_errors": []}
    assert health[0]["component"] == "database"


def test_authenticated_health_returns_repository_status(client: TestClient) -> None:
    response = client.get("/v1/health", headers=api_token_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
