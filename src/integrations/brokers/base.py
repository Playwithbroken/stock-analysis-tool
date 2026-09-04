from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional


ORDER_SIDES = frozenset({"buy", "sell"})
ORDER_TYPES = frozenset({"market", "limit", "stop", "stop_limit"})
TIME_IN_FORCE = frozenset({"day", "gtc", "opg", "cls", "ioc", "fok"})


def _positive_decimal(value: Any, field_name: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{field_name} must be positive and finite")
    return format(number.normalize(), "f")


@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str
    symbol: str
    quantity: str
    side: str
    order_type: str
    time_in_force: str
    limit_price: Optional[str] = None
    stop_price: Optional[str] = None
    extended_hours: bool = False
    signal_decision_id: Optional[str] = None

    def __post_init__(self) -> None:
        client_order_id = str(self.client_order_id or "").strip()
        if not client_order_id or len(client_order_id) > 128:
            raise ValueError("client_order_id is required and must be <= 128 characters")
        object.__setattr__(self, "client_order_id", client_order_id)
        symbol = str(self.symbol or "").strip().upper()
        if not symbol or len(symbol) > 32:
            raise ValueError("symbol is required")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "quantity", _positive_decimal(self.quantity, "quantity"))
        side = str(self.side or "").strip().lower()
        if side not in ORDER_SIDES:
            raise ValueError(f"unsupported order side: {side}")
        object.__setattr__(self, "side", side)
        order_type = str(self.order_type or "").strip().lower()
        if order_type not in ORDER_TYPES:
            raise ValueError(f"unsupported order type: {order_type}")
        object.__setattr__(self, "order_type", order_type)
        tif = str(self.time_in_force or "").strip().lower()
        if tif not in TIME_IN_FORCE:
            raise ValueError(f"unsupported time_in_force: {tif}")
        object.__setattr__(self, "time_in_force", tif)
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", _positive_decimal(self.limit_price, "limit_price"))
        if self.stop_price is not None:
            object.__setattr__(self, "stop_price", _positive_decimal(self.stop_price, "stop_price"))
        if order_type in {"limit", "stop_limit"} and self.limit_price is None:
            raise ValueError(f"limit_price is required for {order_type}")
        if order_type in {"stop", "stop_limit"} and self.stop_price is None:
            raise ValueError(f"stop_price is required for {order_type}")
        if self.extended_hours and not (order_type == "limit" and tif in {"day", "gtc"}):
            raise ValueError("extended_hours requires a limit order with day or gtc")

    def provider_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "qty": self.quantity,
            "side": self.side,
            "type": self.order_type,
            "time_in_force": self.time_in_force,
            "extended_hours": self.extended_hours,
        }
        if self.limit_price is not None:
            payload["limit_price"] = self.limit_price
        if self.stop_price is not None:
            payload["stop_price"] = self.stop_price
        return payload

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BrokerAdapter(ABC):
    @abstractmethod
    def get_account(self) -> Dict[str, Any]:
        """Return the current paper-account state."""

    @abstractmethod
    def list_positions(self) -> List[Dict[str, Any]]:
        """Return all open paper positions."""

    @abstractmethod
    def list_orders(self, *, status: str = "all", limit: int = 500) -> List[Dict[str, Any]]:
        """Return paper orders and refresh the local order ledger."""

    @abstractmethod
    def get_asset(self, symbol: str) -> Dict[str, Any]:
        """Return current broker trading and borrow eligibility for one asset."""

    @abstractmethod
    def submit_order(self, request: BrokerOrderRequest) -> Dict[str, Any]:
        """Submit one idempotent paper order."""

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        """Request cancellation of one paper order."""

    @abstractmethod
    async def run(self) -> None:
        """Consume broker order and fill events until stopped."""

    @abstractmethod
    async def close(self) -> None:
        """Stop the broker stream."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return secret-free broker health."""
