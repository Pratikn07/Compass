from __future__ import annotations

from datetime import date
from typing import Any

from prescient.backtest.models import BacktestRunResult
from prescient.storage.models import DEFAULT_STORAGE_SCHEMA_VERSION

BACKTEST_LEARNING_REPORT_TYPE = "backtest"


def backtest_result_to_learning_report_row(
    result: BacktestRunResult,
    report_date: date,
    target: str | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    return {
        "learning_report_id": f"{BACKTEST_LEARNING_REPORT_TYPE}:{result.run_id}",
        "run_id": result.run_id,
        "report_date": report_date.isoformat(),
        "target": _normalize_optional_uppercase(target),
        "theme": _normalize_optional_uppercase(theme),
        "report_type": BACKTEST_LEARNING_REPORT_TYPE,
        "payload": result.model_dump(mode="json"),
        "schema_version": DEFAULT_STORAGE_SCHEMA_VERSION,
    }


def _normalize_optional_uppercase(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned.upper() if cleaned else None
