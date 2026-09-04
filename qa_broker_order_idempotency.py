from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import requests

from src.broker_order_store import BrokerOrderStore
from src.integrations.brokers.alpaca_paper import (
    AlpacaPaperBrokerAdapter,
    AlpacaPaperBrokerError,
    AlpacaPaperConfig,
    BrokerSubmissionUncertainError,
)
from src.integrations.brokers.base import BrokerOrderRequest
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeResponse:
    def __init__(self, status_code: int, payload=None, request_id: str = "request-qa"):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"X-Request-ID": request_id}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def account_response():
    return FakeResponse(
        200,
        {"id": "paper-account-123", "status": "ACTIVE", "trading_blocked": False, "equity": "100000"},
        "account-request",
    )


def order_request(client_order_id="paper-order-1", quantity="1"):
    return BrokerOrderRequest(
        client_order_id=client_order_id,
        symbol="AAPL",
        quantity=quantity,
        side="buy",
        order_type="market",
        time_in_force="day",
    )


def broker_order(client_order_id="paper-order-1", status="accepted", filled_qty="0", avg=None):
    return {
        "id": "broker-order-123",
        "client_order_id": client_order_id,
        "symbol": "AAPL",
        "qty": "1",
        "filled_qty": filled_qty,
        "filled_avg_price": avg,
        "side": "buy",
        "type": "market",
        "order_type": "market",
        "time_in_force": "day",
        "status": status,
        "submitted_at": "2026-08-27T14:00:00Z",
        "updated_at": "2026-08-27T14:00:00Z",
    }


def test_submit_is_idempotent_and_persists_request_id() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="broker-submit-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "broker.db")
        try:
            storage.init_db()
            session = FakeSession([account_response(), FakeResponse(200, broker_order(), "submit-request")])
            adapter = AlpacaPaperBrokerAdapter(
                AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
                http_session=session,
            )
            first = adapter.submit_order(order_request())
            second = adapter.submit_order(order_request())
            require(first["status"] == "accepted" and first["broker_order_id"] == "broker-order-123", "accepted order not stored")
            require(first["request_id"] == "submit-request", "Alpaca request ID was not retained")
            require(second["idempotent_replay"] is True, "retry was not identified as idempotent")
            require(len(session.calls) == 2, "idempotent retry made another HTTP request")
            require(session.calls[1]["url"] == "https://paper-api.alpaca.markets/v2/orders", "wrong order endpoint")
            headers = session.calls[1]["headers"]
            require(headers["APCA-API-KEY-ID"] == "paper-key", "paper auth header missing")

            try:
                adapter.submit_order(order_request(quantity="2"))
            except ValueError as exc:
                require("collision" in str(exc), "client ID collision reason wrong")
            else:
                raise AssertionError("same client ID with changed order was accepted")
        finally:
            storage.DB_PATH = original_db_path


def test_timeout_is_uncertain_and_never_blindly_resubmitted() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="broker-timeout-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "timeout.db")
        try:
            storage.init_db()
            session = FakeSession([account_response(), requests.Timeout("slow")])
            adapter = AlpacaPaperBrokerAdapter(
                AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
                http_session=session,
            )
            try:
                adapter.submit_order(order_request("timeout-order"))
            except BrokerSubmissionUncertainError:
                pass
            else:
                raise AssertionError("timeout did not become an uncertain submission")
            stored = BrokerOrderStore().get("timeout-order")
            require(stored["status"] == "submission_uncertain", "uncertain outcome not persisted")
            replay = adapter.submit_order(order_request("timeout-order"))
            require(replay["status"] == "submission_uncertain", "retry changed uncertain state")
            require(len(session.calls) == 2, "uncertain submission was sent a second time")
        finally:
            storage.DB_PATH = original_db_path


def test_http_rejection_and_trade_update_state_machine() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="broker-events-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "events.db")
        try:
            storage.init_db()
            rejected_session = FakeSession(
                [account_response(), FakeResponse(422, {"message": "invalid qty"}, "reject-request")]
            )
            rejected_adapter = AlpacaPaperBrokerAdapter(
                AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
                http_session=rejected_session,
            )
            try:
                rejected_adapter.submit_order(order_request("rejected-order"))
            except AlpacaPaperBrokerError as exc:
                require(exc.http_status == 422, "HTTP rejection status was lost")
            else:
                raise AssertionError("HTTP 422 did not reject the order")
            rejected = BrokerOrderStore().get("rejected-order")
            require(rejected["status"] == "rejected" and rejected["request_id"] == "reject-request", "rejection not persisted")

            store = BrokerOrderStore()
            store.reserve(order_request("fill-order"), account_id_hash="paper-hash")
            store.update_from_broker_order(broker_order("fill-order", "accepted"))
            partial_payload = {
                "stream": "trade_updates",
                "data": {
                    "event": "partial_fill",
                    "execution_id": "execution-partial",
                    "timestamp": "2026-08-27T14:00:01Z",
                    "qty": "0.4",
                    "price": "200.10",
                    "order": broker_order("fill-order", "partially_filled", "0.4", "200.10"),
                },
            }
            fill_payload = {
                "stream": "trade_updates",
                "data": {
                    "event": "fill",
                    "execution_id": "execution-fill",
                    "timestamp": "2026-08-27T14:00:02Z",
                    "qty": "0.6",
                    "price": "200.20",
                    "order": broker_order("fill-order", "filled", "1", "200.16"),
                },
            }
            adapter = AlpacaPaperBrokerAdapter(
                AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=False)
            )
            partial = adapter.process_trade_update(partial_payload)
            filled = adapter.process_trade_update(fill_payload)
            duplicate = adapter.process_trade_update(fill_payload)
            require(partial["order"]["status"] == "partially_filled", "partial fill state wrong")
            require(filled["order"]["status"] == "filled", "fill state wrong")
            require(filled["order"]["filled_quantity"] == 1 and filled["order"]["filled_avg_price"] == 200.16, "fill totals wrong")
            require(duplicate["inserted"] is False, "duplicate fill event inserted")

            late_accepted = {
                "stream": "trade_updates",
                "data": {
                    "event": "accepted",
                    "event_id": "late-accepted",
                    "timestamp": "2026-08-27T14:00:03Z",
                    "order": broker_order("fill-order", "accepted", "0"),
                },
            }
            result = adapter.process_trade_update(late_accepted)
            require(result["order"]["status"] == "filled", "terminal filled state regressed")

            binary = str.encode(__import__("json").dumps(fill_payload))
            require(adapter._decode_stream_message(binary)["stream"] == "trade_updates", "binary frame failed")
            conn = sqlite3.connect(storage.DB_PATH)
            events = conn.execute(
                "SELECT event_type, filled_quantity FROM broker_order_events WHERE client_order_id = 'fill-order' ORDER BY id"
            ).fetchall()
            conn.close()
            require(events[:2] == [("partially_filled", 0.4), ("filled", 0.6)], "fill event history wrong")
        finally:
            storage.DB_PATH = original_db_path


def test_account_positions_and_order_snapshot_endpoints() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="broker-snapshot-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "snapshot.db")
        try:
            storage.init_db()
            session = FakeSession(
                [
                    account_response(),
                    FakeResponse(200, [{"symbol": "AAPL", "qty": "1", "market_value": "200"}]),
                    FakeResponse(200, [broker_order("snapshot-order", "filled", "1", "200")]),
                ]
            )
            adapter = AlpacaPaperBrokerAdapter(
                AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
                http_session=session,
            )
            positions = adapter.list_positions()
            orders = adapter.list_orders(status="all", limit=500)
            require(positions[0]["symbol"] == "AAPL", "position list response was not accepted")
            require(orders[0]["client_order_id"] == "snapshot-order", "order list response was not accepted")
            require(session.calls[1]["url"].endswith("/v2/positions"), "wrong positions endpoint")
            require(session.calls[2]["params"]["status"] == "all", "order reconciliation did not request all statuses")
            require(BrokerOrderStore().get("snapshot-order")["status"] == "filled", "broker order snapshot was not persisted")
        finally:
            storage.DB_PATH = original_db_path


if __name__ == "__main__":
    test_submit_is_idempotent_and_persists_request_id()
    test_timeout_is_uncertain_and_never_blindly_resubmitted()
    test_http_rejection_and_trade_update_state_machine()
    test_account_positions_and_order_snapshot_endpoints()
    print("broker order idempotency and trade-update QA passed")
