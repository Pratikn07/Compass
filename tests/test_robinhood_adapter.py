from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from prescient.broker import get_broker_adapter
from prescient.broker.models import (
    BrokerAuthenticationError,
    BrokerConnectionError,
    BrokerExecutionError,
    BrokerOrderStatus,
    BrokerRateLimitError,
    ConfigurationError,
    UnsupportedCapabilityError,
)
from prescient.risk.models import (
    ExecutionMode,
    RiskOrderProposal,
)
from prescient.safety import KillSwitchState, KillSwitchStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter():
    """Create a RobinhoodAdapter with login mocked out."""
    with patch("prescient.broker.robinhood.r.login"):
        from prescient.broker.robinhood import RobinhoodAdapter

        yield RobinhoodAdapter(
            execution_mode=ExecutionMode.LIVE,
            username="test",
            password="test",
        )


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


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    error = requests.exceptions.HTTPError(f"HTTP {status_code}")
    error.response = response
    return error


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


@patch("prescient.broker.robinhood.r.login")
def test_paper_mode_raises_configuration_error(mock_login: MagicMock) -> None:
    from prescient.broker.robinhood import RobinhoodAdapter

    with pytest.raises(ConfigurationError) as exc:
        RobinhoodAdapter(
            execution_mode=ExecutionMode.PAPER,
            username="test",
            password="test",
        )
    assert "paper" in str(exc.value).lower()
    mock_login.assert_not_called()


@patch("prescient.broker.robinhood.r.login")
def test_missing_credentials_raises_authentication_error(mock_login: MagicMock) -> None:
    from prescient.broker.robinhood import RobinhoodAdapter

    with pytest.raises(BrokerAuthenticationError) as exc:
        RobinhoodAdapter(execution_mode=ExecutionMode.LIVE)
    assert "credentials" in str(exc.value).lower()
    mock_login.assert_not_called()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def test_capabilities_reports_no_options_no_paper(adapter) -> None:
    caps = adapter.get_capabilities()
    assert caps.supports_options is False
    assert caps.supports_paper_trading is False
    assert caps.broker_name == "robinhood"


# ---------------------------------------------------------------------------
# Account snapshot
# ---------------------------------------------------------------------------


@patch("prescient.broker.robinhood.r.profiles.load_account_profile")
def test_get_account_snapshot_maps_correctly(mock_profile: MagicMock, adapter) -> None:
    mock_profile.return_value = {
        "equity": "15000.00",
        "cash": "5000.00",
        "buying_power": "10000.00",
    }

    snapshot = adapter.get_account_snapshot()

    assert snapshot.equity == 15000.0
    assert snapshot.cash == 5000.0
    assert snapshot.buying_power == 10000.0
    mock_profile.assert_called_once()


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


@patch("prescient.broker.robinhood.r.account.build_holdings")
def test_get_positions_filters_crypto(mock_holdings: MagicMock, adapter) -> None:
    mock_holdings.return_value = {
        "AAPL": {
            "quantity": "10",
            "equity": "1500.00",
            "average_buy_price": "150.00",
            "type": "stock",
        },
        "DOGE": {
            "quantity": "1000",
            "equity": "80.00",
            "average_buy_price": "0.08",
            "type": "cryptocurrency",
        },
    }

    positions = adapter.get_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].qty == 10.0
    assert positions[0].market_value == 1500.0
    assert positions[0].average_entry_price == 150.0


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------


def test_place_order_rejects_options(adapter) -> None:
    proposal = RiskOrderProposal(
        target="AAPL260619C00150000",
        expression="CALL_OPTION",
        estimated_entry_cost=1.5,
        maximum_loss=1.0,
    )

    with pytest.raises(UnsupportedCapabilityError) as exc:
        adapter.place_order(proposal)
    assert "options" in str(exc.value).lower()


@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_stock_succeeds(mock_order: MagicMock, adapter) -> None:
    mock_order.return_value = {
        "id": "abc-123",
        "state": "filled",
        "cumulative_quantity": "1.0000",
        "average_price": "150.00",
    }

    proposal = RiskOrderProposal(
        target="AAPL",
        expression="STOCK",
        estimated_entry_cost=150.0,
        maximum_loss=30.0,
    )

    result = adapter.place_order(proposal)

    assert result.order_id == "abc-123"
    assert result.status == BrokerOrderStatus.FILLED
    assert result.filled_qty == 1
    assert result.avg_fill_price == 150.0
    mock_order.assert_called_once()


@pytest.mark.parametrize(
    (
        "state",
        "expected_status",
        "cumulative_quantity",
        "average_price",
        "expected_filled_qty",
        "expected_avg_fill_price",
    ),
    [
        ("filled", BrokerOrderStatus.FILLED, "1.0000", "150.00", 1, 150.0),
        ("cancelled", BrokerOrderStatus.CANCELLED, "0.0000", None, 0, None),
        ("canceled", BrokerOrderStatus.CANCELLED, "0.0000", None, 0, None),
        ("rejected", BrokerOrderStatus.REJECTED, "0.0000", None, 0, None),
        ("confirmed", BrokerOrderStatus.OPEN, "0.0000", None, 0, None),
    ],
)
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_stock_maps_status_and_request_shape(
    mock_order: MagicMock,
    adapter,
    state: str,
    expected_status: BrokerOrderStatus,
    cumulative_quantity: str,
    average_price: str | None,
    expected_filled_qty: int,
    expected_avg_fill_price: float | None,
) -> None:
    mock_order.return_value = {
        "id": "rh-order-123",
        "state": state,
        "cumulative_quantity": cumulative_quantity,
        "average_price": average_price,
    }

    result = adapter.place_order(_proposal(target=" msft "))

    assert result.order_id == "rh-order-123"
    assert result.status == expected_status
    assert result.filled_qty == expected_filled_qty
    assert result.avg_fill_price == expected_avg_fill_price
    assert f"Status: {state}" in result.message
    mock_order.assert_called_once_with(
        symbol="MSFT",
        quantity=1,
        limitPrice=150.0,
        timeInForce="gfd",
    )


@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_rejects_options_before_order_api(
    mock_order: MagicMock,
    adapter,
) -> None:
    with pytest.raises(UnsupportedCapabilityError, match="options trading"):
        adapter.place_order(
            _proposal(
                target="AAPL260619C00150000",
                expression="CALL_OPTION",
                estimated_entry_cost=1.50,
            )
        )

    mock_order.assert_not_called()


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------


@patch("prescient.broker.robinhood.r.profiles.load_account_profile")
def test_connection_error_mapped(mock_profile: MagicMock, adapter) -> None:
    mock_profile.side_effect = requests.exceptions.ConnectionError("Network unreachable")

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
    ],
)
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_maps_order_api_http_errors(
    mock_order: MagicMock,
    adapter,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    mock_order.side_effect = _http_error(status_code)

    with pytest.raises(expected_error):
        adapter.place_order(_proposal())


@pytest.mark.parametrize(
    "side_effect",
    [
        requests.exceptions.ConnectionError("Network unreachable"),
        requests.exceptions.Timeout("Request timed out"),
    ],
)
@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
def test_place_order_maps_order_api_connection_failures(
    mock_order: MagicMock,
    adapter,
    side_effect: Exception,
) -> None:
    mock_order.side_effect = side_effect

    with pytest.raises(BrokerConnectionError):
        adapter.place_order(_proposal())


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


@patch("prescient.broker.robinhood.r.login")
def test_factory_resolves_robinhood_adapter(mock_login: MagicMock) -> None:
    from prescient.broker.robinhood import RobinhoodAdapter

    from prescient.broker.execution_guard import KillSwitchBrokerWrapper, PreflightCheckBrokerWrapper

    adapter = get_broker_adapter(
        "robinhood",
        "live",
        username="test",
        password="test",
    )

    assert isinstance(adapter, KillSwitchBrokerWrapper)
    assert isinstance(adapter._inner, PreflightCheckBrokerWrapper)
    assert isinstance(adapter._inner._inner, RobinhoodAdapter)
    assert adapter.get_capabilities().broker_name == "robinhood"
    mock_login.assert_called_once()


def test_factory_rejects_robinhood_paper_mode() -> None:
    with pytest.raises(ConfigurationError) as exc:
        get_broker_adapter("robinhood", "paper", username="test", password="test")
    assert "paper" in str(exc.value).lower()


@patch("prescient.broker.robinhood.r.orders.order_buy_limit")
@patch("prescient.broker.robinhood.r.profiles.load_account_profile")
@patch("prescient.broker.robinhood.r.login")
def test_robinhood_factory_kill_switch_blocks_before_profile_or_order(
    mock_login: MagicMock,
    mock_profile: MagicMock,
    mock_order: MagicMock,
) -> None:
    provider = MagicMock()
    provider.read_state.return_value = KillSwitchState(status=KillSwitchStatus.ACTIVE)

    adapter = get_broker_adapter(
        "robinhood",
        "live",
        username="test",
        password="test",
        kill_switch_provider=provider,
    )

    with pytest.raises(BrokerExecutionError, match="Kill switch active"):
        adapter.place_order(_proposal(target="AAPL", estimated_entry_cost=100.0))

    mock_login.assert_called_once()
    provider.read_state.assert_called_once()
    mock_profile.assert_not_called()
    mock_order.assert_not_called()
