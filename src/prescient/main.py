from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date

from prescient.safety import (
    KillSwitchActivationSource,
    activate_kill_switch,
    get_kill_switch_state,
    reset_kill_switch,
)
from prescient.scheduler import CronRunRequest, run_cron_guarded_job


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "kill-switch":
        if args.command == "scheduler":
            return _handle_scheduler_command(args)
        if args.command == "seed-run":
            return _handle_seed_run_command(args)
        parser.print_help()
        return 2

    if args.kill_switch_command == "status":
        state = get_kill_switch_state(path=args.path)
        print(f"status: {state.status.value}")
        if state.reason:
            print(f"reason: {state.reason}")
        if state.activated_by:
            print(f"actor: {state.activated_by}")
        return 0

    if args.kill_switch_command == "activate":
        result = activate_kill_switch(
            reason=args.reason,
            actor=args.actor,
            source=KillSwitchActivationSource.CLI,
            cancel_open_orders=args.cancel_open_orders,
            path=args.path,
        )
        print(f"kill switch {result.state.status.value}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        return 0

    if args.kill_switch_command == "reset":
        state = reset_kill_switch(
            reason=args.reason,
            actor=args.actor,
            source=KillSwitchActivationSource.CLI,
            path=args.path,
        )
        print(f"kill switch {state.status.value}")
        return 0

    parser.print_help()
    return 2


def _handle_scheduler_command(args: argparse.Namespace) -> int:
    if args.scheduler_command != "cron-guard":
        return 2

    request = CronRunRequest(
        job_name=args.job_name,
        run_key=args.run_key,
        scheduled_for=date.fromisoformat(args.scheduled_for),
        database_path=args.database_path,
        execution_mode=args.execution_mode,
    )
    result = run_cron_guarded_job(request, lambda: 0)
    print(f"{args.command_label}: {result.status.value}")
    print(f"message: {result.message}")
    return result.exit_code


def _handle_seed_run_command(args: argparse.Namespace) -> int:
    from prescient.seed import run_seed_pipeline

    current_date = (
        date.fromisoformat(args.current_date)
        if args.current_date
        else date.today()
    )
    summary = run_seed_pipeline(
        current_date=current_date,
        storage_write_policy=args.storage_write_policy,
    )
    print(f"seed-run: {summary.run_id}")
    print(f"decisions: {summary.decision_count}")
    print(f"wrote_storage: {summary.wrote_storage}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prescient")
    subparsers = parser.add_subparsers(dest="command", required=True)

    kill_switch = subparsers.add_parser(
        "kill-switch",
        help="Manage the local broker kill switch.",
    )
    kill_switch_subparsers = kill_switch.add_subparsers(
        dest="kill_switch_command",
        required=True,
    )

    activate = kill_switch_subparsers.add_parser(
        "activate",
        help="Activate the kill switch.",
    )
    activate.add_argument("--reason", required=True)
    activate.add_argument("--actor", required=True)
    activate.add_argument("--cancel-open-orders", action="store_true")
    activate.add_argument("--path", default=None)

    status = kill_switch_subparsers.add_parser(
        "status",
        help="Show kill switch state.",
    )
    status.add_argument("--path", default=None)

    reset = kill_switch_subparsers.add_parser(
        "reset",
        help="Reset the kill switch to inactive.",
    )
    reset.add_argument("--reason", required=True)
    reset.add_argument("--actor", required=True)
    reset.add_argument("--path", default=None)

    scheduler = subparsers.add_parser(
        "scheduler",
        help="Manage bounded scheduled job helpers.",
    )
    scheduler_subparsers = scheduler.add_subparsers(
        dest="scheduler_command",
        required=True,
    )

    cron_guard = scheduler_subparsers.add_parser(
        "cron-guard",
        help="Record a bounded cron guard run.",
    )
    cron_guard.add_argument("--job-name", required=True)
    cron_guard.add_argument("--run-key", required=True)
    cron_guard.add_argument("--scheduled-for", required=True)
    cron_guard.add_argument("--database-path", required=True)
    cron_guard.add_argument("--command-label", required=True)
    cron_guard.add_argument("--execution-mode", default="propose_only")

    seed_run = subparsers.add_parser(
        "seed-run",
        help="Run the propose-only pipeline over curated seed inputs and store results.",
    )
    seed_run.add_argument(
        "--current-date",
        default=None,
        help="ISO date for the run (defaults to today).",
    )
    seed_run.add_argument("--storage-write-policy", default="required")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
