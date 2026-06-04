from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from prescient.runtime.models import DecisionJournalRecord
from prescient.storage.models import StorageQuery, StorageWriteResult


class JournalStorageWriter(Protocol):
    def append_decision_journal_records(
        self,
        records: Iterable[DecisionJournalRecord],
    ) -> StorageWriteResult:
        ...


class JournalStorageReader(Protocol):
    def read_decision_journal_records(
        self,
        query: StorageQuery | None = None,
    ) -> Sequence[DecisionJournalRecord]:
        ...


class ProviderSnapshotStorage(Protocol):
    def append_provider_snapshots(
        self,
        snapshots: Iterable[dict[str, object]],
    ) -> StorageWriteResult:
        ...


class LearningReportStorage(Protocol):
    def append_learning_reports(
        self,
        reports: Iterable[dict[str, object]],
    ) -> StorageWriteResult:
        ...
