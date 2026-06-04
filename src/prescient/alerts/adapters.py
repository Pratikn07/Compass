from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any, Callable

import httpx

from prescient.alerts.formatter import PlainTextAlertFormatter
from prescient.alerts.models import (
    AlertChannelType,
    AlertDeliveryResult,
    AlertDeliveryStatus,
    AlertError,
    AlertErrorType,
    AlertEvent,
    AlertProvider,
    AlertRecipient,
    error_from_exception,
    now_utc,
)


TELEGRAM_MAX_MESSAGE_CHARS = 4096
DISCORD_MAX_MESSAGE_CHARS = 2000


class TelegramAlertAdapter:
    def __init__(
        self,
        *,
        bot_token: str,
        http_client: Any | None = None,
        timeout: float = 10.0,
        formatter: PlainTextAlertFormatter | None = None,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.http_client = http_client or httpx.Client()
        self.timeout = timeout
        self.formatter = formatter or PlainTextAlertFormatter()

    def send(self, event: AlertEvent, recipient: AlertRecipient) -> AlertDeliveryResult:
        if not self.bot_token or not recipient.destination.strip():
            return _failed(
                event,
                recipient,
                AlertProvider.TELEGRAM,
                AlertErrorType.MISSING_CREDENTIALS,
                "Missing Telegram alert configuration.",
            )

        text = self.formatter.format_text(event)
        if len(text) > TELEGRAM_MAX_MESSAGE_CHARS:
            return _failed(
                event,
                recipient,
                AlertProvider.TELEGRAM,
                AlertErrorType.MESSAGE_TOO_LONG,
                "Telegram alert message exceeds provider limit.",
            )

        try:
            response = self.http_client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": recipient.destination, "text": text},
                timeout=self.timeout,
            )
            return _http_result(
                event=event,
                recipient=recipient,
                provider=AlertProvider.TELEGRAM,
                response=response,
                message_id_getter=_telegram_message_id,
            )
        except Exception as exc:
            return _failed_with_error(
                event,
                recipient,
                error_from_exception(
                    provider=AlertProvider.TELEGRAM,
                    exc=exc,
                    source="telegram",
                ),
            )


class DiscordAlertAdapter:
    def __init__(
        self,
        *,
        webhook_url: str | None = None,
        http_client: Any | None = None,
        timeout: float = 10.0,
        formatter: PlainTextAlertFormatter | None = None,
    ) -> None:
        self.webhook_url = (webhook_url or "").strip()
        self.http_client = http_client or httpx.Client()
        self.timeout = timeout
        self.formatter = formatter or PlainTextAlertFormatter()

    def send(self, event: AlertEvent, recipient: AlertRecipient) -> AlertDeliveryResult:
        webhook_url = recipient.destination.strip() or self.webhook_url
        if not webhook_url:
            return _failed(
                event,
                recipient,
                AlertProvider.DISCORD,
                AlertErrorType.MISSING_CREDENTIALS,
                "Missing Discord alert configuration.",
            )

        text = self.formatter.format_text(event)
        if len(text) > DISCORD_MAX_MESSAGE_CHARS:
            return _failed(
                event,
                recipient,
                AlertProvider.DISCORD,
                AlertErrorType.MESSAGE_TOO_LONG,
                "Discord alert message exceeds provider limit.",
            )

        try:
            response = self.http_client.post(
                webhook_url,
                json={"content": text},
                timeout=self.timeout,
            )
            return _http_result(
                event=event,
                recipient=recipient,
                provider=AlertProvider.DISCORD,
                response=response,
                message_id_getter=_discord_message_id,
            )
        except Exception as exc:
            return _failed_with_error(
                event,
                recipient,
                error_from_exception(
                    provider=AlertProvider.DISCORD,
                    exc=exc,
                    source="discord",
                ),
            )


class SmtpEmailAlertAdapter:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_address: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 10.0,
        smtp_factory: Callable[[str, int, float], Any] | None = None,
        formatter: PlainTextAlertFormatter | None = None,
    ) -> None:
        self.host = host.strip()
        self.port = port
        self.from_address = from_address.strip()
        self.username = (username or "").strip()
        self.password = password or ""
        self.use_tls = use_tls
        self.timeout = timeout
        self.smtp_factory = smtp_factory or _smtp_factory
        self.formatter = formatter or PlainTextAlertFormatter()

    def send(self, event: AlertEvent, recipient: AlertRecipient) -> AlertDeliveryResult:
        to_address = recipient.destination.strip()
        if not self.host or not self.from_address or not to_address:
            return _failed(
                event,
                recipient,
                AlertProvider.EMAIL,
                AlertErrorType.MISSING_CREDENTIALS,
                "Missing email alert configuration.",
            )

        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = to_address
        message["Subject"] = self.formatter.format_email_subject(event)
        message.set_content(self.formatter.format_text(event))

        try:
            with self.smtp_factory(self.host, self.port, self.timeout) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
        except Exception as exc:
            return _failed_with_error(
                event,
                recipient,
                error_from_exception(
                    provider=AlertProvider.EMAIL,
                    exc=exc,
                    source="smtp",
                ),
            )

        return AlertDeliveryResult(
            alert_id=event.alert_id,
            provider=AlertProvider.EMAIL,
            channel_type=AlertChannelType.EMAIL,
            destination_label=recipient.destination_label,
            status=AlertDeliveryStatus.SENT,
            sent_at=now_utc(),
        )


def _http_result(
    *,
    event: AlertEvent,
    recipient: AlertRecipient,
    provider: AlertProvider,
    response: Any,
    message_id_getter: Callable[[Any], str | None],
) -> AlertDeliveryResult:
    status_code = int(getattr(response, "status_code", 0))
    if 200 <= status_code < 300:
        return AlertDeliveryResult(
            alert_id=event.alert_id,
            provider=provider,
            channel_type=recipient.channel_type,
            destination_label=recipient.destination_label,
            status=AlertDeliveryStatus.SENT,
            sent_at=now_utc(),
            provider_message_id=message_id_getter(response),
        )

    return _failed_with_error(
        event,
        recipient,
        AlertError(
            provider=provider,
            error_type=_http_error_type(status_code),
            message=f"{status_code} provider response failed.",
            retryable=status_code in {408, 429, 500, 502, 503, 504},
            source=provider.value,
        ),
    )


def _failed(
    event: AlertEvent,
    recipient: AlertRecipient,
    provider: AlertProvider,
    error_type: AlertErrorType,
    message: str,
) -> AlertDeliveryResult:
    return _failed_with_error(
        event,
        recipient,
        AlertError(
            provider=provider,
            error_type=error_type,
            message=message,
            retryable=error_type
            in {
                AlertErrorType.RATE_LIMITED,
                AlertErrorType.TIMEOUT,
                AlertErrorType.NETWORK_UNAVAILABLE,
            },
            source=provider.value,
        ),
    )


def _failed_with_error(
    event: AlertEvent,
    recipient: AlertRecipient,
    error: AlertError,
) -> AlertDeliveryResult:
    return AlertDeliveryResult(
        alert_id=event.alert_id,
        provider=error.provider,
        channel_type=recipient.channel_type,
        destination_label=recipient.destination_label,
        status=AlertDeliveryStatus.FAILED,
        errors=[error],
    )


def _http_error_type(status_code: int) -> AlertErrorType:
    if status_code == 401:
        return AlertErrorType.UNAUTHORIZED
    if status_code == 403:
        return AlertErrorType.FORBIDDEN
    if status_code == 429:
        return AlertErrorType.RATE_LIMITED
    if status_code == 408:
        return AlertErrorType.TIMEOUT
    if status_code == 404:
        return AlertErrorType.RECIPIENT_UNAVAILABLE
    return AlertErrorType.UNKNOWN


def _telegram_message_id(response: Any) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None
    result = payload.get("result")
    if isinstance(result, dict) and result.get("message_id") is not None:
        return str(result["message_id"])
    return None


def _discord_message_id(response: Any) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None
    message_id = payload.get("id") if isinstance(payload, dict) else None
    return str(message_id) if message_id is not None else None


def _smtp_factory(host: str, port: int, timeout: float) -> smtplib.SMTP:
    return smtplib.SMTP(host=host, port=port, timeout=timeout)
