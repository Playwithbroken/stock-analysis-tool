from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import random
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional

import websockets

from src.integrations.contracts import EventQuality, MarketEvent, NewsEvent, utc_now_iso
from src.integrations.market_data.base import MarketDataAdapter
from src.latency_monitor_service import LatencyMonitorService
from src.market_event_store import MarketEventStore
from src.news_event_store import NewsEventStore
from src.provider_observability import classify_provider_error, record_provider_result


ALLOWED_FEEDS = frozenset({"iex", "sip", "test"})
MARKET_TYPES = frozenset({"q", "t", "b", "u", "d"})


class AlpacaStreamError(RuntimeError):
    def __init__(self, message: str, *, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AlpacaStreamConfig:
    key_id: str
    secret_key: str
    symbols: tuple[str, ...]
    feed: str = "iex"
    enabled: bool = False
    include_news: bool = True
    auth_timeout_seconds: float = 10.0
    receive_timeout_seconds: float = 45.0
    reconnect_max_seconds: float = 30.0

    def __post_init__(self) -> None:
        normalized_feed = str(self.feed or "").strip().lower()
        if normalized_feed not in ALLOWED_FEEDS:
            raise ValueError(f"unsupported Alpaca feed: {normalized_feed}")
        object.__setattr__(self, "feed", normalized_feed)
        normalized_symbols = tuple(
            dict.fromkeys(str(symbol).strip().upper() for symbol in self.symbols if str(symbol).strip())
        )
        if not normalized_symbols:
            raise ValueError("at least one Alpaca symbol is required")
        object.__setattr__(self, "symbols", normalized_symbols)
        if self.enabled and (not self.key_id.strip() or not self.secret_key.strip()):
            raise ValueError("Alpaca streaming is enabled but credentials are missing")

    @classmethod
    def from_env(cls) -> "AlpacaStreamConfig":
        enabled = os.getenv("ALPACA_MARKET_DATA_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        symbols = tuple(
            part.strip() for part in os.getenv("ALPACA_STREAM_SYMBOLS", "AAPL,SPY,QQQ").split(",")
        )
        return cls(
            key_id=os.getenv("ALPACA_API_KEY_ID", "").strip(),
            secret_key=os.getenv("ALPACA_API_SECRET_KEY", "").strip(),
            symbols=symbols,
            feed=os.getenv("ALPACA_MARKET_FEED", "iex").strip(),
            enabled=enabled,
            include_news=os.getenv("ALPACA_NEWS_STREAM_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"},
        )

    @property
    def market_url(self) -> str:
        if self.feed == "test":
            return "wss://stream.data.alpaca.markets/v2/test"
        return f"wss://stream.data.alpaca.markets/v2/{self.feed}"

    @property
    def news_url(self) -> str:
        return "wss://stream.data.alpaca.markets/v1beta1/news"


class AlpacaMarketDataAdapter(MarketDataAdapter):
    def __init__(
        self,
        config: AlpacaStreamConfig,
        market_store: Optional[MarketEventStore] = None,
        news_store: Optional[NewsEventStore] = None,
        latency_monitor: Optional[LatencyMonitorService] = None,
    ):
        self.config = config
        self.market_store = market_store or MarketEventStore()
        self.news_store = news_store or NewsEventStore()
        self.latency_monitor = latency_monitor or LatencyMonitorService()
        self._stop = asyncio.Event()
        self._health: Dict[str, Any] = {
            "provider": "alpaca",
            "feed": config.feed,
            "enabled": config.enabled,
            "state": "disabled" if not config.enabled else "configured",
            "market": self._channel_health(),
            "news": self._channel_health(),
            "market_events": 0,
            "news_events": 0,
            "duplicates": 0,
            "unsupported_messages": 0,
            "last_error": None,
        }

    @staticmethod
    def _channel_health() -> Dict[str, Any]:
        return {
            "connected": False,
            "authenticated": False,
            "subscribed": False,
            "last_message_at": None,
            "last_transport_ok_at": None,
            "last_event_at": None,
            "reconnect_count": 0,
        }

    def health(self) -> Dict[str, Any]:
        snapshot = json.loads(json.dumps(self._health))
        required_channels = [snapshot["market"]]
        if self.config.include_news:
            required_channels.append(snapshot["news"])
        if not self.config.enabled:
            snapshot["state"] = "disabled"
        elif all(channel["connected"] and channel["authenticated"] and channel["subscribed"] for channel in required_channels):
            snapshot["state"] = "live"
        elif any(channel["connected"] for channel in required_channels):
            snapshot["state"] = "degraded"
        snapshot["generated_at"] = utc_now_iso()
        snapshot["symbols"] = list(self.config.symbols)
        snapshot["credentials_present"] = bool(self.config.key_id and self.config.secret_key)
        return snapshot

    async def close(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        if not self.config.enabled:
            self._health["state"] = "disabled"
            return
        self._health["state"] = "starting"
        tasks = [asyncio.create_task(self._supervise("market"))]
        if self.config.include_news:
            tasks.append(asyncio.create_task(self._supervise("news")))
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._health["state"] = "stopped"

    async def _supervise(self, channel: str) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._run_connection(channel)
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                self._health[channel]["connected"] = False
                self._health[channel]["authenticated"] = False
                self._health[channel]["subscribed"] = False
                self._health[channel]["reconnect_count"] += 1
                self._health["state"] = "degraded"
                error_code = self._error_code(channel, exc)
                self._health["last_error"] = {
                    "channel": channel,
                    "code": error_code,
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "at": utc_now_iso(),
                }
                record_provider_result(
                    "news" if channel == "news" else "quote",
                    "alpaca",
                    f"{channel}_stream",
                    "error",
                    error_code=error_code,
                    error_type=exc.__class__.__name__,
                )
                delay = min(self.config.reconnect_max_seconds, 2 ** min(attempt, 5))
                delay *= random.uniform(0.8, 1.2)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

    async def _run_connection(self, channel: str) -> None:
        url = self.config.news_url if channel == "news" else self.config.market_url
        started = time.perf_counter()
        async with websockets.connect(
            url,
            open_timeout=self.config.auth_timeout_seconds,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_queue=4096,
        ) as websocket:
            self._health[channel]["connected"] = True
            await self._expect_control(websocket, channel, "connected")
            await websocket.send(
                json.dumps(
                    {"action": "auth", "key": self.config.key_id, "secret": self.config.secret_key},
                    separators=(",", ":"),
                )
            )
            await self._expect_control(websocket, channel, "authenticated")
            self._health[channel]["authenticated"] = True

            subscription = (
                {"action": "subscribe", "news": ["*"]}
                if channel == "news"
                else {
                    "action": "subscribe",
                    "trades": list(self.config.symbols),
                    "quotes": list(self.config.symbols),
                    "bars": list(self.config.symbols),
                }
            )
            await websocket.send(json.dumps(subscription, separators=(",", ":")))
            await self._expect_subscription(websocket, channel)
            self._health[channel]["subscribed"] = True
            self._health["state"] = "live"
            record_provider_result(
                "news" if channel == "news" else "quote",
                "alpaca",
                f"{channel}_connect",
                "ok",
                latency_ms=(time.perf_counter() - started) * 1000,
            )

            while not self._stop.is_set():
                try:
                    try:
                        disconnect_limit = max(
                            1.0,
                            float(os.getenv("MARKET_STREAM_DISCONNECT_KILL_SECONDS", "5")),
                        )
                    except (TypeError, ValueError):
                        disconnect_limit = 5.0
                    raw = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=min(self.config.receive_timeout_seconds, max(1.0, disconnect_limit / 2)),
                    )
                except asyncio.TimeoutError:
                    pong = await websocket.ping()
                    await asyncio.wait_for(pong, timeout=min(5.0, disconnect_limit))
                    self._health[channel]["last_transport_ok_at"] = utc_now_iso()
                    continue
                # SQLite work runs outside the event loop so WebSocket pings and the
                # second provider connection remain responsive during persistence.
                self._health[channel]["last_transport_ok_at"] = utc_now_iso()
                await asyncio.to_thread(self.process_message, raw, channel=channel)

    async def _expect_control(self, websocket: Any, channel: str, expected: str) -> None:
        raw = await asyncio.wait_for(websocket.recv(), timeout=self.config.auth_timeout_seconds)
        messages = self._decode_messages(raw)
        self._raise_for_errors(messages)
        if not any(item.get("T") == "success" and item.get("msg") == expected for item in messages):
            raise AlpacaStreamError(f"Alpaca {channel} stream did not confirm {expected}")
        self._health[channel]["last_message_at"] = utc_now_iso()
        self._health[channel]["last_transport_ok_at"] = utc_now_iso()

    async def _expect_subscription(self, websocket: Any, channel: str) -> None:
        raw = await asyncio.wait_for(websocket.recv(), timeout=self.config.auth_timeout_seconds)
        messages = self._decode_messages(raw)
        self._raise_for_errors(messages)
        subscription = next((item for item in messages if item.get("T") == "subscription"), None)
        if not subscription:
            raise AlpacaStreamError(f"Alpaca {channel} stream did not confirm subscriptions")
        expected_symbols = set(self.config.symbols)
        if channel == "news":
            if "*" not in set(subscription.get("news") or ()):
                raise AlpacaStreamError("Alpaca news wildcard subscription was not confirmed")
        else:
            for key in ("trades", "quotes", "bars"):
                if not expected_symbols <= set(subscription.get(key) or ()):
                    raise AlpacaStreamError(f"Alpaca did not confirm all {key} subscriptions")
        self._health[channel]["last_message_at"] = utc_now_iso()
        self._health[channel]["last_transport_ok_at"] = utc_now_iso()

    def process_message(self, raw: str | bytes | Mapping[str, Any] | Iterable[Mapping[str, Any]], *, channel: str) -> Dict[str, int]:
        messages = self._decode_messages(raw)
        self._raise_for_errors(messages)
        self._health[channel]["last_message_at"] = utc_now_iso()
        self._health[channel]["last_transport_ok_at"] = utc_now_iso()
        result = {"inserted": 0, "duplicates": 0, "unsupported": 0}
        for payload in messages:
            if payload.get("T") in {"success", "subscription"}:
                continue
            try:
                if channel == "news" and payload.get("T") == "n":
                    news_event = self.normalize_news(payload)
                    stored = self.news_store.append(news_event, dict(payload))
                    key = "inserted" if stored["inserted"] else "duplicates"
                    result[key] += 1
                    if stored["inserted"]:
                        self._health["news_events"] += 1
                        self._health[channel]["last_event_at"] = news_event.received_at
                        self._record_event_latencies(
                            news_event,
                            service="news",
                            provider_timestamp=str(payload.get("updated_at") or payload.get("created_at") or ""),
                        )
                elif channel == "market" and payload.get("T") in MARKET_TYPES:
                    market_event = self.normalize_market(payload)
                    if self.market_store.append(market_event, dict(payload)):
                        result["inserted"] += 1
                        self._health["market_events"] += 1
                        self._health[channel]["last_event_at"] = market_event.received_at
                        self._record_event_latencies(market_event, service="market_data")
                    else:
                        result["duplicates"] += 1
                else:
                    result["unsupported"] += 1
            except Exception:
                self._health["state"] = "degraded"
                raise
        self._health["duplicates"] += result["duplicates"]
        self._health["unsupported_messages"] += result["unsupported"]
        return result

    def _record_event_latencies(
        self,
        event: MarketEvent | NewsEvent,
        *,
        service: str,
        provider_timestamp: Optional[str] = None,
    ) -> None:
        try:
            sample_every = max(1, int(os.getenv("LATENCY_SAMPLE_EVERY_N_EVENTS", "10")))
        except (TypeError, ValueError):
            sample_every = 10
        sample_bucket = int(hashlib.sha256(event.event_id.encode("utf-8")).hexdigest()[:8], 16)
        if sample_bucket % sample_every:
            return
        source_timestamp = provider_timestamp or (
            event.provider_timestamp if isinstance(event, MarketEvent) else event.published_at
        )
        provider_at = datetime.fromisoformat(str(source_timestamp).replace("Z", "+00:00"))
        received_at = datetime.fromisoformat(event.received_at.replace("Z", "+00:00"))
        normalized_at = datetime.fromisoformat(event.normalized_at.replace("Z", "+00:00"))
        provider_latency = max(0.0, (received_at - provider_at).total_seconds() * 1000)
        normalize_latency = max(0.0, (normalized_at - received_at).total_seconds() * 1000)
        self.latency_monitor.record(
            provider="alpaca",
            service=service,
            segment="provider_to_receive",
            latency_ms=provider_latency,
            status="ok",
            symbol=event.symbol if isinstance(event, MarketEvent) else None,
            correlation_id=event.event_id,
            metadata={"feed": self.config.feed},
        )
        self.latency_monitor.record(
            provider="alpaca",
            service=service,
            segment="normalize",
            latency_ms=normalize_latency,
            status="ok",
            symbol=event.symbol if isinstance(event, MarketEvent) else None,
            correlation_id=event.event_id,
        )

    def normalize_market(self, payload: Mapping[str, Any]) -> MarketEvent:
        message_type = str(payload.get("T") or "")
        if message_type not in MARKET_TYPES:
            raise ValueError(f"unsupported Alpaca market message type: {message_type}")
        symbol = str(payload.get("S") or "").strip().upper()
        provider_timestamp = str(payload.get("t") or "")
        received_at = utc_now_iso()
        raw_identity = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:24]
        channel_name = {"q": "quote", "t": "trade", "b": "bar", "u": "updated_bar", "d": "daily_bar"}[message_type]
        event_id = f"{self.config.feed}:{channel_name}:{symbol}:{digest}"
        bid = payload.get("bp") if message_type == "q" else None
        ask = payload.get("ap") if message_type == "q" else None
        crossed = bid is not None and ask is not None and float(bid) > float(ask)
        exchange = payload.get("x")
        if message_type == "q":
            exchange = f"{payload.get('bx') or '?'}:{payload.get('ax') or '?'}"
        return MarketEvent(
            event_id=event_id,
            event_type="quote" if message_type == "q" else "trade" if message_type == "t" else "bar",
            provider="alpaca",
            feed=self.config.feed,
            asset_class="equity",
            symbol=symbol,
            exchange=str(exchange or "") or None,
            provider_timestamp=provider_timestamp,
            received_at=received_at,
            normalized_at=utc_now_iso(),
            sequence=int(payload["i"]) if message_type == "t" and payload.get("i") is not None else None,
            bid=bid,
            ask=ask,
            last=payload.get("p") if message_type == "t" else payload.get("c") if message_type in {"b", "u", "d"} else None,
            size=payload.get("s") if message_type == "t" else payload.get("v") if message_type in {"b", "u", "d"} else None,
            quality=EventQuality(
                crossed_market=crossed,
                reasons=("provider_crossed_quote",) if crossed else (),
            ),
        )

    def normalize_news(self, payload: Mapping[str, Any]) -> NewsEvent:
        if payload.get("T") != "n":
            raise ValueError("unsupported Alpaca news message")
        created_at = str(payload.get("created_at") or "")
        received_at = utc_now_iso()
        native_id = str(payload.get("id") or "").strip()
        if not native_id:
            raise ValueError("Alpaca news event is missing its native ID")
        headline = str(payload.get("headline") or "").strip()
        lower_headline = headline.lower()
        correction_status = "corrected" if any(
            marker in lower_headline for marker in ("correction:", "corrected:", "withdrawn", "retracted")
        ) else "original"
        return NewsEvent(
            event_id=f"news:{native_id}",
            provider="alpaca",
            publisher=str(payload.get("source") or payload.get("author") or "alpaca-news"),
            headline=headline,
            # Alpaca documents URL as optional. It is retained honestly as empty;
            # the downstream news-entry gate must reject evidence without a URL.
            source_url=str(payload.get("url") or ""),
            published_at=created_at,
            received_at=received_at,
            normalized_at=utc_now_iso(),
            symbols=tuple(payload.get("symbols") or ()),
            correction_status=correction_status,
        )

    @staticmethod
    def _decode_messages(raw: str | bytes | Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            decoded = json.loads(raw)
        elif isinstance(raw, Mapping):
            decoded = dict(raw)
        else:
            decoded = list(raw)
        values = decoded if isinstance(decoded, list) else [decoded]
        if not all(isinstance(item, dict) for item in values):
            raise AlpacaStreamError("Alpaca stream returned a non-object message")
        return [dict(item) for item in values]

    @staticmethod
    def _raise_for_errors(messages: Iterable[Mapping[str, Any]]) -> None:
        error = next((item for item in messages if item.get("T") == "error"), None)
        if error:
            code = int(error["code"]) if str(error.get("code") or "").isdigit() else None
            raise AlpacaStreamError(str(error.get("msg") or "Alpaca stream error"), code=code)

    @staticmethod
    def _error_code(channel: str, exc: Exception) -> str:
        if isinstance(exc, AlpacaStreamError):
            if exc.code in {401, 402, 403}:
                return "ALPACA_AUTH"
            if exc.code == 406:
                return "ALPACA_CONNECTION_LIMIT"
            if exc.code == 407:
                return "ALPACA_SLOW_CLIENT"
            if exc.code == 409:
                return "ALPACA_SUBSCRIPTION"
        return classify_provider_error("news" if channel == "news" else "quote", error=exc)
