from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prescient.learning.models import (
    LearningJournalReadResult,
    LearningJournalRecord,
    LearningRecordType,
)


class LocalJsonlLearningJournalReader:
    """Read local JSONL journals into normalized learning records."""

    def read_records(
        self,
        *,
        start_date: date,
        end_date: date,
        paths: Sequence[str],
    ) -> LearningJournalReadResult:
        records: list[LearningJournalRecord] = []
        records_skipped = 0
        malformed_record_count = 0
        warnings: list[str] = []

        for raw_path in paths:
            path = Path(raw_path)
            if not path.exists():
                records_skipped += 1
                warnings.append(f"missing journal file: {path}")
                continue

            with path.open("r", encoding="utf-8") as journal_file:
                for line_number, line in enumerate(journal_file, start=1):
                    if not line.strip():
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        malformed_record_count += 1
                        records_skipped += 1
                        warnings.append(
                            f"malformed journal line skipped at {path.name}:{line_number}"
                        )
                        continue

                    try:
                        record = _normalize_record(payload)
                    except (TypeError, ValueError, ValidationError):
                        malformed_record_count += 1
                        records_skipped += 1
                        warnings.append(
                            f"invalid journal record skipped at {path.name}:{line_number}"
                        )
                        continue

                    if record is None:
                        records_skipped += 1
                        continue

                    if (
                        record.trading_date is not None
                        and not start_date <= record.trading_date <= end_date
                    ):
                        records_skipped += 1
                        continue

                    records.append(record)

        return LearningJournalReadResult(
            records=records,
            records_read=len(records),
            records_skipped=records_skipped,
            malformed_record_count=malformed_record_count,
            warnings=warnings,
        )


def _normalize_record(payload: Any) -> LearningJournalRecord | None:
    if not isinstance(payload, dict):
        raise TypeError("Journal payload must be an object.")

    if "record_type" in payload:
        return LearningJournalRecord.model_validate(payload)

    if "event_type" in payload:
        return _normalize_pipeline_event(payload)

    return None


def _normalize_pipeline_event(payload: dict[str, Any]) -> LearningJournalRecord | None:
    if payload.get("event_type") != "hot_path_decision":
        return None

    strategy_decision = payload.get("strategy_decision")
    if not isinstance(strategy_decision, dict):
        strategy_decision = {}

    decision_payload: dict[str, Any] = {
        "strategy_status": payload.get("strategy_status")
        or strategy_decision.get("status"),
    }

    audit = strategy_decision.get("audit")
    if isinstance(audit, dict):
        thresholds = audit.get("thresholds")
        if isinstance(thresholds, dict):
            decision_payload["thresholds"] = thresholds

    candidate = strategy_decision.get("candidate")
    if isinstance(candidate, dict):
        peer_signal = candidate.get("peer_signal")
        if isinstance(peer_signal, dict):
            decision_payload["peer_signal"] = peer_signal

    decision_index = payload.get("decision_index")
    decision_id = None if decision_index is None else f"pipeline-decision-{decision_index}"

    return LearningJournalRecord(
        record_type=LearningRecordType.STRATEGY_DECISION,
        run_id=payload.get("run_id"),
        decision_id=decision_id,
        trading_date=None,
        target=payload.get("target"),
        theme=payload.get("theme"),
        strategy_type=strategy_decision.get("strategy_type"),
        payload=decision_payload,
    )
