from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

from src.integrations.brokers.alpaca_paper import (
    PAPER_BASE_URL,
    PAPER_STREAM_URL,
    AlpacaPaperBrokerAdapter,
    AlpacaPaperConfig,
)
from src.integrations.brokers.base import BrokerOrderRequest
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_configuration_refuses_live_or_custom_endpoints() -> None:
    unsafe = (
        {"base_url": "https://api.alpaca.markets"},
        {"base_url": "http://paper-api.alpaca.markets"},
        {"base_url": "https://paper-api.alpaca.markets:443"},
        {"stream_url": "wss://api.alpaca.markets/stream"},
        {"stream_url": "ws://paper-api.alpaca.markets/stream"},
    )
    for overrides in unsafe:
        values = {
            "key_id": "paper-key",
            "secret_key": "paper-secret",
            "enabled": True,
            "base_url": PAPER_BASE_URL,
            "stream_url": PAPER_STREAM_URL,
        }
        values.update(overrides)
        try:
            AlpacaPaperConfig(**values)
        except ValueError:
            continue
        raise AssertionError(f"unsafe endpoint accepted: {overrides}")

    try:
        AlpacaPaperConfig(key_id="", secret_key="", enabled=True)
    except ValueError:
        pass
    else:
        raise AssertionError("enabled paper adapter without credentials was accepted")


def test_order_request_contract_is_conservative() -> None:
    order = BrokerOrderRequest(
        client_order_id="paper-qa-1",
        symbol="aapl",
        quantity="1.2500",
        side="BUY",
        order_type="limit",
        time_in_force="day",
        limit_price="200.50",
    )
    require(order.symbol == "AAPL" and order.quantity == "1.25", "order normalization wrong")
    require(order.provider_payload()["limit_price"] == "200.5", "decimal payload is not canonical")
    invalid = (
        {"client_order_id": "", "symbol": "AAPL", "quantity": "1", "side": "buy", "order_type": "market", "time_in_force": "day"},
        {"client_order_id": "x", "symbol": "AAPL", "quantity": "0", "side": "buy", "order_type": "market", "time_in_force": "day"},
        {"client_order_id": "x", "symbol": "AAPL", "quantity": "1", "side": "hold", "order_type": "market", "time_in_force": "day"},
        {"client_order_id": "x", "symbol": "AAPL", "quantity": "1", "side": "buy", "order_type": "limit", "time_in_force": "day"},
        {"client_order_id": "x", "symbol": "AAPL", "quantity": "1", "side": "buy", "order_type": "market", "time_in_force": "day", "extended_hours": True},
    )
    for payload in invalid:
        try:
            BrokerOrderRequest(**payload)
        except ValueError:
            continue
        raise AssertionError(f"unsafe order request accepted: {payload}")


def test_health_never_exposes_credentials() -> None:
    adapter = AlpacaPaperBrokerAdapter(
        AlpacaPaperConfig(key_id="super-paper-key", secret_key="super-paper-secret", enabled=False)
    )
    text = json.dumps(adapter.health())
    require("super-paper-key" not in text and "super-paper-secret" not in text, "health leaked credentials")
    require('"paper_only": true' in text and PAPER_BASE_URL in text, "paper invariant missing in health")


if __name__ == "__main__":
    test_configuration_refuses_live_or_custom_endpoints()
    test_order_request_contract_is_conservative()
    test_health_never_exposes_credentials()
    print("broker paper-only gate QA passed")

