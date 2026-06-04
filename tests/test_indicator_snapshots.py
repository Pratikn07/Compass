from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from prescient.signal.models import (
    IndicatorFreshness,
    MacdState,
    PriceVsVwapState,
    TechnicalIndicatorSnapshot,
)


def _snapshot(**overrides: object) -> TechnicalIndicatorSnapshot:
    values = {
        "ticker": "ntnx",
        "as_of": date(2026, 6, 1),
        "rsi_14": 62.4,
        "macd_line": 1.25,
        "macd_signal": 1.05,
        "macd_histogram": 0.2,
        "macd_state": "bullish",
        "vwap": 42.75,
        "price_vs_vwap": "above",
        "missing_fields": [],
        "source": "mock-provider",
        "freshness": "current",
    }
    values.update(overrides)
    return TechnicalIndicatorSnapshot.model_validate(values)


def test_valid_indicator_snapshot_serializes_compact_structured_fields() -> None:
    snapshot = _snapshot()

    assert snapshot.ticker == "NTNX"
    assert snapshot.macd_state == MacdState.BULLISH
    assert snapshot.price_vs_vwap == PriceVsVwapState.ABOVE
    assert snapshot.freshness == IndicatorFreshness.CURRENT
    assert snapshot.model_dump(mode="json") == {
        "ticker": "NTNX",
        "as_of": "2026-06-01",
        "rsi_14": 62.4,
        "macd_line": 1.25,
        "macd_signal": 1.05,
        "macd_histogram": 0.2,
        "macd_state": "bullish",
        "vwap": 42.75,
        "price_vs_vwap": "above",
        "missing_fields": [],
        "source": "mock-provider",
        "freshness": "current",
    }


def test_invalid_indicator_enum_values_are_rejected() -> None:
    with pytest.raises(ValidationError, match="macd_state"):
        _snapshot(macd_state="crossing_up")

    with pytest.raises(ValidationError, match="price_vs_vwap"):
        _snapshot(price_vs_vwap="far_above")


@pytest.mark.parametrize("raw_key", ["raw_ohlcv", "candles", "ohlcv"])
def test_raw_candle_payload_fields_are_rejected(raw_key: str) -> None:
    with pytest.raises(ValidationError, match=raw_key):
        _snapshot(**{raw_key: []})


def test_missing_indicator_values_must_be_listed_in_missing_fields() -> None:
    snapshot = _snapshot(rsi_14=None, missing_fields=["rsi_14"])

    assert snapshot.rsi_14 is None
    assert snapshot.missing_fields == ["rsi_14"]

    with pytest.raises(ValidationError, match="rsi_14"):
        _snapshot(rsi_14=None, missing_fields=[])
