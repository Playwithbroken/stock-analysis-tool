from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import uuid
from typing import Any, Dict, List, Mapping, Optional

from src.broker_order_store import BrokerOrderStore, TERMINAL_ORDER_STATUSES
from src.integrations.contracts import canonical_json, payload_sha256
import src.storage as storage


class BrokerReconciliationBlockedError(RuntimeError):
    pass


class BrokerReconciliationService:
    INCIDENT_ID = "alpaca-paper-reconciliation"

    def __init__(self, adapter: Any = None, *, order_store: Optional[BrokerOrderStore] = None):
        self.adapter = adapter
        self.order_store = order_store or BrokerOrderStore()

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_positions(positions: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for position in positions:
            symbol = str(position.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            quantity = BrokerReconciliationService._float(position.get("qty"))
            side = str(position.get("side") or ("short" if quantity < 0 else "long")).lower()
            if side == "short" and quantity > 0:
                quantity = -quantity
            rows.append(
                {
                    "symbol": symbol,
                    "asset_class": str(position.get("asset_class") or "unknown").lower(),
                    "quantity": round(quantity, 9),
                    "side": side,
                    "avg_entry_price": BrokerReconciliationService._float(position.get("avg_entry_price")),
                    "current_price": BrokerReconciliationService._float(position.get("current_price")),
                    "market_value": BrokerReconciliationService._float(position.get("market_value")),
                    "cost_basis": BrokerReconciliationService._float(position.get("cost_basis")),
                }
            )
        return sorted(rows, key=lambda item: item["symbol"])

    @staticmethod
    def _normalize_orders(orders: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        for order in orders:
            client_id = str(order.get("client_order_id") or "").strip()
            if not client_id:
                continue
            rows.append(
                {
                    "client_order_id": client_id,
                    "broker_order_id": str(order.get("id") or "").strip() or None,
                    "symbol": str(order.get("symbol") or "").strip().upper(),
                    "side": str(order.get("side") or "").lower(),
                    "status": str(order.get("status") or "").lower(),
                    "quantity": BrokerReconciliationService._float(order.get("qty")),
                    "filled_quantity": BrokerReconciliationService._float(order.get("filled_qty")),
                    "filled_avg_price": (
                        BrokerReconciliationService._float(order.get("filled_avg_price"))
                        if order.get("filled_avg_price") not in {None, ""}
                        else None
                    ),
                    "updated_at": order.get("updated_at"),
                }
            )
        return sorted(rows, key=lambda item: item["client_order_id"])

    def _expected_positions(self, local_orders: List[Mapping[str, Any]]) -> Dict[str, float]:
        expected: Dict[str, float] = {}
        for order in local_orders:
            filled = self._float(order.get("filled_quantity"))
            if filled <= 0:
                continue
            sign = 1.0 if str(order.get("side") or "").lower() == "buy" else -1.0
            symbol = str(order.get("symbol") or "").upper()
            if symbol:
                expected[symbol] = expected.get(symbol, 0.0) + sign * filled
        return {symbol: round(quantity, 9) for symbol, quantity in expected.items() if abs(quantity) > 1e-9}

    def reconcile(self) -> Dict[str, Any]:
        if self.adapter is None:
            raise RuntimeError("broker reconciliation adapter is not configured")
        account = self.adapter.get_account()
        positions = self._normalize_positions(self.adapter.list_positions())
        broker_orders_raw = self.adapter.list_orders(status="all", limit=500)
        for order in broker_orders_raw:
            self.order_store.update_from_broker_order(order)
        broker_orders = self._normalize_orders(broker_orders_raw)
        local_orders = self.order_store.list_orders(limit=10000)

        account_id = str(account.get("id") or "").strip()
        if not account_id:
            raise RuntimeError("paper account response is missing account ID")
        account_id_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()
        cash = self._float(account.get("cash"))
        equity = self._float(account.get("equity"))
        quantity_tolerance = max(0.0, float(os.getenv("BROKER_RECONCILIATION_QUANTITY_TOLERANCE", "0.000001")))
        equity_tolerance = max(0.01, float(os.getenv("BROKER_RECONCILIATION_EQUITY_TOLERANCE", "1.00")))

        expected_positions = self._expected_positions(local_orders)
        actual_positions = {row["symbol"]: float(row["quantity"]) for row in positions}
        differences: List[Dict[str, Any]] = []
        for symbol in sorted(set(expected_positions) | set(actual_positions)):
            expected = float(expected_positions.get(symbol, 0))
            actual = float(actual_positions.get(symbol, 0))
            if abs(expected - actual) > quantity_tolerance:
                differences.append(
                    {
                        "type": "position_quantity_mismatch",
                        "symbol": symbol,
                        "local_quantity": expected,
                        "broker_quantity": actual,
                        "difference": round(actual - expected, 9),
                    }
                )

        broker_client_ids = {row["client_order_id"] for row in broker_orders}
        for order in local_orders:
            status = str(order.get("status") or "").lower()
            if status in TERMINAL_ORDER_STATUSES:
                continue
            client_id = str(order.get("client_order_id") or "")
            if client_id not in broker_client_ids:
                differences.append(
                    {
                        "type": "active_local_order_missing_at_broker",
                        "client_order_id": client_id,
                        "local_status": status,
                    }
                )

        position_market_value = round(sum(float(row["market_value"]) for row in positions), 2)
        calculated_equity = round(cash + position_market_value, 2)
        if abs(equity - calculated_equity) > equity_tolerance:
            differences.append(
                {
                    "type": "cash_equity_inconsistency",
                    "broker_cash": round(cash, 2),
                    "broker_equity": round(equity, 2),
                    "cash_plus_position_market_value": calculated_equity,
                    "difference": round(equity - calculated_equity, 2),
                }
            )

        captured_at = datetime.now(timezone.utc).isoformat()
        status = "reconciled" if not differences else "unreconciled"
        local_state = {"orders": local_orders, "expected_positions": expected_positions}
        broker_state = {
            "positions": positions,
            "orders": broker_orders,
            "cash": round(cash, 2),
            "equity": round(equity, 2),
        }
        snapshot = {
            "id": str(uuid.uuid4()),
            "provider": "alpaca",
            "account_mode": "paper",
            "account_id_hash": account_id_hash,
            "positions": positions,
            "orders": broker_orders,
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "local_state_hash": payload_sha256(local_state),
            "broker_state_hash": payload_sha256(broker_state),
            "reconciliation_status": status,
            "differences": differences,
            "captured_at": captured_at,
            "paper_only": True,
        }
        self._save_snapshot(snapshot)
        self._update_incident(snapshot)
        return snapshot

    def status(self) -> Dict[str, Any]:
        snapshot = self.latest_snapshot()
        required = os.getenv("BROKER_RECONCILIATION_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}
        max_age = max(10, int(float(os.getenv("BROKER_RECONCILIATION_MAX_AGE_SECONDS", "90"))))
        if not snapshot:
            return {
                "state": "not_run",
                "required": required,
                "trade_allowed": not required,
                "max_age_seconds": max_age,
                "paper_only": True,
            }
        try:
            captured = datetime.fromisoformat(str(snapshot["captured_at"]).replace("Z", "+00:00"))
            age = max(0.0, (datetime.now(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            age = float("inf")
        fresh = age <= max_age
        reconciled = snapshot.get("reconciliation_status") == "reconciled"
        expected_account_hash = None
        if self.adapter is not None:
            try:
                expected_account_hash = self.adapter.health().get("account_id_hash")
            except Exception:
                expected_account_hash = None
        account_match = not expected_account_hash or expected_account_hash == snapshot.get("account_id_hash")
        return {
            **snapshot,
            "state": (
                "account_mismatch"
                if not account_match
                else "ready"
                if reconciled and fresh
                else "stale"
                if reconciled
                else "blocked"
            ),
            "required": required,
            "fresh": fresh,
            "account_match": account_match,
            "age_seconds": round(age, 3) if age != float("inf") else None,
            "max_age_seconds": max_age,
            "trade_allowed": (reconciled and fresh and account_match) or not required,
            "paper_only": True,
        }

    def enforce_reconciled(self) -> Dict[str, Any]:
        status = self.status()
        if status.get("trade_allowed") is not True:
            raise BrokerReconciliationBlockedError(
                "Broker-paper reconciliation blocks new orders: " + str(status.get("state") or "unknown")
            )
        return status

    def latest_snapshot(self) -> Optional[Dict[str, Any]]:
        conn = storage._connect_db(row_factory=True)
        try:
            row = conn.execute(
                "SELECT * FROM broker_positions_snapshots WHERE provider = 'alpaca' ORDER BY captured_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            for source, target, fallback in (
                ("positions_json", "positions", []),
                ("orders_json", "orders", []),
                ("differences_json", "differences", []),
            ):
                try:
                    result[target] = json.loads(result.pop(source) or json.dumps(fallback))
                except (TypeError, ValueError, json.JSONDecodeError):
                    result[target] = fallback
            result["paper_only"] = result.get("account_mode") == "paper"
            return result
        finally:
            conn.close()

    def _save_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        conn = storage._connect_db()
        try:
            conn.execute(
                """
                INSERT INTO broker_positions_snapshots (
                    id, provider, account_mode, account_id_hash, positions_json, cash, equity,
                    local_state_hash, broker_state_hash, reconciliation_status, orders_json,
                    differences_json, captured_at, created_at
                ) VALUES (?, 'alpaca', 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["id"], snapshot["account_id_hash"], canonical_json(snapshot["positions"]),
                    snapshot["cash"], snapshot["equity"], snapshot["local_state_hash"],
                    snapshot["broker_state_hash"], snapshot["reconciliation_status"],
                    canonical_json(snapshot["orders"]), canonical_json(snapshot["differences"]),
                    snapshot["captured_at"], snapshot["captured_at"],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_incident(self, snapshot: Mapping[str, Any]) -> None:
        now = str(snapshot["captured_at"])
        conn = storage._connect_db()
        try:
            if snapshot["reconciliation_status"] == "reconciled":
                conn.execute(
                    """
                    UPDATE integration_incidents SET status = 'resolved', resolved_at = ?, updated_at = ?
                    WHERE id = ? AND status != 'resolved'
                    """,
                    (now, now, self.INCIDENT_ID),
                )
            else:
                details = {
                    "snapshot_id": snapshot["id"],
                    "difference_count": len(snapshot["differences"]),
                    "differences": snapshot["differences"],
                    "paper_only": True,
                }
                conn.execute(
                    """
                    INSERT INTO integration_incidents (
                        id, provider, component, incident_type, severity, status, summary,
                        details_json, opened_at, resolved_at, updated_at
                    ) VALUES (?, 'alpaca', 'broker_paper', 'reconciliation_mismatch', 'critical',
                              'open', ?, ?, ?, NULL, ?)
                    ON CONFLICT(id) DO UPDATE SET status = 'open', severity = 'critical',
                        summary = excluded.summary, details_json = excluded.details_json,
                        opened_at = CASE WHEN integration_incidents.status = 'resolved' THEN excluded.opened_at ELSE integration_incidents.opened_at END,
                        resolved_at = NULL, updated_at = excluded.updated_at
                    """,
                    (
                        self.INCIDENT_ID,
                        f"Alpaca paper reconciliation found {len(snapshot['differences'])} difference(s)",
                        canonical_json(details), now, now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
