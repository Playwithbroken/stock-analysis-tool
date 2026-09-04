from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import random
import time
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse
from urllib.parse import quote

import requests
import websockets

from src.broker_order_store import BrokerOrderStore
from src.integrations.brokers.base import BrokerAdapter, BrokerOrderRequest
from src.latency_monitor_service import LatencyMonitorService
from src.provider_observability import classify_provider_error, record_provider_result


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
PAPER_STREAM_URL = "wss://paper-api.alpaca.markets/stream"


class AlpacaPaperBrokerError(RuntimeError):
    def __init__(self, message: str, *, http_status: Optional[int] = None, request_id: Optional[str] = None):
        super().__init__(message)
        self.http_status = http_status
        self.request_id = request_id


class BrokerSubmissionUncertainError(AlpacaPaperBrokerError):
    pass


@dataclass(frozen=True)
class AlpacaPaperConfig:
    key_id: str
    secret_key: str
    enabled: bool = False
    base_url: str = PAPER_BASE_URL
    stream_url: str = PAPER_STREAM_URL
    timeout_seconds: float = 10.0
    reconnect_max_seconds: float = 30.0

    def __post_init__(self) -> None:
        normalized_base = str(self.base_url or "").strip().rstrip("/")
        normalized_stream = str(self.stream_url or "").strip()
        if normalized_base != PAPER_BASE_URL:
            raise ValueError("Alpaca paper adapter refuses every non-paper REST endpoint")
        if normalized_stream != PAPER_STREAM_URL:
            raise ValueError("Alpaca paper adapter refuses every non-paper stream endpoint")
        for url in (normalized_base, normalized_stream):
            parsed = urlparse(url)
            if parsed.hostname != "paper-api.alpaca.markets" or parsed.port is not None:
                raise ValueError("Alpaca paper endpoint host or port is unsafe")
        object.__setattr__(self, "base_url", normalized_base)
        object.__setattr__(self, "stream_url", normalized_stream)
        if self.enabled and (not self.key_id.strip() or not self.secret_key.strip()):
            raise ValueError("Alpaca paper broker is enabled but paper credentials are missing")

    @classmethod
    def from_env(cls) -> "AlpacaPaperConfig":
        return cls(
            key_id=(
                os.getenv("ALPACA_PAPER_API_KEY_ID", "").strip()
                or os.getenv("APCA_API_KEY_ID", "").strip()
            ),
            secret_key=(
                os.getenv("ALPACA_PAPER_API_SECRET_KEY", "").strip()
                or os.getenv("APCA_API_SECRET_KEY", "").strip()
            ),
            enabled=os.getenv("ALPACA_PAPER_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            base_url=os.getenv("ALPACA_PAPER_BASE_URL", PAPER_BASE_URL).strip(),
            stream_url=os.getenv("ALPACA_PAPER_STREAM_URL", PAPER_STREAM_URL).strip(),
            timeout_seconds=max(1.0, float(os.getenv("ALPACA_PAPER_TIMEOUT_SECONDS", "10"))),
        )


class AlpacaPaperBrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        config: AlpacaPaperConfig,
        *,
        order_store: Optional[BrokerOrderStore] = None,
        latency_monitor: Optional[LatencyMonitorService] = None,
        http_session: Optional[requests.Session] = None,
    ):
        self.config = config
        self.order_store = order_store or BrokerOrderStore()
        self.latency_monitor = latency_monitor or LatencyMonitorService()
        self.http = http_session or requests.Session()
        self._stop = asyncio.Event()
        self._account: Optional[Dict[str, Any]] = None
        self._account_id_hash: Optional[str] = None
        self._health: Dict[str, Any] = {
            "provider": "alpaca",
            "account_mode": "paper",
            "paper_only": True,
            "enabled": config.enabled,
            "state": "disabled" if not config.enabled else "configured",
            "rest_verified": False,
            "stream_connected": False,
            "stream_authorized": False,
            "stream_listening": False,
            "last_stream_message_at": None,
            "last_order_event_at": None,
            "reconnect_count": 0,
            "event_count": 0,
            "duplicate_event_count": 0,
            "last_error": None,
        }

    def health(self) -> Dict[str, Any]:
        result = json.loads(json.dumps(self._health))
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["credentials_present"] = bool(self.config.key_id and self.config.secret_key)
        result["base_url"] = PAPER_BASE_URL
        result["account_id_hash"] = self._account_id_hash
        return result

    def verify_account(self, *, force: bool = False) -> Dict[str, Any]:
        self._ensure_enabled()
        if self._account is not None and not force:
            return dict(self._account)
        account, response = self._request("GET", "/v2/account")
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            raise AlpacaPaperBrokerError("Alpaca paper account response is missing account ID")
        if account.get("trading_blocked") is True or account.get("account_blocked") is True:
            raise AlpacaPaperBrokerError("Alpaca paper account is blocked for trading")
        account_status = str(account.get("status") or "ACTIVE").upper()
        if account_status not in {"ACTIVE", "ACCOUNT_UPDATED"}:
            raise AlpacaPaperBrokerError(f"Alpaca paper account status is not active: {account_status}")
        self._account = dict(account)
        self._account_id_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()
        self._health["rest_verified"] = True
        self._health["state"] = "ready"
        return dict(account)

    def get_account(self) -> Dict[str, Any]:
        return self.verify_account(force=True)

    def list_positions(self) -> List[Dict[str, Any]]:
        self._ensure_enabled()
        self.verify_account()
        positions, _ = self._request("GET", "/v2/positions", expected_type=list)
        return [dict(item) for item in positions if isinstance(item, Mapping)]

    def list_orders(self, *, status: str = "all", limit: int = 500) -> List[Dict[str, Any]]:
        self._ensure_enabled()
        self.verify_account()
        normalized_status = str(status or "all").lower()
        if normalized_status not in {"open", "closed", "all"}:
            raise ValueError("order status must be open, closed or all")
        safe_limit = max(1, min(int(limit), 500))
        orders, _ = self._request(
            "GET",
            "/v2/orders",
            params={"status": normalized_status, "limit": safe_limit, "direction": "desc", "nested": "false"},
            expected_type=list,
        )
        result: List[Dict[str, Any]] = []
        for item in orders:
            if not isinstance(item, Mapping):
                continue
            normalized = dict(item)
            self.order_store.update_from_broker_order(normalized)
            result.append(normalized)
        return result

    def get_asset(self, symbol: str) -> Dict[str, Any]:
        self._ensure_enabled()
        self.verify_account()
        normalized = str(symbol or "").strip().upper()
        if not normalized or len(normalized) > 32:
            raise ValueError("symbol is required")
        asset, _ = self._request("GET", f"/v2/assets/{quote(normalized, safe='.-')}")
        return dict(asset)

    def assess_short_sale(
        self,
        *,
        symbol: str,
        quantity: Any,
        reference_price: float,
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        account = self.verify_account()
        try:
            requested_quantity = Decimal(str(quantity))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("short quantity must be numeric") from exc
        if not requested_quantity.is_finite() or requested_quantity <= 0:
            raise ValueError("short quantity must be positive")
        positions = self.list_positions()
        normalized_symbol = str(symbol or "").strip().upper()
        current_position = next(
            (item for item in positions if str(item.get("symbol") or "").strip().upper() == normalized_symbol),
            {},
        )
        current_quantity = Decimal(str(current_position.get("qty") or "0"))
        if str(current_position.get("side") or "").lower() == "short" and current_quantity > 0:
            current_quantity = -current_quantity
        long_quantity = max(Decimal("0"), current_quantity)
        opening_short_quantity = max(Decimal("0"), requested_quantity - long_quantity)
        if opening_short_quantity <= 0:
            return {
                "allowed": True,
                "action": "reduce_or_close_long",
                "opens_short": False,
                "symbol": normalized_symbol,
                "requested_quantity": float(requested_quantity),
                "opening_short_quantity": 0.0,
                "paper_only": True,
                "reasons": [],
            }

        asset = self.get_asset(normalized_symbol)
        borrow_status = str(asset.get("borrow_status") or "").strip().lower()
        easy_to_borrow = asset.get("easy_to_borrow") is True or borrow_status == "easy_to_borrow"
        blockers = []
        if str(asset.get("class") or asset.get("asset_class") or "").lower() != "us_equity":
            blockers.append("only_us_equity_can_be_shorted")
        if str(asset.get("status") or "").lower() != "active":
            blockers.append("asset_not_active")
        if asset.get("tradable") is not True:
            blockers.append("asset_not_tradable")
        if asset.get("marginable") is not True:
            blockers.append("asset_not_marginable")
        if asset.get("shortable") is not True:
            blockers.append("asset_not_shortable")
        if not easy_to_borrow:
            blockers.append("borrow_not_easy_to_borrow")
        if requested_quantity != requested_quantity.to_integral_value():
            blockers.append("fractional_short_not_supported")
        equity = float(account.get("equity") or 0)
        if equity < 2_000:
            blockers.append("paper_account_equity_below_short_minimum")

        price = max(0.0, float(reference_price or 0))
        existing_short_value = sum(
            abs(float(item.get("market_value") or 0))
            for item in positions
            if str(item.get("side") or "").lower() == "short" or float(item.get("qty") or 0) < 0
        )
        proposed_short_value = float(opening_short_quantity) * price
        max_position_pct = max(0.1, float(os.getenv("BROKER_PAPER_MAX_SHORT_POSITION_PCT", "12")))
        max_total_pct = max(0.1, float(os.getenv("BROKER_PAPER_MAX_TOTAL_SHORT_PCT", "30")))
        if price <= 0:
            blockers.append("short_reference_price_missing")
        if proposed_short_value > equity * (max_position_pct / 100) + 0.01:
            blockers.append("short_position_limit_exceeded")
        if existing_short_value + proposed_short_value > equity * (max_total_pct / 100) + 0.01:
            blockers.append("total_short_exposure_limit_exceeded")
        return {
            "allowed": not blockers,
            "action": "open_or_increase_short",
            "opens_short": True,
            "symbol": normalized_symbol,
            "requested_quantity": float(requested_quantity),
            "opening_short_quantity": float(opening_short_quantity),
            "reference_price": price,
            "proposed_short_value": round(proposed_short_value, 2),
            "existing_short_value": round(existing_short_value, 2),
            "max_short_position_value": round(equity * (max_position_pct / 100), 2),
            "max_total_short_value": round(equity * (max_total_pct / 100), 2),
            "borrow_status": borrow_status or ("easy_to_borrow" if asset.get("easy_to_borrow") is True else "unknown"),
            "easy_to_borrow": easy_to_borrow,
            "paper_only": True,
            "locate_workflow_enabled": False,
            "reasons": blockers,
        }

    def submit_order(self, request: BrokerOrderRequest) -> Dict[str, Any]:
        self._ensure_enabled()
        self.verify_account()
        account_hash = self._account_id_hash or "paper-account-unverified"
        reserved = self.order_store.reserve(request, account_id_hash=account_hash)
        if reserved.get("created") is not True:
            return reserved
        started = time.perf_counter()
        try:
            order, response = self._request("POST", "/v2/orders", json_body=request.provider_payload())
            request_id = response.headers.get("X-Request-ID")
            if str(order.get("client_order_id") or "") != request.client_order_id:
                self.order_store.mark_submission_uncertain(
                    request.client_order_id, "broker response client_order_id mismatch"
                )
                raise BrokerSubmissionUncertainError(
                    "Alpaca response client_order_id does not match the submitted order",
                    request_id=request_id,
                )
            stored = self.order_store.update_from_broker_order(order, request_id=request_id)
            self.latency_monitor.record(
                provider="alpaca",
                service="broker_paper",
                segment="submit_ack",
                latency_ms=(time.perf_counter() - started) * 1000,
                status="ok",
                symbol=request.symbol,
                correlation_id=request.client_order_id,
                metadata={"request_id": request_id, "paper_only": True},
            )
            return {**stored, "created": True, "idempotent_replay": False}
        except AlpacaPaperBrokerError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            self.latency_monitor.record(
                provider="alpaca",
                service="broker_paper",
                segment="submit_ack",
                latency_ms=elapsed,
                status="error",
                symbol=request.symbol,
                correlation_id=request.client_order_id,
                metadata={"http_status": exc.http_status, "request_id": exc.request_id},
            )
            if exc.http_status is not None and 400 <= exc.http_status < 500:
                self.order_store.mark_rejected(
                    request.client_order_id, str(exc), request_id=exc.request_id
                )
            else:
                self.order_store.mark_submission_uncertain(request.client_order_id, str(exc))
            raise
        except (requests.Timeout, requests.ConnectionError) as exc:
            self.order_store.mark_submission_uncertain(request.client_order_id, exc.__class__.__name__)
            raise BrokerSubmissionUncertainError(
                "Alpaca paper submission outcome is uncertain; automatic resubmission is blocked"
            ) from exc

    def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        self._ensure_enabled()
        self.verify_account()
        normalized = str(broker_order_id or "").strip()
        if not normalized:
            raise ValueError("broker_order_id is required")
        _, response = self._request("DELETE", f"/v2/orders/{normalized}", expect_json=False)
        return {
            "status": "cancel_requested",
            "broker_order_id": normalized,
            "request_id": response.headers.get("X-Request-ID"),
            "paper_only": True,
        }

    def get_order_by_client_id(self, client_order_id: str) -> Dict[str, Any]:
        self._ensure_enabled()
        self.verify_account()
        order, response = self._request(
            "GET",
            "/v2/orders:by_client_order_id",
            params={"client_order_id": str(client_order_id)},
        )
        return self.order_store.update_from_broker_order(
            order, request_id=response.headers.get("X-Request-ID")
        )

    async def close(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        if not self.config.enabled:
            self._health["state"] = "disabled"
            return
        await asyncio.to_thread(self.verify_account)
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._run_stream()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                self._health["stream_connected"] = False
                self._health["stream_authorized"] = False
                self._health["stream_listening"] = False
                self._health["state"] = "degraded"
                self._health["reconnect_count"] += 1
                self._health["last_error"] = {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                record_provider_result(
                    "broker",
                    "alpaca_paper",
                    "trade_updates",
                    "error",
                    error_code=classify_provider_error("broker", error=exc),
                    error_type=exc.__class__.__name__,
                )
                delay = min(self.config.reconnect_max_seconds, 2 ** min(attempt, 5))
                delay *= random.uniform(0.8, 1.2)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

    async def _run_stream(self) -> None:
        async with websockets.connect(
            self.config.stream_url,
            open_timeout=self.config.timeout_seconds,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_queue=1024,
        ) as websocket:
            self._health["stream_connected"] = True
            await websocket.send(
                json.dumps(
                    {"action": "auth", "key": self.config.key_id, "secret": self.config.secret_key},
                    separators=(",", ":"),
                )
            )
            auth = self._decode_stream_message(
                await asyncio.wait_for(websocket.recv(), timeout=self.config.timeout_seconds)
            )
            auth_data = auth.get("data") if isinstance(auth.get("data"), Mapping) else {}
            if auth.get("stream") != "authorization" or auth_data.get("status") != "authorized":
                raise AlpacaPaperBrokerError("Alpaca paper trade-update stream authorization failed")
            self._health["stream_authorized"] = True
            await websocket.send(
                json.dumps(
                    {"action": "listen", "data": {"streams": ["trade_updates"]}},
                    separators=(",", ":"),
                )
            )
            listening = self._decode_stream_message(
                await asyncio.wait_for(websocket.recv(), timeout=self.config.timeout_seconds)
            )
            streams = (listening.get("data") or {}).get("streams") if isinstance(listening.get("data"), Mapping) else []
            if listening.get("stream") != "listening" or "trade_updates" not in (streams or []):
                raise AlpacaPaperBrokerError("Alpaca paper stream did not confirm trade_updates")
            self._health["stream_listening"] = True
            self._health["state"] = "live"
            record_provider_result("broker", "alpaca_paper", "trade_updates_connect", "ok")

            while not self._stop.is_set():
                raw = await websocket.recv()
                self._health["last_stream_message_at"] = datetime.now(timezone.utc).isoformat()
                payload = self._decode_stream_message(raw)
                if payload.get("action") == "error":
                    raise AlpacaPaperBrokerError(
                        str((payload.get("data") or {}).get("error_message") or "Alpaca stream error")
                    )
                if payload.get("stream") != "trade_updates":
                    continue
                result = await asyncio.to_thread(
                    self.order_store.append_trade_update,
                    payload,
                    account_id_hash=self._account_id_hash or "paper-account-unverified",
                )
                self._record_trade_update_latency(result)
                if result["inserted"]:
                    self._health["event_count"] += 1
                    self._health["last_order_event_at"] = result["event"]["provider_timestamp"]
                else:
                    self._health["duplicate_event_count"] += 1

    def process_trade_update(self, raw: str | bytes | Mapping[str, Any]) -> Dict[str, Any]:
        payload = self._decode_stream_message(raw)
        if payload.get("stream") != "trade_updates":
            raise ValueError("message is not an Alpaca trade_updates event")
        result = self.order_store.append_trade_update(
            payload,
            account_id_hash=self._account_id_hash or "paper-account-unverified",
        )
        self._record_trade_update_latency(result)
        return result

    def _record_trade_update_latency(self, result: Mapping[str, Any]) -> None:
        event = result.get("event") if isinstance(result.get("event"), Mapping) else {}
        if not result.get("inserted") or event.get("event_type") not in {"partially_filled", "filled"}:
            return
        try:
            provider_at = datetime.fromisoformat(str(event.get("provider_timestamp")).replace("Z", "+00:00"))
            received_at = datetime.fromisoformat(str(event.get("received_at")).replace("Z", "+00:00"))
            latency_ms = max(0.0, (received_at - provider_at).total_seconds() * 1000)
        except (TypeError, ValueError):
            return
        self.latency_monitor.record(
            provider="alpaca",
            service="broker_paper",
            segment="fill",
            latency_ms=latency_ms,
            status="ok",
            symbol=str(event.get("symbol") or "") or None,
            correlation_id=str(event.get("event_id") or "") or None,
            metadata={"event_type": event.get("event_type"), "paper_only": True},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        expect_json: bool = True,
        expected_type: type = dict,
    ) -> tuple[Any, requests.Response]:
        if not str(path).startswith("/") or "//" in str(path):
            raise ValueError("unsafe Alpaca paper API path")
        url = PAPER_BASE_URL + path
        response = self.http.request(
            method,
            url,
            headers={
                "APCA-API-KEY-ID": self.config.key_id,
                "APCA-API-SECRET-KEY": self.config.secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=json_body,
            params=params,
            timeout=self.config.timeout_seconds,
        )
        request_id = response.headers.get("X-Request-ID")
        if response.status_code >= 400:
            try:
                detail = response.json()
                message = str(detail.get("message") or detail.get("code") or "request rejected")
            except Exception:
                message = "request rejected"
            raise AlpacaPaperBrokerError(
                f"Alpaca paper API rejected the request: {message[:300]}",
                http_status=response.status_code,
                request_id=request_id,
            )
        if not expect_json:
            return {}, response
        try:
            payload = response.json()
        except Exception as exc:
            raise AlpacaPaperBrokerError(
                "Alpaca paper API returned invalid JSON", request_id=request_id
            ) from exc
        if not isinstance(payload, expected_type):
            raise AlpacaPaperBrokerError(
                f"Alpaca paper API returned an unexpected {type(payload).__name__} response",
                request_id=request_id,
            )
        return payload, response

    def _ensure_enabled(self) -> None:
        if not self.config.enabled:
            raise AlpacaPaperBrokerError("Alpaca paper broker is disabled")
        if self.config.base_url != PAPER_BASE_URL or self.config.stream_url != PAPER_STREAM_URL:
            raise AlpacaPaperBrokerError("paper-only endpoint invariant failed")

    @staticmethod
    def _decode_stream_message(raw: str | bytes | Mapping[str, Any]) -> Dict[str, Any]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if not isinstance(payload, dict):
            raise AlpacaPaperBrokerError("Alpaca paper stream returned a non-object message")
        return payload
