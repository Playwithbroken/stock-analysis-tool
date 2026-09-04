from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any, Dict, List

from src.data_fetcher import DataFetcher
from src.market_event_store import MarketEventStore
from src.provider_observability import record_provider_result


class RealtimeMarketService:
    MAX_SYMBOLS = 18

    def __init__(self, event_store: MarketEventStore | None = None):
        self.event_store = event_store or MarketEventStore()

    def build_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        started = time.perf_counter()
        cleaned: List[str] = []
        for symbol in symbols:
            normalized = (symbol or "").strip().upper()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        cleaned = cleaned[: self.MAX_SYMBOLS]

        now = datetime.now(timezone.utc)
        quotes = [item for item in (self._build_quote(symbol) for symbol in cleaned) if item]
        stale_seconds: Dict[str, int] = {}
        for quote in quotes:
            symbol = str(quote.get("symbol") or "").upper()
            updated_raw = quote.get("updated_at")
            if not symbol or not updated_raw:
                continue
            try:
                updated_at = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
                stale_seconds[symbol] = max(0, int((now - updated_at).total_seconds()))
            except Exception:
                continue

        all_streaming = bool(quotes) and all(quote.get("streaming") is True for quote in quotes)
        if not quotes:
            connection_state = "degraded"
        elif not all_streaming or any(seconds > 20 for seconds in stale_seconds.values()):
            connection_state = "snapshot"
        else:
            connection_state = "live"

        result = {
            "type": "realtime_snapshot",
            "generated_at": now.isoformat(),
            "connection_state": connection_state,
            "stale_seconds": stale_seconds,
            "quotes": quotes,
        }
        metric_status = "ok" if connection_state == "live" else "degraded"
        record_provider_result(
            "quote",
            "realtime_aggregator",
            "build_snapshot",
            metric_status,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=None if metric_status == "ok" else "QUOTE_STALE_OR_EMPTY",
        )
        return result

    def _build_quote(self, symbol: str) -> Dict[str, Any] | None:
        stream_quote = self._build_stream_quote(symbol)
        if stream_quote is not None:
            return stream_quote
        try:
            fetcher = DataFetcher(symbol)
            price_data = fetcher.get_price_data()
            info = fetcher.info
            volatility = fetcher.get_volatility_data()
            news = fetcher.get_news()

            price = (
                price_data.get("current_price")
                or info.get("currentPrice")
                or info.get("regularMarketPrice")
            )
            if price is None:
                return None

            headline = None
            publisher = None
            if news:
                headline = news[0].get("title")
                publisher = news[0].get("publisher")

            return {
                "symbol": symbol,
                "price": round(float(price), 4),
                "change_1w": self._safe_round(price_data.get("change_1w")),
                "change_1m": self._safe_round(price_data.get("change_1m")),
                "volume_ratio": self._safe_round(volatility.get("volume_ratio")),
                "asset_class": self._infer_asset_class(symbol, info),
                "currency": info.get("currency") or price_data.get("currency") or "USD",
                "headline": headline,
                "publisher": publisher,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "yfinance",
                "feed": "research_fallback",
                "streaming": False,
            }
        except Exception:
            return None

    def _build_stream_quote(self, symbol: str) -> Dict[str, Any] | None:
        try:
            event = self.event_store.latest_valid_event(symbol, "quote")
            if event is None:
                return None
            provider_time = datetime.fromisoformat(event.provider_timestamp.replace("Z", "+00:00"))
            age_seconds = max(0.0, (datetime.now(timezone.utc) - provider_time).total_seconds())
            try:
                max_age_seconds = max(1.0, float(os.getenv("ALPACA_SNAPSHOT_MAX_AGE_SECONDS", "20")))
            except (TypeError, ValueError):
                max_age_seconds = 20.0
            if age_seconds > max_age_seconds:
                return None
            if event.bid is not None and event.ask is not None:
                price = (event.bid + event.ask) / 2
            else:
                price = event.last
            if price is None:
                return None
            return {
                "symbol": event.symbol,
                "price": round(float(price), 4),
                "bid": event.bid,
                "ask": event.ask,
                "asset_class": event.asset_class,
                "currency": "USD",
                "updated_at": event.provider_timestamp,
                "received_at": event.received_at,
                "data_age_ms": round(age_seconds * 1000, 1),
                "source": event.provider,
                "feed": event.feed,
                "exchange": event.exchange,
                "streaming": True,
                "event_id": event.event_id,
            }
        except Exception:
            return None

    def _safe_round(self, value: Any, digits: int = 2) -> float | None:
        try:
            if value is None:
                return None
            return round(float(value), digits)
        except Exception:
            return None

    def _infer_asset_class(self, symbol: str, info: Dict[str, Any]) -> str:
        quote_type = (info.get("quoteType") or "").upper()
        if symbol.endswith("-USD") or quote_type == "CRYPTOCURRENCY":
            return "crypto"
        if quote_type == "ETF":
            return "etf"
        if quote_type in {"INDEX", "MUTUALFUND"} or symbol.startswith("^") or symbol.endswith("=F"):
            return "macro"
        return "equity"
