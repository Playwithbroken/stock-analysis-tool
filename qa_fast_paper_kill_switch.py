from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.fast_paper_safety_service import FastPaperSafetyService
from src.integrations.contracts import MarketEvent
from src.market_event_store import MarketEventStore
from src.paper_trading_service import PaperTradingService
from src.storage import PortfolioManager
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def live_health(last_message_at: str) -> dict:
    return {
        "state": "live",
        "market": {
            "connected": True,
            "authenticated": True,
            "subscribed": True,
            "last_message_at": last_message_at,
            "last_transport_ok_at": last_message_at,
        },
    }


def test_feed_loss_pauses_once_and_never_auto_resumes() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="kill-switch-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "safety.db")
        env_patch = patch.dict(
            "os.environ",
            {"FAST_PAPER_ENABLED": "true", "MARKET_STREAM_DISCONNECT_KILL_SECONDS": "5"},
        )
        env_patch.start()
        try:
            manager = PortfolioManager()
            safety = FastPaperSafetyService(manager)
            now = datetime.now(timezone.utc)
            ready = safety.monitor_stream(live_health(now.isoformat()), now=now)
            require(ready["paused"] is False, "healthy stream paused fast-paper")

            paused = safety.monitor_stream(live_health((now - timedelta(seconds=6)).isoformat()), now=now)
            require(paused["paused"] is True, "stale stream did not trigger kill switch")
            require(paused["reason"] == "alpaca_market_stream_stale", "pause reason wrong")
            incident_id = paused["incident_id"]

            still_paused = safety.monitor_stream(live_health(now.isoformat()), now=now)
            require(still_paused["paused"] is True, "kill switch auto-resumed without review")
            require(still_paused["incident_id"] == incident_id, "repeated monitor created a new pause")
            try:
                safety.enforce_not_paused()
            except ValueError as exc:
                require("kill switch" in str(exc).lower(), "entry rejection is not actionable")
            else:
                raise AssertionError("paused fast-paper entry was allowed")

            conn = sqlite3.connect(storage.DB_PATH)
            incidents = conn.execute("SELECT COUNT(*) FROM integration_incidents").fetchone()[0]
            row = conn.execute("SELECT severity, status, incident_type FROM integration_incidents").fetchone()
            conn.close()
            require(incidents == 1, "kill switch incident was duplicated")
            require(row == ("critical", "open", "fast_paper_auto_pause"), "incident evidence wrong")
        finally:
            env_patch.stop()
            storage.DB_PATH = original_db_path


def test_fast_paper_entry_requires_valid_stream_quote() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="fast-entry-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "entry.db")
        env_patch = patch.dict(
            "os.environ",
            {"FAST_PAPER_ENABLED": "true", "FAST_REQUIRE_REGULAR_SESSION": "false"},
        )
        env_patch.start()
        try:
            manager = PortfolioManager()
            service = PaperTradingService(manager)
            try:
                service._enforce_fast_paper_entry_gate("AAPL", "equity")
            except ValueError as exc:
                require("stream_quote_missing" in str(exc), "missing-stream rejection reason wrong")
            else:
                raise AssertionError("fast-paper entry without a stream quote was allowed")

            now = datetime.now(timezone.utc).isoformat()
            MarketEventStore().append(
                MarketEvent(
                    event_id="fast-entry-quote",
                    event_type="quote",
                    provider="alpaca",
                    feed="sip",
                    asset_class="equity",
                    symbol="AAPL",
                    provider_timestamp=now,
                    received_at=now,
                    normalized_at=now,
                    bid=200.0,
                    ask=200.1,
                )
            )
            report = service._enforce_fast_paper_entry_gate("AAPL", "equity")
            require(report is not None and report["trade_allowed"] is True, "valid stream quote was blocked")
            require(report["midpoint"] == 200.05, "entry gate did not preserve stream midpoint")
        finally:
            env_patch.stop()
            storage.DB_PATH = original_db_path


if __name__ == "__main__":
    test_feed_loss_pauses_once_and_never_auto_resumes()
    test_fast_paper_entry_requires_valid_stream_quote()
    print("fast-paper kill switch QA passed")
