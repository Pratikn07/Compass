from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


UNSAFE_CLAUDE_KEYS = {
    "account_allocation",
    "broker_action",
    "contracts",
    "execute_trade",
    "notional",
    "order_quantity",
    "portfolio_allocation",
    "position_size",
    "quantity",
    "risk_override",
    "shares",
}


def contains_unsafe_claude_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in UNSAFE_CLAUDE_KEYS
            or contains_unsafe_claude_key(item)
            for key, item in value.items()
        )

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return any(contains_unsafe_claude_key(item) for item in value)

    return False
