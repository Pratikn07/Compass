"""Run the propose-only deterministic pipeline over curated seed inputs and write
the resulting decisions to storage.

Used as the Railway cron job body and via the `prescient seed-run` CLI. Claude-free,
no broker, propose-only — it can only propose and journal, never trade.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from prescient.scheduler import (
    ScheduledRunRequest,
    ScheduleTriggerType,
    run_scheduled_strategy_pipeline,
)
from prescient.seed.inputs import build_seed_inputs

# Earnings window the seed candidate must fall within (target reports day after run).
_WINDOW_DAYS = 14


@dataclass(frozen=True)
class SeedRunSummary:
    run_id: str
    decision_count: int
    wrote_storage: bool


def run_seed_pipeline(
    *,
    current_date: date,
    storage_writer: object | None = None,
    storage_write_policy: object = "required",
    env: Mapping[str, str] | None = None,
) -> SeedRunSummary:
    """Build seed inputs, run the real pipeline, write decisions to storage.

    storage_writer: injected for tests. When None, a SupabaseStorageAdapter is built
    from env (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY).
    """
    seed = build_seed_inputs(current_date=current_date)

    writer = storage_writer if storage_writer is not None else _supabase_writer(env)

    request = ScheduledRunRequest(
        run_id=f"{ScheduleTriggerType.SCHEDULED.value}:{current_date.isoformat()}",
        trigger_type=ScheduleTriggerType.SCHEDULED,
        scheduled_date=current_date,
        current_date=current_date,
        window_start=current_date,
        window_end=current_date + timedelta(days=_WINDOW_DAYS),
        relevant_tickers=[event.ticker for event in seed.upcoming_events],
    )

    result = run_scheduled_strategy_pipeline(
        request=request,
        universe=seed.universe,
        upcoming_events=seed.upcoming_events,
        peer_results=seed.peer_results,
        target_market_data=seed.target_market_data,
        options_chains=seed.options_chains,
        enable_claude_analysis=False,
        storage_writer=writer,
        storage_write_policy=storage_write_policy,
    )

    return SeedRunSummary(
        run_id=request.run_id,
        decision_count=result.summary.total_decision_count,
        wrote_storage=writer is not None,
    )


def _supabase_writer(env: Mapping[str, str] | None) -> object:
    from prescient.storage.supabase import SupabaseStorageAdapter

    active_env = env if env is not None else os.environ
    return SupabaseStorageAdapter.from_env(environ=active_env)
