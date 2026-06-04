from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from prescient.runtime.models import DecisionJournalRecord, DecisionJournalRecordType
from prescient.storage import StorageQuery, SupabaseStorageAdapter
from tests.support.supabase_test_env import (
    SupabaseIntegrationTestNotEnabled,
    load_supabase_integration_test_config,
)


def test_supabase_adapter_round_trips_against_configured_test_project() -> None:
    try:
        config = load_supabase_integration_test_config(os.environ)
    except SupabaseIntegrationTestNotEnabled as exc:
        pytest.skip(str(exc))

    from supabase import create_client

    client = create_client(config.url, config.service_role_key)
    adapter = SupabaseStorageAdapter(client=client, schema=config.schema)
    record_id = f"test_jrnl_{uuid4().hex}"
    run_id = f"test_run_{uuid4().hex}"
    record = DecisionJournalRecord(
        journal_record_id=record_id,
        record_type=DecisionJournalRecordType.STRATEGY_DECISION,
        run_id=run_id,
        decision_id=f"test_decision_{uuid4().hex}",
        decision_index=0,
        trading_date=date(2026, 6, 4),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
        target="NTNX",
        theme="AI_STORAGE",
        strategy_type="bullish_earnings_readthrough",
        strategy_status="candidate_ready_for_analyst",
        execution_mode="propose_only",
        source="tests.supabase.integration",
        payload={"test": True},
    )

    try:
        write_result = adapter.append_decision_journal_records([record])
        assert write_result.ok is True
        assert write_result.records_written == 1

        records = adapter.read_decision_journal_records(StorageQuery(run_id=run_id, limit=5))

        assert [stored.journal_record_id for stored in records] == [record_id]
        assert records[0].payload == {"test": True}
    finally:
        client.schema(config.schema).table("journal_records").delete().eq(
            "journal_record_id",
            record_id,
        ).execute()
