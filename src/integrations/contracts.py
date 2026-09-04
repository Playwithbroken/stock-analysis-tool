from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Dict, Mapping, Optional


MARKET_EVENT_TYPES = frozenset({"quote", "trade", "bar", "heartbeat"})
ASSET_CLASSES = frozenset({"equity", "etf", "crypto", "option", "forex", "macro"})
BROKER_EVENT_TYPES = frozenset(
    {
        "new", "accepted", "pending", "pending_new", "partially_filled", "filled",
        "canceled", "rejected", "expired", "done_for_day", "replaced",
        "pending_cancel", "pending_replace", "stopped", "calculated", "suspended",
        "replace_rejected", "cancel_rejected",
    }
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_utc_timestamp(value: str, field_name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def canonical_json(value: Mapping[str, Any] | Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def payload_sha256(value: Mapping[str, Any] | Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(
    value: Any,
    field_name: str,
    *,
    uppercase: bool = False,
    lowercase: bool = False,
) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if uppercase:
        return normalized.upper()
    if lowercase:
        return normalized.lower()
    return normalized


def _optional_number(value: Any, field_name: str) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass(frozen=True)
class EventQuality:
    stale: bool = False
    sequence_gap: bool = False
    crossed_market: bool = False
    fallback: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "EventQuality":
        raw = value or {}
        return cls(
            stale=bool(raw.get("stale", False)),
            sequence_gap=bool(raw.get("sequence_gap", False)),
            crossed_market=bool(raw.get("crossed_market", False)),
            fallback=bool(raw.get("fallback", False)),
            reasons=tuple(str(item).strip() for item in raw.get("reasons", ()) if str(item).strip()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stale": self.stale,
            "sequence_gap": self.sequence_gap,
            "crossed_market": self.crossed_market,
            "fallback": self.fallback,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    event_type: str
    provider: str
    feed: str
    asset_class: str
    symbol: str
    provider_timestamp: str
    received_at: str
    normalized_at: str
    exchange: Optional[str] = None
    sequence: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    size: Optional[float] = None
    quality: EventQuality = field(default_factory=EventQuality)
    source_payload_hash: Optional[str] = None
    schema_version: str = "market-event.v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required_text(self.event_id, "event_id"))
        event_type = _required_text(self.event_type, "event_type", lowercase=True)
        if event_type not in MARKET_EVENT_TYPES:
            raise ValueError(f"unsupported market event_type: {event_type}")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "provider", _required_text(self.provider, "provider", lowercase=True))
        object.__setattr__(self, "feed", _required_text(self.feed, "feed", lowercase=True))
        asset_class = _required_text(self.asset_class, "asset_class", lowercase=True)
        if asset_class not in ASSET_CLASSES:
            raise ValueError(f"unsupported asset_class: {asset_class}")
        object.__setattr__(self, "asset_class", asset_class)
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol", uppercase=True))
        object.__setattr__(
            self, "provider_timestamp", normalize_utc_timestamp(self.provider_timestamp, "provider_timestamp")
        )
        object.__setattr__(self, "received_at", normalize_utc_timestamp(self.received_at, "received_at"))
        object.__setattr__(self, "normalized_at", normalize_utc_timestamp(self.normalized_at, "normalized_at"))
        if self.sequence is not None:
            object.__setattr__(self, "sequence", int(self.sequence))
        for name in ("bid", "ask", "last", "size"):
            object.__setattr__(self, name, _optional_number(getattr(self, name), name))
        if self.bid is not None and self.ask is not None and self.bid > self.ask and not self.quality.crossed_market:
            raise ValueError("bid above ask must be marked as crossed_market")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MarketEvent":
        raw = dict(value)
        if not isinstance(raw.get("quality"), EventQuality):
            raw["quality"] = EventQuality.from_mapping(raw.get("quality"))
        return cls(**raw)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["quality"] = self.quality.to_dict()
        return result

    def with_source_payload(self, source_payload: Mapping[str, Any]) -> "MarketEvent":
        values = self.to_dict()
        values["source_payload_hash"] = payload_sha256(dict(source_payload))
        return MarketEvent.from_dict(values)


@dataclass(frozen=True)
class NewsEvent:
    event_id: str
    provider: str
    publisher: str
    headline: str
    source_url: str
    published_at: str
    received_at: str
    normalized_at: str
    symbols: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1
    correction_status: str = "original"
    source_payload_hash: Optional[str] = None
    schema_version: str = "news-event.v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required_text(self.event_id, "event_id"))
        object.__setattr__(self, "provider", _required_text(self.provider, "provider", lowercase=True))
        if not str(self.publisher or "").strip():
            raise ValueError("publisher is required")
        if not str(self.headline or "").strip():
            raise ValueError("headline is required")
        source_url = str(self.source_url or "").strip()
        if source_url and not source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be empty or an HTTP(S) URL")
        object.__setattr__(self, "source_url", source_url)
        object.__setattr__(self, "published_at", normalize_utc_timestamp(self.published_at, "published_at"))
        object.__setattr__(self, "received_at", normalize_utc_timestamp(self.received_at, "received_at"))
        object.__setattr__(self, "normalized_at", normalize_utc_timestamp(self.normalized_at, "normalized_at"))
        object.__setattr__(self, "symbols", tuple(dict.fromkeys(str(s).strip().upper() for s in self.symbols if str(s).strip())))
        if int(self.version) < 1:
            raise ValueError("version must be >= 1")
        object.__setattr__(self, "version", int(self.version))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "NewsEvent":
        return cls(**dict(value))

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["symbols"] = list(self.symbols)
        return result


@dataclass(frozen=True)
class BrokerOrderEvent:
    event_id: str
    provider: str
    client_order_id: str
    broker_order_id: str
    event_type: str
    account_mode: str
    symbol: str
    provider_timestamp: str
    received_at: str
    filled_quantity: float = 0.0
    fill_price: Optional[float] = None
    reason: Optional[str] = None
    source_payload_hash: Optional[str] = None
    schema_version: str = "broker-order-event.v1"

    def __post_init__(self) -> None:
        for name in ("event_id", "provider", "client_order_id", "broker_order_id"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        event_type = _required_text(self.event_type, "event_type", lowercase=True)
        if event_type not in BROKER_EVENT_TYPES:
            raise ValueError(f"unsupported broker event_type: {event_type}")
        object.__setattr__(self, "event_type", event_type)
        account_mode = _required_text(self.account_mode, "account_mode", lowercase=True)
        if account_mode != "paper":
            raise ValueError("broker event account_mode must be paper")
        object.__setattr__(self, "account_mode", account_mode)
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol", uppercase=True))
        object.__setattr__(
            self, "provider_timestamp", normalize_utc_timestamp(self.provider_timestamp, "provider_timestamp")
        )
        object.__setattr__(self, "received_at", normalize_utc_timestamp(self.received_at, "received_at"))
        quantity = _optional_number(self.filled_quantity, "filled_quantity") or 0.0
        if quantity < 0:
            raise ValueError("filled_quantity must be >= 0")
        object.__setattr__(self, "filled_quantity", quantity)
        object.__setattr__(self, "fill_price", _optional_number(self.fill_price, "fill_price"))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BrokerOrderEvent":
        return cls(**dict(value))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
