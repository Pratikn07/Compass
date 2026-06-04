from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import OrderSide, TimeInForce

from prescient.broker.alpaca import AlpacaAdapter
from prescient.broker.models import (
    BrokerAuthenticationError,
    BrokerCapabilities,
    BrokerConnectionError,
    BrokerExecutionError,
    BrokerOrderStatus,
    BrokerRateLimitError,
    UnsupportedCapabilityError,
)
from prescient.risk.models import (
    ExecutionMode,
    RiskOrderProposal,
    TradeExpression,
)


def _alpaca_order(
    *,
    order_id: str = "alpaca-order-1",
    status: str = "accepted",
    filled_qty: str | None = "0.0",
    filled_avg_price: str | None = None,
) -> Mock:
    order = Mock()
    order.id = order_id
    order.status = Mock()
    order.status.value = status
    order.filled_qty = filled_qty
    order.filled_avg_price = filled_avg_price
    return order


def _proposal(
    target: str = " AAPL ",
    *,
    expression: str = "STOCK",
    estimated_entry_cost: float = 150.0,
) -> RiskOrderProposal:
    return RiskOrderProposal(
        target=target,
        expression=expression,
        estimated_entry_cost=estimated_entry_cost,
        maximum_loss=30.0,
    )


def _make_alpaca_api_error(status_code: int, message: str) -> APIError:
    mock_http_err = Mock()
    mock_http_err.response = Mock()
    mock_http_err.response.status_code = status_code
    return APIError(
        error=json.dumps({"code": status_code, "message": message}),
        http_error=mock_http_err,
    )


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_adapter_initialization(mock_trading_client) -> None:
    # 1. Missing keys raises Authentication Error
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(BrokerAuthenticationError):
            AlpacaAdapter(execution_mode=ExecutionMode.PAPER)

    # 2. Key provided via parameters succeeds
    adapter = AlpacaAdapter(
        execution_mode=ExecutionMode.PAPER,
        api_key="test_key",
        api_secret="test_secret",
    )
    assert adapter.paper is True
    mock_trading_client.assert_called_once_with(
        api_key="test_key",
        secret_key="test_secret",
        paper=True,
    )


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_get_account_snapshot(mock_trading_client_cls) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    mock_account = Mock()
    mock_account.equity = "30000.0"
    mock_account.cash = "20000.0"
    mock_account.buying_power = "25000.0"
    mock_client.get_account.return_value = mock_account

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )
    snapshot = adapter.get_account_snapshot()

    assert snapshot.equity == 30000.0
    assert snapshot.cash == 20000.0
    assert snapshot.buying_power == 25000.0
    mock_client.get_account.assert_called_once()


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_get_positions(mock_trading_client_cls) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    # Stock position mock
    mock_pos_stock = Mock()
    mock_pos_stock.symbol = "AAPL"
    mock_pos_stock.asset_class = Mock()
    mock_pos_stock.asset_class.value = "us_equity"
    mock_pos_stock.qty = "10.0"
    mock_pos_stock.market_value = "1500.0"
    mock_pos_stock.avg_entry_price = "145.0"

    # Option position mock
    mock_pos_option = Mock()
    mock_pos_option.symbol = "AAPL260619C00150000"
    mock_pos_option.asset_class = Mock()
    mock_pos_option.asset_class.value = "us_option"
    mock_pos_option.qty = "2.0"
    mock_pos_option.market_value = "500.0"
    mock_pos_option.avg_entry_price = "2.5"

    mock_client.get_all_positions.return_value = [mock_pos_stock, mock_pos_option]

    adapter = AlpacaAdapter(
        execution_mode="live",
        api_key="k",
        api_secret="s",
    )
    positions = adapter.get_positions()

    assert len(positions) == 2
    assert positions[0].symbol == "AAPL"
    assert positions[0].expression == TradeExpression.STOCK
    assert positions[0].qty == 10.0

    assert positions[1].symbol == "AAPL260619C00150000"
    assert positions[1].expression == TradeExpression.CALL_OPTION
    assert positions[1].qty == 2.0


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order(mock_trading_client_cls) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    mock_order = Mock()
    mock_order.id = "f05be702-86ff-4c6e-8263-6cf1be5e525a"
    mock_order.status = Mock()
    mock_order.status.value = "accepted"
    mock_order.filled_qty = "0.0"
    mock_order.filled_avg_price = None
    mock_client.submit_order.return_value = mock_order

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )
    proposal = RiskOrderProposal(
        target="AAPL",
        expression="STOCK",
        estimated_entry_cost=150.0,
        maximum_loss=30.0,
    )
    result = adapter.place_order(proposal)

    assert result.order_id == "f05be702-86ff-4c6e-8263-6cf1be5e525a"
    assert result.filled_qty == 0
    assert result.avg_fill_price is None


@pytest.mark.parametrize(
    (
        "alpaca_status",
        "expected_status",
        "filled_qty",
        "filled_avg_price",
        "expected_filled_qty",
        "expected_avg_fill_price",
    ),
    [
        ("filled", BrokerOrderStatus.FILLED, "1.0", "151.25", 1, 151.25),
        ("canceled", BrokerOrderStatus.CANCELLED, "0.0", None, 0, None),
        ("rejected", BrokerOrderStatus.REJECTED, "0.0", None, 0, None),
        ("accepted", BrokerOrderStatus.OPEN, "0.0", None, 0, None),
    ],
)
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_maps_status_and_request_shape(
    mock_trading_client_cls,
    alpaca_status: str,
    expected_status: BrokerOrderStatus,
    filled_qty: str | None,
    filled_avg_price: str | None,
    expected_filled_qty: int,
    expected_avg_fill_price: float | None,
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client
    mock_client.submit_order.return_value = _alpaca_order(
        status=alpaca_status,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
    )

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    result = adapter.place_order(_proposal(target=" msft "))

    assert result.order_id == "alpaca-order-1"
    assert result.status == expected_status
    assert result.filled_qty == expected_filled_qty
    assert result.avg_fill_price == expected_avg_fill_price
    assert f"Status: {alpaca_status}" in result.message

    mock_client.submit_order.assert_called_once()
    order_request = mock_client.submit_order.call_args.args[0]
    assert order_request.symbol == "MSFT"
    assert float(order_request.qty) == 1.0
    assert order_request.side == OrderSide.BUY
    assert order_request.time_in_force == TimeInForce.DAY


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_exception_mapping(mock_trading_client_cls) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    # Helper to construct APIError
    def make_api_error(status_code: int, message: str) -> APIError:
        mock_http_err = Mock()
        mock_http_err.response = Mock()
        mock_http_err.response.status_code = status_code
        return APIError(
            error=json.dumps({"code": status_code, "message": message}),
            http_error=mock_http_err,
        )

    # 1. 401 Unauthorized -> BrokerAuthenticationError
    mock_client.get_account.side_effect = make_api_error(401, "Auth failed")
    with pytest.raises(BrokerAuthenticationError):
        adapter.get_account_snapshot()

    # 2. 429 Too Many Requests -> BrokerRateLimitError
    mock_client.get_account.side_effect = make_api_error(429, "Rate limited")
    with pytest.raises(BrokerRateLimitError):
        adapter.get_account_snapshot()

    # 3. 422 Invalid Order -> BrokerExecutionError
    mock_client.get_account.side_effect = make_api_error(422, "Insufficient funds")
    with pytest.raises(BrokerExecutionError):
        adapter.get_account_snapshot()

    # 4. Connection Timeout -> BrokerConnectionError
    mock_client.get_account.side_effect = ConnectionError("timeout connection dns lookup")
    with pytest.raises(BrokerConnectionError):
        adapter.get_account_snapshot()


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, BrokerAuthenticationError),
        (403, BrokerAuthenticationError),
        (429, BrokerRateLimitError),
        (400, BrokerExecutionError),
        (422, BrokerExecutionError),
        (404, BrokerExecutionError),
    ],
)
@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_maps_submit_order_api_errors(
    mock_trading_client_cls,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client
    mock_client.submit_order.side_effect = _make_alpaca_api_error(status_code, "order failed")

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    with pytest.raises(expected_error):
        adapter.place_order(_proposal())


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_maps_submit_order_connection_error(
    mock_trading_client_cls,
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client
    mock_client.submit_order.side_effect = ConnectionError("timeout connection dns lookup")

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    with pytest.raises(BrokerConnectionError):
        adapter.place_order(_proposal())


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_place_order_rejects_options_when_capability_disabled_before_submit(
    mock_trading_client_cls,
) -> None:
    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    adapter = AlpacaAdapter(
        execution_mode="paper",
        api_key="k",
        api_secret="s",
    )

    with patch.object(
        adapter,
        "get_capabilities",
        return_value=BrokerCapabilities(
            supports_options=False,
            supports_paper_trading=True,
            broker_name="alpaca",
        ),
    ):
        with pytest.raises(UnsupportedCapabilityError, match="options capability disabled"):
            adapter.place_order(
                _proposal(
                    target="AAPL260619C00150000",
                    expression="CALL_OPTION",
                    estimated_entry_cost=1.50,
                )
            )

    mock_client.submit_order.assert_not_called()


@patch("prescient.broker.alpaca.TradingClient")
def test_alpaca_factory_propose_only_never_submits_order(
    mock_trading_client_cls,
) -> None:
    from prescient.broker import get_broker_adapter

    mock_client = MagicMock()
    mock_trading_client_cls.return_value = mock_client

    mock_client.get_account.return_value = Mock(
        equity="20000.0",
        cash="20000.0",
        buying_power="20000.0",
    )

    adapter = get_broker_adapter(
        "alpaca",
        "propose_only",
        api_key="k",
        api_secret="s",
    )

    result = adapter.place_order(_proposal(target="AAPL", estimated_entry_cost=100.0))

    assert result.status == BrokerOrderStatus.OPEN
    assert result.order_id.startswith("propose-only-")
    assert "propose-only mode active" in result.message
    mock_client.get_account.assert_called_once()
    mock_client.submit_order.assert_not_called()
