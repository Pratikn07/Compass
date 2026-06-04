from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from prescient.runtime.models import DecisionJournalRecord
from prescient.storage.models import StorageQuery, StorageWriteResult


class JsonlStorageAdapter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append_decision_journal_records(
        self,
        records: Iterable[DecisionJournalRecord],
    ) -> StorageWriteResult:
        batch = list(records)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("a", encoding="utf-8") as journal_file:
            for record in batch:
                journal_file.write(record.model_dump_json())
                journal_file.write("\n")

        return StorageWriteResult(records_written=len(batch))

    def read_decision_journal_records(
        self,
        query: StorageQuery | None = None,
    ) -> Sequence[DecisionJournalRecord]:
        active_query = query or StorageQuery()
        records: list[DecisionJournalRecord] = []
        if not self.path.exists():
            return records

        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = DecisionJournalRecord.model_validate(json.loads(line))
            if not _matches_query(record, active_query):
                continue
            records.append(record)

        return records


def _matches_query(record: DecisionJournalRecord, query: StorageQuery) -> bool:
    if query.run_id is not None and record.run_id != query.run_id:
        return False
    if query.decision_id is not None and record.decision_id != query.decision_id:
        return False
    if query.target is not None and record.target != query.target:
        return False
    if query.theme is not None and record.theme != query.theme:
        return False
    if query.record_type is not None and record.record_type.value != query.record_type:
        return False
    if query.from_date is not None and record.trading_date < query.from_date:
        return False
    if query.to_date is not None and record.trading_date > query.to_date:
        return False
    return True
