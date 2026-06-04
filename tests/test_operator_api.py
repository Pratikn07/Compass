from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from prescient.operator.api import create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        token="test-token",
        mode_path=tmp_path / "execution-mode.json",
        kill_switch_path=tmp_path / "kill-switch.json",
        env={},
    )
    return TestClient(app)


def test_status_requires_bearer_token(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/status")

    assert response.status_code == 401


def test_status_returns_operator_state(tmp_path: Path) -> None:
    response = _client(tmp_path).get(
        "/status",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "propose_only"
    assert payload["kill_switch"]["status"] == "inactive"


def test_mode_authorization_uses_server_token_and_actor_from_payload(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/mode-authorization",
        headers={"Authorization": "Bearer test-token"},
        json={
            "requested_mode": "paper",
            "actor": "operator@example.com",
            "reason": "paper validation",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["active_mode"] == "paper"


def test_live_mode_is_rejected_by_default(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/mode-authorization",
        headers={"Authorization": "Bearer test-token"},
        json={
            "requested_mode": "live",
            "actor": "operator@example.com",
            "reason": "try live",
            "confirmation_text": "AUTHORIZE LIVE TRADING",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert "live_mode_disabled" in payload["rejection_reasons"]
