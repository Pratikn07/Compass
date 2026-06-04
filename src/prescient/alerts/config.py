from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from prescient.alerts.adapters import DiscordAlertAdapter, SmtpEmailAlertAdapter, TelegramAlertAdapter
from prescient.alerts.dispatcher import AlertDispatcher
from prescient.alerts.models import AlertChannelType, AlertProvider, AlertRecipient


class AlertRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    dry_run: bool = False
    recipients: list[AlertRecipient] = Field(default_factory=list)


def load_alert_config_from_env(
    environ: Mapping[str, str] | None = None,
) -> AlertRuntimeConfig:
    env = environ if environ is not None else os.environ
    enabled = _truthy(env.get("ALERTS_ENABLED", "false"))
    dry_run = _truthy(env.get("ALERTS_DRY_RUN", "false"))
    recipients: list[AlertRecipient] = []

    telegram_chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()
    if telegram_chat_id:
        recipients.append(
            AlertRecipient(
                channel_type=AlertChannelType.TELEGRAM,
                provider=AlertProvider.TELEGRAM,
                destination_label="telegram",
                destination=telegram_chat_id,
            )
        )

    discord_webhook = env.get("DISCORD_WEBHOOK_URL", "").strip()
    if discord_webhook:
        recipients.append(
            AlertRecipient(
                channel_type=AlertChannelType.DISCORD,
                provider=AlertProvider.DISCORD,
                destination_label="discord",
                destination=discord_webhook,
            )
        )

    email_to = env.get("ALERT_EMAIL_TO", "").strip()
    if email_to:
        recipients.append(
            AlertRecipient(
                channel_type=AlertChannelType.EMAIL,
                provider=AlertProvider.EMAIL,
                destination_label="email",
                destination=email_to,
            )
        )

    return AlertRuntimeConfig(enabled=enabled, dry_run=dry_run, recipients=recipients)


def build_alert_dispatcher_from_env(
    environ: Mapping[str, str] | None = None,
) -> AlertDispatcher:
    env = environ if environ is not None else os.environ
    smtp_port = int(env.get("ALERT_EMAIL_SMTP_PORT", "587") or "587")
    return AlertDispatcher(
        adapters={
            AlertProvider.TELEGRAM: TelegramAlertAdapter(
                bot_token=env.get("TELEGRAM_BOT_TOKEN", ""),
            ),
            AlertProvider.DISCORD: DiscordAlertAdapter(
                webhook_url=env.get("DISCORD_WEBHOOK_URL", ""),
            ),
            AlertProvider.EMAIL: SmtpEmailAlertAdapter(
                host=env.get("ALERT_EMAIL_SMTP_HOST", ""),
                port=smtp_port,
                username=env.get("ALERT_EMAIL_USERNAME", ""),
                password=env.get("ALERT_EMAIL_PASSWORD", ""),
                from_address=env.get("ALERT_EMAIL_FROM", ""),
            ),
        }
    )


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

