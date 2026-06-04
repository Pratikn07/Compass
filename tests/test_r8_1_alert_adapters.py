from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from prescient.alerts import (
    AlertChannelType,
    AlertDeliveryStatus,
    AlertErrorType,
    AlertEvent,
    AlertEventType,
    AlertProvider,
    AlertRecipient,
    AlertSeverity,
    DiscordAlertAdapter,
    SmtpEmailAlertAdapter,
    TelegramAlertAdapter,
)


def _event(summary: str = "Bullish setup detected.") -> AlertEvent:
    return AlertEvent(
        alert_id="alert-1",
        event_type=AlertEventType.SETUP_DETECTED,
        severity=AlertSeverity.INFO,
        run_id="run-1",
        decision_id="decision-1",
        journal_record_id="journal-1",
        target="NTNX",
        theme="AI_STORAGE",
        strategy_type="bullish_earnings_readthrough",
        execution_mode="paper",
        title="Setup detected",
        summary=summary,
        created_at=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
    )


def test_telegram_adapter_sends_send_message_payload_with_fake_http_client() -> None:
    client = FakeHttpClient(FakeResponse(200, {"ok": True, "result": {"message_id": 123}}))
    adapter = TelegramAlertAdapter(bot_token="bot-token", http_client=client)
    recipient = AlertRecipient(
        channel_type=AlertChannelType.TELEGRAM,
        provider=AlertProvider.TELEGRAM,
        destination_label="ops",
        destination="chat-1",
    )

    result = adapter.send(_event(), recipient)

    assert result.status == AlertDeliveryStatus.SENT
    assert result.provider_message_id == "123"
    assert client.calls[0]["url"] == "https://api.telegram.org/botbot-token/sendMessage"
    assert client.calls[0]["json"]["chat_id"] == "chat-1"
    assert "NTNX" in client.calls[0]["json"]["text"]


def test_discord_adapter_sends_webhook_payload_without_leaking_webhook_on_error() -> None:
    client = FakeHttpClient(FakeResponse(401, {"message": "bad webhook secret token"}))
    adapter = DiscordAlertAdapter(http_client=client)
    recipient = AlertRecipient(
        channel_type=AlertChannelType.DISCORD,
        provider=AlertProvider.DISCORD,
        destination_label="ops",
        destination="https://discord.test/webhook-secret",
    )

    result = adapter.send(_event(), recipient)

    assert result.status == AlertDeliveryStatus.FAILED
    assert result.errors[0].error_type == AlertErrorType.UNAUTHORIZED
    assert "webhook-secret" not in result.model_dump_json()


def test_smtp_email_adapter_sends_subject_and_body_through_fake_smtp() -> None:
    smtp = FakeSmtp()
    adapter = SmtpEmailAlertAdapter(
        host="smtp.test",
        port=587,
        from_address="alerts@example.test",
        username="user",
        password="password",
        smtp_factory=lambda host, port, timeout: smtp,
    )
    recipient = AlertRecipient(
        channel_type=AlertChannelType.EMAIL,
        provider=AlertProvider.EMAIL,
        destination_label="ops-email",
        destination="ops@example.test",
    )

    result = adapter.send(_event(), recipient)

    assert result.status == AlertDeliveryStatus.SENT
    assert smtp.started_tls is True
    assert smtp.login_args == ("user", "password")
    assert isinstance(smtp.messages[0], EmailMessage)
    assert smtp.messages[0]["To"] == "ops@example.test"
    assert "SETUP_DETECTED NTNX paper" in smtp.messages[0]["Subject"]


def test_adapters_return_missing_credentials_and_message_too_long_errors() -> None:
    telegram = TelegramAlertAdapter(bot_token="")
    recipient = AlertRecipient(
        channel_type=AlertChannelType.TELEGRAM,
        provider=AlertProvider.TELEGRAM,
        destination_label="ops",
        destination="chat-1",
    )

    missing = telegram.send(_event(), recipient)
    too_long = TelegramAlertAdapter(bot_token="token").send(
        _event("x" * 5000),
        recipient,
    )

    assert missing.errors[0].error_type == AlertErrorType.MISSING_CREDENTIALS
    assert too_long.errors[0].error_type == AlertErrorType.MESSAGE_TOO_LONG


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self.response


class FakeSmtp:
    def __init__(self) -> None:
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages: list[EmailMessage] = []

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)

