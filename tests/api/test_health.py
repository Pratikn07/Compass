from __future__ import annotations

from fastapi.testclient import TestClient

from compass.api.dependencies import get_repository
from compass.api.main import app


class HealthRepository:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def ping(self) -> None:
        if self.error is not None:
            raise self.error


def client_for(repository: HealthRepository) -> TestClient:
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app)


def test_liveness_never_queries_the_database() -> None:
    response = client_for(HealthRepository(error=RuntimeError("database detail"))).get(
        "/v1/live"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_sanitized_503_when_database_is_unavailable() -> None:
    response = client_for(HealthRepository(error=RuntimeError("database detail"))).get(
        "/v1/ready"
    )

    assert response.status_code == 503
    assert response.json() == {"status": "unready", "database": "error"}
    assert "database detail" not in response.text


def test_readiness_reports_ready_after_database_ping() -> None:
    response = client_for(HealthRepository()).get("/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}

