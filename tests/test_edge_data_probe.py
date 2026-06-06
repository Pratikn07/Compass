from __future__ import annotations

from datetime import date

from prescient.edge.models import OptionQuote


def _q(ticker, qdate):
    return OptionQuote(
        ticker=ticker, option_type="CALL", strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=qdate, bid=1.0, ask=1.2,
    )


def test_summarize_depth_reports_earliest_and_count_per_ticker() -> None:
    from prescient.edge.data_probe import summarize_option_history_depth

    quotes = {
        "MU": [_q("MU", date(2024, 1, 2)), _q("MU", date(2024, 6, 25))],
        "NVDA": [_q("NVDA", date(2024, 5, 1))],
    }
    summary = summarize_option_history_depth(quotes)
    assert summary["MU"].earliest_quote_date == date(2024, 1, 2)
    assert summary["MU"].quote_count == 2
    assert summary["NVDA"].quote_count == 1
