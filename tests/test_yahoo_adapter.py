"""Pure-parse tests for the Yahoo chart adapter (no network)."""
from datetime import date

from compass.adapters.yahoo import parse_chart

TS_2006_01_03 = 1136300400  # 2006-01-03 US market day (UTC-normalized to date)
TS_2006_01_04 = 1136386800


def _payload(timestamps, opens, highs, lows, closes, volumes, adjcloses):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"dataGranularity": "1d"},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens,
                                "high": highs,
                                "low": lows,
                                "close": closes,
                                "volume": volumes,
                            }
                        ],
                        "adjclose": [{"adjclose": adjcloses}],
                    },
                }
            ]
        }
    }


def test_parses_normal_bars():
    payload = _payload(
        [TS_2006_01_03, TS_2006_01_04],
        [10.0, 10.5], [10.6, 10.9], [9.9, 10.4], [10.5, 10.8],
        [1000, 2000], [10.1, 10.4],
    )
    bars = parse_chart("TEST", payload)
    assert len(bars) == 2
    assert bars[0].ticker == "TEST"
    assert bars[0].d == date(2006, 1, 3)
    assert bars[0].adj_close == 10.1
    assert bars[0].close == 10.5
    assert bars[1].volume == 2000
    assert all(b.source == "yahoo" for b in bars)


def test_skips_bars_with_null_adjclose_never_fabricates():
    payload = _payload(
        [TS_2006_01_03, TS_2006_01_04],
        [10.0, None], [None, None], [None, None], [10.5, None],
        [1000, None], [10.1, None],
    )
    bars = parse_chart("TEST", payload)
    assert len(bars) == 1
    assert bars[0].d == date(2006, 1, 3)


def test_skips_null_timestamp():
    payload = _payload([None, TS_2006_01_04], [1, 2], [1, 2], [1, 2], [1, 2], [1, 2], [1.0, 2.0])
    bars = parse_chart("TEST", payload)
    assert len(bars) == 1
    assert bars[0].adj_close == 2.0


def test_drops_pre_1990_history():
    ts_1989 = 600000000  # 1989-01-05
    payload = _payload([ts_1989, TS_2006_01_03], [1, 2], [1, 2], [1, 2], [1, 2], [1, 2], [1.0, 2.0])
    bars = parse_chart("TEST", payload)
    assert len(bars) == 1
    assert bars[0].d.year == 2006


def test_malformed_payload_returns_empty():
    assert parse_chart("TEST", {}) == []
    assert parse_chart("TEST", {"chart": {"result": None}}) == []
    assert parse_chart("TEST", {"chart": {"result": [{}]}}) == []
