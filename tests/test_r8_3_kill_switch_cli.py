from __future__ import annotations

from pathlib import Path

from prescient.main import main
from prescient.safety import FileKillSwitchProvider, KillSwitchStatus


def test_cli_activate_status_and_reset(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "kill-switch.json"

    activate_code = main(
        [
            "kill-switch",
            "activate",
            "--reason",
            "unexpected live activity",
            "--actor",
            "operator",
            "--path",
            str(state_path),
        ]
    )
    assert activate_code == 0
    assert "active" in capsys.readouterr().out.lower()
    assert FileKillSwitchProvider(path=state_path, env={}).read_state().status == (
        KillSwitchStatus.ACTIVE
    )

    status_code = main(["kill-switch", "status", "--path", str(state_path)])
    assert status_code == 0
    assert "active" in capsys.readouterr().out.lower()

    reset_code = main(
        [
            "kill-switch",
            "reset",
            "--reason",
            "manual review complete",
            "--actor",
            "operator",
            "--path",
            str(state_path),
        ]
    )
    assert reset_code == 0
    assert "inactive" in capsys.readouterr().out.lower()


def test_cli_cancel_open_orders_without_broker_succeeds_with_message(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "kill-switch.json"

    exit_code = main(
        [
            "kill-switch",
            "activate",
            "--reason",
            "stop",
            "--actor",
            "operator",
            "--cancel-open-orders",
            "--path",
            str(state_path),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out.lower()
    assert "active" in output
    assert "requires broker context" in output

