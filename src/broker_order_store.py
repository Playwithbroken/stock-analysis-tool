from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional

from src.integrations.brokers.base import BrokerOrderRequest
from src.integrations.contracts import BrokerOrderEvent, canonical_json, payload_sha256
import src.storage as storage


TERMINAL_ORDER_STATUSES = frozenset({"filled", "canceled", "rejected", "expired", "replaced"})
NON_REGRESSING_STATUSES = frozenset({"partially_filled", *TERMINAL_ORDER_STATUSES})
EVENT_STATUS_MAP = {
    "new": "new",
    "accepted": "accepted",
    "pending_new": "pending_new",
    "partial_fill": "partially_filled",
    "fill": "filled",
    "canceled": "canceled",
    "rejected": "rejected",
    "expired": "expired",
    "done_for_day": "done_for_day",
    "replaced": "replaced",
    "pending_cancel": "pending_cancel",
    "pending_replace": "pending_replace",
    "stopped": "stopped",
    "calculated": "calculated",
    "suspended": "suspended",
    "order_replace_rejected": "replace_rejected",
    "order_cancel_rejected": "cancel_rejected",
}


class BrokerOrderStore:
    def reserve(self, request: BrokerOrderRequest, *, account_id_hash: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        request_hash = payload_sha256(
            {"account_mode": "paper", "provider": "alpaca", **request.provider_payload()}
        )
        conn = storage._connect_db(row_factory=True)
        try:
            existing = conn.execute(
                "SELECT * FROM broker_orders WHERE client_order_id = ?",
                (request.client_order_id,),
            ).fetchone()
            if existing:
                row = self._row_to_dict(existing)
                if row["request_hash"] != request_hash:
                    raise ValueError("client_order_id collision: existing order has a different request")
                return {**row, "created": False, "idempotent_replay": True}
            conn.execute(
                """
                INSERT INTO broker_orders (
                    client_order_id, broker_order_id, provider, account_mode, account_id_hash,
                    symbol, side, order_type, time_in_force, requested_quantity,
                    limit_price, stop_price, status, request_hash, signal_decision_id,
                    submitted_at, filled_quantity, filled_avg_price, last_event_at,
                    request_id, raw_order_json, updated_at, created_at
                ) VALUES (?, ?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.client_order_id,
                    None,
                    "alpaca",
                    account_id_hash,
                    request.symbol,
                    request.side,
                    request.order_type,
                    request.time_in_force,
                    float(request.quantity),
                    float(request.limit_price) if request.limit_price else None,
                    float(request.stop_price) if request.stop_price else None,
                    "submit_pending",
                    request_hash,
                    request.signal_decision_id,
                    None,
                    None,
                    None,
                    None,
                    canonical_json(request.provider_payload()),
                    now,
                    now,
                ),
            )
            conn.commit()
            created = self.get(request.client_order_id)
            return {**(created or {}), "created": True, "idempotent_replay": False}
        finally:
            conn.close()

    def update_from_broker_order(
        self,
        order: Mapping[str, Any],
        *,
        request_id: Optional[str] = None,
        event_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        client_order_id = str(order.get("client_order_id") or "").strip()
        if not client_order_id:
            raise ValueError("broker order is missing client_order_id")
        current = self.get(client_order_id)
        if not current:
            self._import_stream_order(order)
            current = self.get(client_order_id) or {}
        candidate = str(order.get("status") or current.get("status") or "pending").strip().lower()
        status = self._next_status(str(current.get("status") or ""), candidate)
        now = datetime.now(timezone.utc).isoformat()
        conn = storage._connect_db()
        try:
            conn.execute(
                """
                UPDATE broker_orders
                SET broker_order_id = COALESCE(?, broker_order_id), status = ?,
                    submitted_at = COALESCE(?, submitted_at), filled_quantity = ?,
                    filled_avg_price = ?, last_event_at = COALESCE(?, last_event_at),
                    request_id = COALESCE(?, request_id), raw_order_json = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (
                    str(order.get("id") or "").strip() or None,
                    status,
                    order.get("submitted_at"),
                    float(order.get("filled_qty") or 0),
                    float(order["filled_avg_price"]) if order.get("filled_avg_price") not in {None, ""} else None,
                    event_at,
                    request_id,
                    canonical_json(dict(order)),
                    now,
                    client_order_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(client_order_id) or {}

    def mark_submission_uncertain(self, client_order_id: str, reason: str) -> Dict[str, Any]:
        return self._set_status(client_order_id, "submission_uncertain", {"reason": str(reason)})

    def mark_rejected(self, client_order_id: str, reason: str, *, request_id: Optional[str] = None) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        conn = storage._connect_db()
        try:
            conn.execute(
                """
                UPDATE broker_orders
                SET status = 'rejected', request_id = COALESCE(?, request_id),
                    raw_order_json = ?, last_event_at = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (request_id, canonical_json({"rejection_reason": str(reason)}), now, now, client_order_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(client_order_id) or {}

    def append_trade_update(self, payload: Mapping[str, Any], *, account_id_hash: str) -> Dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
        order = data.get("order") if isinstance(data.get("order"), Mapping) else {}
        raw_event = str(data.get("event") or "").strip().lower()
        normalized_event = EVENT_STATUS_MAP.get(raw_event)
        if not normalized_event:
            raise ValueError(f"unsupported Alpaca trade update event: {raw_event}")
        if not order:
            raise ValueError("Alpaca trade update is missing order")
        client_order_id = str(order.get("client_order_id") or "").strip()
        broker_order_id = str(order.get("id") or "").strip()
        if not client_order_id or not broker_order_id:
            raise ValueError("Alpaca trade update is missing order IDs")
        if not self.get(client_order_id):
            self._import_stream_order(order, account_id_hash=account_id_hash)

        provider_timestamp = str(
            data.get("timestamp") or data.get("at") or order.get("updated_at") or datetime.now(timezone.utc).isoformat()
        )
        event_id = str(data.get("event_id") or data.get("execution_id") or "").strip()
        if not event_id:
            event_id = "trade-update:" + payload_sha256(dict(payload))[:32]
        event = BrokerOrderEvent(
            event_id=event_id,
            provider="alpaca",
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            event_type=normalized_event,
            account_mode="paper",
            symbol=str(order.get("symbol") or ""),
            provider_timestamp=provider_timestamp,
            received_at=datetime.now(timezone.utc).isoformat(),
            filled_quantity=float(data.get("qty") or 0),
            fill_price=float(data["price"]) if data.get("price") not in {None, ""} else None,
            reason=str(data.get("reason") or order.get("reject_reason") or "").strip() or None,
            source_payload_hash=payload_sha256(dict(payload)),
        )
        conn = storage._connect_db()
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO broker_order_events (
                    provider, event_id, schema_version, client_order_id, broker_order_id,
                    event_type, account_mode, symbol, provider_timestamp, received_at,
                    filled_quantity, fill_price, reason, source_payload_hash, source_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'paper', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.provider,
                    event.event_id,
                    event.schema_version,
                    event.client_order_id,
                    event.broker_order_id,
                    event.event_type,
                    event.symbol,
                    event.provider_timestamp,
                    event.received_at,
                    event.filled_quantity,
                    event.fill_price,
                    event.reason,
                    event.source_payload_hash,
                    canonical_json(dict(payload)),
                ),
            )
            inserted = cursor.rowcount == 1
            if not inserted:
                existing = conn.execute(
                    "SELECT source_payload_hash FROM broker_order_events WHERE provider = 'alpaca' AND event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if existing and existing[0] != event.source_payload_hash:
                    raise ValueError("broker event ID collision with changed payload")
            conn.commit()
        finally:
            conn.close()
        updated = self.update_from_broker_order(order, event_at=event.provider_timestamp)
        return {"inserted": inserted, "event": event.to_dict(), "order": updated}

    def get(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        conn = storage._connect_db(row_factory=True)
        try:
            row = conn.execute(
                "SELECT * FROM broker_orders WHERE client_order_id = ?", (str(client_order_id),)
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = storage._connect_db(row_factory=True)
        try:
            rows = conn.execute(
                "SELECT * FROM broker_orders ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 10000)),),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def _set_status(self, client_order_id: str, status: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        conn = storage._connect_db()
        try:
            conn.execute(
                "UPDATE broker_orders SET status = ?, raw_order_json = ?, updated_at = ? WHERE client_order_id = ?",
                (status, canonical_json(dict(payload)), now, client_order_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(client_order_id) or {}

    def _import_stream_order(self, order: Mapping[str, Any], *, account_id_hash: str = "stream_import") -> None:
        client_order_id = str(order.get("client_order_id") or "").strip()
        now = datetime.now(timezone.utc).isoformat()
        request_material = {
            "client_order_id": client_order_id,
            "symbol": str(order.get("symbol") or "").strip().upper(),
            "qty": str(order.get("qty") or "0"),
            "side": str(order.get("side") or "unknown"),
            "type": str(order.get("type") or order.get("order_type") or "unknown"),
            "time_in_force": str(order.get("time_in_force") or "unknown"),
        }
        conn = storage._connect_db()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO broker_orders (
                    client_order_id, broker_order_id, provider, account_mode, account_id_hash,
                    symbol, side, order_type, time_in_force, requested_quantity,
                    limit_price, stop_price, status, request_hash, signal_decision_id,
                    submitted_at, filled_quantity, filled_avg_price, last_event_at,
                    request_id, raw_order_json, updated_at, created_at
                ) VALUES (?, ?, 'alpaca', 'paper', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    client_order_id,
                    str(order.get("id") or "").strip() or None,
                    account_id_hash,
                    request_material["symbol"],
                    request_material["side"],
                    request_material["type"],
                    request_material["time_in_force"],
                    float(order.get("qty") or 0),
                    float(order["limit_price"]) if order.get("limit_price") not in {None, ""} else None,
                    float(order["stop_price"]) if order.get("stop_price") not in {None, ""} else None,
                    str(order.get("status") or "pending"),
                    payload_sha256(request_material),
                    order.get("submitted_at"),
                    float(order.get("filled_qty") or 0),
                    float(order["filled_avg_price"]) if order.get("filled_avg_price") not in {None, ""} else None,
                    order.get("updated_at"),
                    canonical_json(dict(order)),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _next_status(current: str, candidate: str) -> str:
        current = str(current or "").lower()
        candidate = str(candidate or "").lower()
        if current in TERMINAL_ORDER_STATUSES:
            return current
        if current == "partially_filled" and candidate in {
            "new", "accepted", "pending", "pending_new", "submit_pending"
        }:
            return current
        return candidate or current or "pending"

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        result = dict(row)
        try:
            result["raw_order"] = json.loads(result.pop("raw_order_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            result["raw_order"] = {}
            result.pop("raw_order_json", None)
        result["paper_only"] = result.get("account_mode") == "paper"
        return result
