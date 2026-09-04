from __future__ import annotations

from datetime import datetime, time as datetime_time, timezone
import math
import os
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from src.latency_monitor_service import LatencyMonitorService
from src.market_event_store import MarketEventStore


class MarketQualityService:
    def __init__(
        self,
        event_store: Optional[MarketEventStore] = None,
        latency_monitor: Optional[LatencyMonitorService] = None,
    ):
        self.event_store = event_store or MarketEventStore()
        self.latency_monitor = latency_monitor or LatencyMonitorService()

    def evaluate_latest(
        self,
        symbol: str,
        asset_class: str,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        started = datetime.now(timezone.utc)
        current = (now or started).astimezone(timezone.utc)
        normalized_symbol = str(symbol or "").strip().upper()
        normalized_asset = str(asset_class or "equity").strip().lower()
        blockers: List[str] = []
        warnings: List[str] = []
        event = self.event_store.latest_event(normalized_symbol, "quote")
        if event is None:
            blockers.append("stream_quote_missing")
            return self._report(normalized_symbol, normalized_asset, None, blockers, warnings, started)

        try:
            provider_time = datetime.fromisoformat(event.provider_timestamp.replace("Z", "+00:00"))
            provider_time = provider_time.astimezone(timezone.utc)
            age_ms = (current - provider_time).total_seconds() * 1000
        except (TypeError, ValueError):
            provider_time = None
            age_ms = None
            blockers.append("provider_timestamp_invalid")

        max_age_ms = self.max_quote_age_ms(normalized_asset)
        if age_ms is not None:
            if age_ms < -self._float_env("FAST_MAX_CLOCK_SKEW_MS", 1000.0, minimum=0.0):
                blockers.append("provider_timestamp_in_future")
            elif age_ms > max_age_ms:
                blockers.append("stream_quote_stale")

        bid = event.bid
        ask = event.ask
        if bid is None or ask is None:
            blockers.append("bid_ask_missing")
        elif bid <= 0 or ask <= 0:
            blockers.append("bid_ask_invalid")
        elif bid > ask:
            blockers.append("crossed_market")

        spread_bps = None
        midpoint = None
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            midpoint = (bid + ask) / 2
            spread_bps = ((ask - bid) / midpoint) * 10000 if midpoint > 0 else None
            if spread_bps is not None and spread_bps > self.max_spread_bps(normalized_asset):
                blockers.append("spread_too_wide")

        quality = event.quality
        if quality.sequence_gap:
            blockers.append("sequence_gap")
        if quality.crossed_market and "crossed_market" not in blockers:
            blockers.append("crossed_market")
        if quality.stale and "stream_quote_stale" not in blockers:
            blockers.append("provider_marked_stale")
        if quality.fallback:
            blockers.append("fallback_feed_forbidden")
        if event.provider != "alpaca":
            blockers.append("unapproved_fast_provider")
        if event.feed not in {"iex", "sip", "test"}:
            blockers.append("unapproved_fast_feed")
        if event.feed == "iex":
            warnings.append("iex_is_single_exchange_not_full_sip_market")

        if normalized_asset in {"equity", "etf"} and self._bool_env("FAST_REQUIRE_REGULAR_SESSION", True):
            if not self._is_us_regular_session(current):
                blockers.append("outside_us_regular_session")

        return self._report(
            normalized_symbol,
            normalized_asset,
            event,
            blockers,
            warnings,
            started,
            age_ms=age_ms,
            spread_bps=spread_bps,
            midpoint=midpoint,
        )

    def _report(
        self,
        symbol: str,
        asset_class: str,
        event: Any,
        blockers: List[str],
        warnings: List[str],
        started: datetime,
        *,
        age_ms: Optional[float] = None,
        spread_bps: Optional[float] = None,
        midpoint: Optional[float] = None,
    ) -> Dict[str, Any]:
        duration_ms = max(0.0, (datetime.now(timezone.utc) - started).total_seconds() * 1000)
        self.latency_monitor.record(
            provider=getattr(event, "provider", "internal"),
            service="market_quality",
            segment="risk",
            latency_ms=duration_ms,
            status="ok" if not blockers else "degraded",
            symbol=symbol,
            correlation_id=getattr(event, "event_id", None),
        )
        return {
            "schema": "market-quality.v1",
            "status": "pass" if not blockers else "no_trade",
            "trade_allowed": not blockers,
            "symbol": symbol,
            "asset_class": asset_class,
            "provider": getattr(event, "provider", None),
            "feed": getattr(event, "feed", None),
            "event_id": getattr(event, "event_id", None),
            "provider_timestamp": getattr(event, "provider_timestamp", None),
            "received_at": getattr(event, "received_at", None),
            "data_age_ms": round(age_ms, 3) if age_ms is not None and math.isfinite(age_ms) else None,
            "max_data_age_ms": self.max_quote_age_ms(asset_class),
            "bid": getattr(event, "bid", None),
            "ask": getattr(event, "ask", None),
            "midpoint": round(midpoint, 8) if midpoint is not None else None,
            "spread_bps": round(spread_bps, 3) if spread_bps is not None else None,
            "max_spread_bps": self.max_spread_bps(asset_class),
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def max_quote_age_ms(cls, asset_class: str) -> float:
        key = "FAST_CRYPTO_MAX_QUOTE_AGE_MS" if str(asset_class).lower() == "crypto" else "FAST_EQUITY_MAX_QUOTE_AGE_MS"
        default = 1000.0 if str(asset_class).lower() == "crypto" else 2000.0
        return cls._float_env(key, default, minimum=1.0)

    @classmethod
    def max_spread_bps(cls, asset_class: str) -> float:
        normalized = str(asset_class or "equity").lower()
        defaults = {"equity": 50.0, "etf": 30.0, "crypto": 100.0, "option": 250.0}
        key = f"FAST_{normalized.upper()}_MAX_SPREAD_BPS"
        return cls._float_env(key, defaults.get(normalized, 50.0), minimum=0.1)

    @staticmethod
    def _is_us_regular_session(value: datetime) -> bool:
        eastern = value.astimezone(ZoneInfo("America/New_York"))
        return eastern.weekday() < 5 and datetime_time(9, 30) <= eastern.time().replace(tzinfo=None) < datetime_time(16, 0)

    @staticmethod
    def _float_env(name: str, default: float, *, minimum: float) -> float:
        try:
            return max(minimum, float(os.getenv(name, str(default))))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bool_env(name: str, default: bool) -> bool:
        return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}
