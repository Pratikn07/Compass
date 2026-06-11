"""Pure-parse tests for the Alpaca bars adapter (no network)."""
from datetime import date

from compass.adapters.alpaca import parse_bars


def test_parses_pages_and_skips_garbled():
    pages = [
        {
            "bars": [
                {"t": "2024-01-02T05:00:00Z", "o": 10.0, "h": 11.0, "l": 9.5,
                 "c": 10.5, "v": 12345},
                {"t": "bad-timestamp", "c": 1.0},  # skipped
                {"t": "2024-01-03T05:00:00Z"},  # missing close -> skipped
            ]
        },
        {"bars": [{"t": "2024-01-04T05:00:00Z", "c": 11.0, "v": 99}]},
        {"bars": None},  # empty page tolerated
    ]
    bars = parse_bars("TEST", pages)
    assert [b.d for b in bars] == [date(2024, 1, 2), date(2024, 1, 4)]
    assert bars[0].adj_close == 10.5  # adjustment=all -> close is adjusted
    assert bars[1].volume == 99
    assert all(b.source == "alpaca" for b in bars)
