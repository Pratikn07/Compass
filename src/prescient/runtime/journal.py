from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from prescient.runtime.models import DecisionJournalRecord, PipelineJournalEvent
from prescient.storage.jsonl import JsonlStorageAdapter
from prescient.storage.models import StorageQuery


def append_pipeline_journal(
    events: Iterable[PipelineJournalEvent],
    path: str | Path,
) -> None:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    with journal_path.open("a", encoding="utf-8") as journal_file:
        for event in events:
            journal_file.write(event.model_dump_json())
            journal_file.write("\n")


def append_decision_journal_records(
    records: Iterable[DecisionJournalRecord],
    path: str | Path,
) -> None:
    JsonlStorageAdapter(path).append_decision_journal_records(records)


def read_decision_journal_records(
    path: str | Path,
    *,
    run_id: str | None = None,
    decision_id: str | None = None,
) -> Sequence[DecisionJournalRecord]:
    return JsonlStorageAdapter(path).read_decision_journal_records(
        StorageQuery(run_id=run_id, decision_id=decision_id)
    )
