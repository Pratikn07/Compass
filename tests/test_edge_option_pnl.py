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


def test_capped_short_small_move_keeps_credit_minus_wings() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # straddle credit 8.0, stock moved $2 (strike 100 -> 102), W=5, haircut 0.
    # wing_cost = 8 * (8 / (2*5)) = 8*0.8 = 6.4. payout owed = |102-100| = 2.0.
    # net = 8 - 6.4 - 2.0 = -0.4 -> small loss, NOT floored (within -5).
    pnl = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=102.0, risk_width=5.0, cost_haircut_pct=0.0,
    )
    assert pnl is not None
    assert pnl.entry_premium == 8.0
    assert round(pnl.net_pnl, 2) == -0.4
    # return measured on W (5.0): -0.4 / 5 * 100 = -8%
    assert round(pnl.return_pct, 1) == -8.0


def test_capped_short_tiny_move_is_profitable() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # credit 8, stock barely moved ($0.5). wing 6.4, payout 0.5 -> net 1.1 WIN.
    pnl = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=100.5, risk_width=5.0, cost_haircut_pct=0.0,
    )
    assert pnl is not None
    assert round(pnl.net_pnl, 2) == 1.1
    assert pnl.net_pnl > 0


def test_capped_short_big_move_loss_floored_at_minus_W() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # stock moved $30 -> payout would be huge, but loss is floored at -W = -5.
    pnl = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=130.0, risk_width=5.0, cost_haircut_pct=0.0,
    )
    assert pnl is not None
    assert pnl.net_pnl == -5.0          # floored at -W exactly
    assert pnl.return_pct == -100.0     # -5 / 5 * 100


def test_capped_short_tighter_W_costs_more_wings() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # Same tiny move; compare W=5 vs W=10. Tighter cap (W=5) -> bigger wing cost
    # -> smaller net credit than the wider W=10.
    tight = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=100.5, risk_width=5.0, cost_haircut_pct=0.0,
    )
    wide = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=100.5, risk_width=10.0, cost_haircut_pct=0.0,
    )
    assert tight is not None and wide is not None
    assert wide.net_pnl > tight.net_pnl  # wider cap = cheaper wings = more profit


def test_capped_short_invalid_inputs_return_none() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    assert simulate_capped_short_straddle_pnl(
        straddle_price=0.0, strike=100.0, underlying_price=100.0,
        post_report_close=101.0, risk_width=5.0, cost_haircut_pct=0.0,
    ) is None
    assert simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=101.0, risk_width=0.0, cost_haircut_pct=0.0,
    ) is None
