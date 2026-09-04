from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.integrations.contracts import EventQuality, MarketEvent
from src.market_event_store import MarketEventStore
from src.market_quality_service import MarketQualityService
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def quote(
    event_id: str,
    provider_at: datetime,
    *,
    bid: float = 100.0,
    ask: float = 100.1,
    quality: EventQuality | None = None,
    provider: str = "alpaca",
    feed: str = "sip",
    received_at: datetime | None = None,
) -> MarketEvent:
    stamp = provider_at.astimezone(timezone.utc).isoformat()
    received_stamp = (received_at or provider_at).astimezone(timezone.utc).isoformat()
    return MarketEvent(
        event_id=event_id,
        event_type="quote",
        provider=provider,
        feed=feed,
        asset_class="equity",
        symbol="AAPL",
        provider_timestamp=stamp,
        received_at=received_stamp,
        normalized_at=received_stamp,
        bid=bid,
        ask=ask,
        quality=quality or EventQuality(),
    )


def test_market_quality_gate_blocks_bad_evidence() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="quality-gate-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "quality.db")
        env_patch = patch.dict(
            "os.environ",
            {
                "FAST_REQUIRE_REGULAR_SESSION": "false",
                "FAST_EQUITY_MAX_QUOTE_AGE_MS": "2000",
                "FAST_EQUITY_MAX_SPREAD_BPS": "50",
            },
        )
        env_patch.start()
        try:
            storage.init_db()
            store = MarketEventStore()
            service = MarketQualityService(store)
            now = datetime(2026, 8, 27, 14, 0, 0, tzinfo=timezone.utc)

            missing = service.evaluate_latest("MSFT", "equity", now=now)
            require(missing["status"] == "no_trade" and "stream_quote_missing" in missing["blockers"], "missing quote passed")

            store.append(quote("fresh", now - timedelta(milliseconds=250)))
            passed = service.evaluate_latest("AAPL", "equity", now=now)
            require(passed["trade_allowed"] is True, f"fresh quote blocked: {passed['blockers']}")
            require(passed["data_age_ms"] == 250.0 and passed["midpoint"] == 100.05, "fresh evidence metrics wrong")

            store.append(quote("stale", now - timedelta(seconds=3), received_at=now))
            stale = service.evaluate_latest("AAPL", "equity", now=now)
            require("stream_quote_stale" in stale["blockers"], "stale quote passed")

            store.append(quote("wide", now, bid=100.0, ask=102.0))
            wide = service.evaluate_latest("AAPL", "equity", now=now)
            require("spread_too_wide" in wide["blockers"], "wide spread passed")

            store.append(
                quote(
                    "crossed",
                    now,
                    bid=101.0,
                    ask=100.0,
                    quality=EventQuality(crossed_market=True, reasons=("provider_crossed_quote",)),
                )
            )
            crossed = service.evaluate_latest("AAPL", "equity", now=now)
            require("crossed_market" in crossed["blockers"], "crossed market passed")

            store.append(quote("fallback", now, provider="yfinance", feed="research_fallback", quality=EventQuality(fallback=True)))
            fallback = service.evaluate_latest("AAPL", "equity", now=now)
            require("fallback_feed_forbidden" in fallback["blockers"], "fallback feed passed")
            require("unapproved_fast_provider" in fallback["blockers"], "unapproved provider passed")
        finally:
            env_patch.stop()
            storage.DB_PATH = original_db_path


if __name__ == "__main__":
    test_market_quality_gate_blocks_bad_evidence()
    print("market staleness and quality gate QA passed")
