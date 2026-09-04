from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakePaperAdapter:
    def __init__(self) -> None:
        self.account: Dict[str, Any] = {"id": "paper-account-qa", "cash": "900", "equity": "1000"}
        self.positions: List[Dict[str, Any]] = []
        self.orders: List[Dict[str, Any]] = []

    def get_account(self) -> Dict[str, Any]:
        return dict(self.account)

    def list_positions(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.positions]

    def list_orders(self, *, status: str = "all", limit: int = 500) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.orders[:limit]]


def broker_order(client_id: str, symbol: str, qty: float, filled: float, status: str, side: str = "buy") -> Dict[str, Any]:
    return {
        "id": f"broker-{client_id}",
        "client_order_id": client_id,
        "symbol": symbol,
        "qty": str(qty),
        "filled_qty": str(filled),
        "filled_avg_price": "10" if filled else None,
        "side": side,
        "type": "market",
        "time_in_force": "day",
        "status": status,
        "submitted_at": "2026-08-27T10:00:00Z",
        "updated_at": "2026-08-27T10:00:01Z",
    }


def position(symbol: str, qty: float, market_value: float) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "asset_class": "us_equity",
        "qty": str(qty),
        "side": "long",
        "avg_entry_price": "10",
        "current_price": str(market_value / qty),
        "market_value": str(market_value),
        "cost_basis": str(qty * 10),
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "reconciliation.db")
        os.environ["BROKER_RECONCILIATION_REQUIRED"] = "true"
        os.environ["BROKER_RECONCILIATION_MAX_AGE_SECONDS"] = "90"

        from src.broker_order_store import BrokerOrderStore
        from src.broker_reconciliation_service import (
            BrokerReconciliationBlockedError,
            BrokerReconciliationService,
        )
        from src.integrations.brokers.base import BrokerOrderRequest
        import src.storage as storage

        storage.init_db()
        adapter = FakePaperAdapter()
        store = BrokerOrderStore()
        service = BrokerReconciliationService(adapter, order_store=store)

        first = broker_order("qa-order-0001", "AAPL", 10, 10, "filled")
        adapter.orders = [first]
        adapter.positions = [position("AAPL", 10, 100)]
        clean = service.reconcile()
        require(clean["reconciliation_status"] == "reconciled", "clean fill did not reconcile")
        require(service.enforce_reconciled()["trade_allowed"] is True, "fresh clean snapshot did not open gate")

        adapter.positions = [position("AAPL", 11, 110)]
        adapter.account = {"id": "paper-account-qa", "cash": "890", "equity": "1000"}
        mismatch = service.reconcile()
        require(mismatch["reconciliation_status"] == "unreconciled", "position mismatch was missed")
        require(any(item["type"] == "position_quantity_mismatch" for item in mismatch["differences"]), "quantity difference missing")
        try:
            service.enforce_reconciled()
            raise AssertionError("unreconciled snapshot did not block orders")
        except BrokerReconciliationBlockedError:
            pass

        adapter.positions = [position("AAPL", 10, 100)]
        adapter.account = {"id": "paper-account-qa", "cash": "900", "equity": "1000"}
        recovered = service.reconcile()
        require(recovered["reconciliation_status"] == "reconciled", "recovery did not reconcile")

        partial = broker_order("qa-order-0002", "MSFT", 10, 4, "partially_filled")
        adapter.orders = [first, partial]
        adapter.positions = [position("AAPL", 10, 100), position("MSFT", 4, 80)]
        adapter.account = {"id": "paper-account-qa", "cash": "820", "equity": "1000"}
        partial_snapshot = service.reconcile()
        require(partial_snapshot["reconciliation_status"] == "reconciled", "partial fill did not reconcile")

        pending_request = BrokerOrderRequest(
            client_order_id="qa-order-0003",
            symbol="NVDA",
            quantity="2",
            side="buy",
            order_type="market",
            time_in_force="day",
        )
        store.reserve(pending_request, account_id_hash=partial_snapshot["account_id_hash"])
        missing = service.reconcile()
        require(any(item["type"] == "active_local_order_missing_at_broker" for item in missing["differences"]), "missing active order was not detected")

        canceled = broker_order("qa-order-0003", "NVDA", 2, 0, "canceled")
        adapter.orders = [first, partial, canceled]
        canceled_snapshot = service.reconcile()
        require(canceled_snapshot["reconciliation_status"] == "reconciled", "canceled zero-fill order did not reconcile")

        restarted = BrokerReconciliationService(adapter, order_store=BrokerOrderStore())
        restart_status = restarted.status()
        require(restart_status["state"] == "ready", "reconciliation state was not restart-safe")
        require(restart_status["paper_only"] is True, "snapshot escaped paper-only mode")

        conn = storage._connect_db(row_factory=True)
        try:
            incident = conn.execute(
                "SELECT status, resolved_at, details_json FROM integration_incidents WHERE id = ?",
                (BrokerReconciliationService.INCIDENT_ID,),
            ).fetchone()
        finally:
            conn.close()
        require(incident is not None and incident["status"] == "resolved", "reconciliation incident was not resolved")
        require("paper-account-qa" not in str(incident["details_json"]), "raw account ID leaked into incident")

        print("broker reconciliation QA passed (mismatch, partial fill, cancel, restart, fail-closed gate)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
