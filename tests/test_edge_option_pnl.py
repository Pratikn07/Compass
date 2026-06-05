from __future__ import annotations

import pytest


def test_correct_direction_small_move_still_loses_to_iv_crush() -> None:
    # bought call for 4.00, strike 100, stock rose only to 103 (+3%, under implied 8%)
    from prescient.edge.option_pnl import simulate_option_pnl

    pnl = simulate_option_pnl(
        direction="UP",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=103.0,
        cost_haircut_pct=0.05,
    )
    assert pnl is not None
    # intrinsic 3.0, minus 4.0 premium, minus 0.2 haircut = -1.2
    assert pnl.net_pnl == pytest.approx(-1.2)
    assert pnl.return_pct == pytest.approx(-30.0)


def test_big_move_wins() -> None:
    from prescient.edge.option_pnl import simulate_option_pnl

    pnl = simulate_option_pnl(
        direction="UP",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=110.0,
        cost_haircut_pct=0.05,
    )
    assert pnl is not None
    # intrinsic 10.0 - 4.0 - 0.2 = 5.8
    assert pnl.net_pnl == pytest.approx(5.8)
    assert pnl.return_pct == pytest.approx(145.0)


def test_put_intrinsic_and_total_loss_floor() -> None:
    from prescient.edge.option_pnl import simulate_option_pnl

    # PUT, stock went UP so put expires worthless: lose premium + haircut, floored at -100%
    pnl = simulate_option_pnl(
        direction="DOWN",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=110.0,
        cost_haircut_pct=0.05,
    )
    assert pnl is not None
    assert pnl.exit_value == pytest.approx(0.0)
    assert pnl.return_pct == pytest.approx(-100.0)


def test_none_direction_returns_none() -> None:
    from prescient.edge.option_pnl import simulate_option_pnl

    assert simulate_option_pnl(
        direction="NONE",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=110.0,
        cost_haircut_pct=0.05,
    ) is None
