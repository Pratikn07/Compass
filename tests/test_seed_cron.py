from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from prescient.seed.inputs import build_seed_inputs
from prescient.signal.core import evaluate_core_strategy
from prescient.signal.models import StrategyStatus


def test_build_seed_inputs_yields_a_proposed_decision() -> None:
    """The seed must produce a real, non-rejected candidate the dashboard renders."""
    seed = build_seed_inputs(current_date=date(2026, 6, 1))

    decisions = evaluate_core_strategy(
        universe=seed.universe,
        upcoming_events=seed.upcoming_events,
        peer_results=seed.peer_results,
        target_market_data=seed.target_market_data,
        options_chains=seed.options_chains,
        current_date=seed.current_date,
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.candidate is not None
    assert decision.candidate.target == "NTNX"
    assert decision.candidate.theme == "AI_STORAGE"
    assert decision.candidate.direction == "bullish"


def test_build_seed_inputs_is_deterministic() -> None:
    a = build_seed_inputs(current_date=date(2026, 6, 1))
    b = build_seed_inputs(current_date=date(2026, 6, 1))
    assert a.universe == b.universe
    assert a.upcoming_events == b.upcoming_events
    assert a.peer_results == b.peer_results


# --- run_seed_pipeline orchestration (fake storage writer) -----------------

from prescient.seed.run import run_seed_pipeline  # noqa: E402


class _FakeStorageWriter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.appended_batches: list[list[Any]] = []

    def append_decision_journal_records(self, records: Any) -> Any:
        batch = list(records)
        self.appended_batches.append(batch)

        class _Result:
            def __init__(self, n: int, errors: list[Any]) -> None:
                self.records_written = n
                self.errors = errors

            def raise_if_required(self) -> None:
                if self.errors:
                    raise RuntimeError("storage write failed (required policy)")

        if self.fail:
            return _Result(0, [object()])
        return _Result(len(batch), [])


def test_run_seed_pipeline_writes_decisions_to_storage() -> None:
    writer = _FakeStorageWriter()
    summary = run_seed_pipeline(
        current_date=date(2026, 6, 1),
        storage_writer=writer,
    )

    assert summary.decision_count >= 1
    assert summary.wrote_storage is True
    # at least one journal batch with records was appended
    assert any(len(batch) > 0 for batch in writer.appended_batches)
    assert summary.run_id == "scheduled:2026-06-01"


def test_run_seed_pipeline_raises_when_required_write_fails() -> None:
    writer = _FakeStorageWriter(fail=True)
    with pytest.raises(Exception):
        run_seed_pipeline(
            current_date=date(2026, 6, 1),
            storage_writer=writer,
            storage_write_policy="required",
        )
