import asyncio
import os
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main() -> int:
    source = (ROOT / "api.py").read_text(encoding="utf-8")
    block = source.split("async def build_radar_bootstrap", 1)[1].split(
        '@app.get("/api/radar/bootstrap")', 1
    )[0]
    for marker in [
        "asyncio.wait_for",
        "asyncio.to_thread",
        "asyncio.gather",
        '"radar-bootstrap-status.v1"',
        '"status": "timeout"',
        "no synthetic scores were inserted",
        "no fallback movers were invented",
        "no candidate or trade was fabricated",
    ]:
        require(marker in block, f"radar resilience contract lacks {marker}")
    require(
        "get_public_signal_service().build_watchlist_snapshot(items)" not in block,
        "watchlist provider still blocks the async request directly",
    )
    require(
        "get_morning_brief_service().get_brief_fast(snapshot)" not in block,
        "morning brief still blocks the async request directly",
    )
    require(
        "get_paper_trading_service().build_dashboard(scoreboard, settings, brief)" not in block,
        "paper dashboard still blocks the async request directly",
    )

    os.environ.update(
        {
            "APP_ACCESS_PASSWORD": "test-pass",
            "APP_SESSION_SECRET": "r" * 64,
            "APP_COOKIE_SECURE": "false",
            "TELEGRAM_ALERTS_ENABLED": "false",
            "RADAR_WATCHLIST_TIMEOUT_SECONDS": "0.01",
            "RADAR_SCOREBOARD_TIMEOUT_SECONDS": "0.01",
            "RADAR_BRIEF_TIMEOUT_SECONDS": "0.01",
            "RADAR_SESSION_LIST_TIMEOUT_SECONDS": "0.01",
            "RADAR_INTELLIGENCE_TIMEOUT_SECONDS": "0.01",
            "RADAR_LEARNING_TIMEOUT_SECONDS": "0.01",
            "RADAR_PAPER_DASHBOARD_TIMEOUT_SECONDS": "0.01",
        }
    )
    import api

    class Manager:
        def get_signal_watch_items(self):
            return [{"kind": "ticker", "value": "TEST"}]

        def get_signal_score_settings(self):
            return {}

        def get_sent_signal_events(self, limit=8):
            return []

    class PublicSignals:
        def build_watchlist_snapshot(self, items):
            time.sleep(0.05)
            return {"items": items, "ticker_signals": [{"ticker": "SHOULD_NOT_ARRIVE"}]}

    class Scores:
        async def build_scoreboard(self, snapshot, settings):
            await asyncio.sleep(0.05)
            return {"stocks": [{"ticker": "SHOULD_NOT_ARRIVE"}]}

    class Brief:
        def get_brief_fast(self, snapshot):
            time.sleep(0.05)
            return {"headline": "SHOULD_NOT_ARRIVE"}

        def build_empty_brief(self, reason):
            return {"headline": "partial", "reason": reason}

    class Sessions:
        async def build_session_lists(self, snapshot):
            await asyncio.sleep(0.05)
            return {"status": "SHOULD_NOT_ARRIVE"}

    class SlowSync:
        def build_snapshot(self, snapshot):
            time.sleep(0.05)
            return {"status": "SHOULD_NOT_ARRIVE"}

        def build_dashboard(self, *args):
            time.sleep(0.05)
            return {"status": "SHOULD_NOT_ARRIVE"}

    manager = Manager()
    api._RESPONSE_CACHE.clear()
    api.get_portfolio_manager = lambda: manager
    api.get_public_signal_service = lambda: PublicSignals()
    api.get_signal_score_service = lambda: Scores()
    api.get_morning_brief_service = lambda: Brief()
    api.get_session_list_service = lambda: Sessions()
    api.get_trading_intelligence_service = lambda: SlowSync()
    api.get_forecast_learning_service = lambda: SlowSync()
    api.get_paper_trading_service = lambda: SlowSync()

    started = time.perf_counter()
    payload = asyncio.run(api.build_radar_bootstrap(limit=8))
    elapsed = time.perf_counter() - started
    require(elapsed < 0.5, f"bounded radar response took too long: {elapsed:.3f}s")
    require(payload["bootstrap_status"]["status"] == "partial", "timed-out radar must be explicit partial")
    require(payload["scoreboard"]["stocks"] == [], "timed-out scoreboard inserted data")
    require(payload["brief"]["headline"] == "partial", "timed-out brief did not use explicit fallback")
    require(payload["paper_dashboard"]["playbooks"] == [], "timed-out paper dashboard inserted candidates")
    require(
        all(
            row.get("status") in {"timeout", "cached"}
            for row in payload["bootstrap_status"]["components"].values()
        ),
        "timed-out component status was not preserved",
    )
    print("radar bootstrap resilience QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
