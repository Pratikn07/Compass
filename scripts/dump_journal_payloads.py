"""Dump real engine journal-record payloads to JSON for frontend parser verification.

Reuses the acceptance-test fixtures to produce a genuine bullish candidate via the
deterministic engine, then builds the strategy-decision journal record exactly as
the runtime does, and serializes the payloads the frontend must parse.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Load the acceptance test module to reuse its fixture builders.
spec = importlib.util.spec_from_file_location(
    "accept", ROOT / "tests" / "test_core_strategy_acceptance.py"
)
accept = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accept)

from prescient.signal.core import evaluate_core_strategy  # noqa: E402
from prescient.runtime.decision_journal import (  # noqa: E402
    build_strategy_decision_record,
)


def _build_strategy_decision():
    # Mirror the passing acceptance test that yields a bullish candidate.
    fn = accept.test_five_ai_storage_peers_with_four_strong_results_create_bullish_candidate
    # The test calls evaluate_core_strategy with fixtures; re-run that call here.
    # We reconstruct the same inputs the test uses by calling the fixture helpers.
    import inspect

    src = inspect.getsource(fn)
    # The test builds inputs inline; simplest path: call the engine with the same
    # helper inputs the module exposes.
    universe = accept._universe()
    # Find the other fixture helpers the test uses by introspection.
    return universe, src


def main() -> None:
    universe = accept._universe()
    # Reproduce the acceptance call signature by reading what helpers exist.
    helpers = [n for n in dir(accept) if n.startswith("_")]
    print("# available fixture helpers:", helpers, file=sys.stderr)

    # Run the canonical bullish scenario via the test function's own body by
    # calling it (it asserts internally; we just want the side data). Instead,
    # call evaluate_core_strategy with the documented fixture helpers.
    decisions = _run_bullish(accept, universe)

    from datetime import date

    out = {}
    for decision in decisions:
        record = build_strategy_decision_record(
            run_id="e2e:verify",
            decision=decision,
            decision_index=0,
            trading_date=date(2025, 5, 14),
            settings=_settings(),
            execution_mode="propose_only",
        )
        out[record.target or "decision"] = {
            "record_type": record.record_type.value,
            "payload": json.loads(
                json.dumps(record.payload, default=str)
            ),
        }
        break

    print(json.dumps(out, default=str, indent=2))


def _settings():
    from prescient.signal.models import StrategySettings

    return StrategySettings()


def _run_bullish(accept_mod, universe):
    # Re-derive the inputs from the acceptance test's bullish test by executing
    # its body with a captured evaluate_core_strategy.
    captured = {}
    real = evaluate_core_strategy

    def spy(*args, **kwargs):
        result = real(*args, **kwargs)
        captured["decisions"] = result
        return result

    accept_mod.evaluate_core_strategy = spy
    try:
        accept_mod.test_five_ai_storage_peers_with_four_strong_results_create_bullish_candidate()
    finally:
        accept_mod.evaluate_core_strategy = real
    return captured.get("decisions", [])


if __name__ == "__main__":
    main()
