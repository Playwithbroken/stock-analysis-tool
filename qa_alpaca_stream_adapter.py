from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import tempfile
from pathlib import Path

from src.integrations.market_data.alpaca import (
    AlpacaMarketDataAdapter,
    AlpacaStreamConfig,
    AlpacaStreamError,
)
from src.market_event_store import MarketEventStore
from src.news_event_store import NewsEventStore
from src.realtime_market_service import RealtimeMarketService
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def config(**overrides) -> AlpacaStreamConfig:
    values = {
        "key_id": "paper-key",
        "secret_key": "paper-secret",
        "symbols": ("aapl", "SPY", "AAPL"),
        "feed": "iex",
        "enabled": False,
        "include_news": True,
    }
    values.update(overrides)
    return AlpacaStreamConfig(**values)


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def recv(self):
        return self.messages.pop(0)

    async def send(self, value):
        self.sent.append(json.loads(value))


def test_safe_config_and_secret_free_health() -> None:
    cfg = config()
    require(cfg.symbols == ("AAPL", "SPY"), "symbols must normalize and deduplicate")
    require(cfg.market_url.endswith("/v2/iex"), "IEX endpoint is wrong")
    test_cfg = config(feed="test", symbols=("FAKEPACA",))
    require(test_cfg.market_url.endswith("/v2/test"), "test endpoint is wrong")
    try:
        config(enabled=True, key_id="", secret_key="")
    except ValueError:
        pass
    else:
        raise AssertionError("enabled stream without credentials must fail closed")
    try:
        config(feed="unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown feed must be rejected")

    health_text = json.dumps(AlpacaMarketDataAdapter(cfg).health())
    require("paper-key" not in health_text and "paper-secret" not in health_text, "health leaked secrets")
    require('"credentials_present": true' in health_text, "health must expose safe config presence")


def test_official_market_fixtures_normalize_and_persist() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="alpaca-stream-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "alpaca.db")
        try:
            storage.init_db()
            adapter = AlpacaMarketDataAdapter(config())
            fixtures = [
                {
                    "T": "q", "S": "AAPL", "bx": "K", "bp": 230.10, "bs": 2,
                    "ax": "Q", "ap": 230.12, "as": 1,
                    "t": "2026-08-27T12:00:00.123456789Z", "c": ["R"], "z": "C",
                },
                {
                    "T": "t", "S": "AAPL", "i": 628, "x": "K", "p": 230.11,
                    "s": 3, "c": ["@", "F"], "z": "C",
                    "t": "2026-08-27T12:00:00.223456789Z",
                },
                {
                    "T": "b", "S": "AAPL", "o": 230.0, "h": 230.2, "l": 229.9,
                    "c": 230.11, "v": 205, "n": 16, "vw": 230.05,
                    "t": "2026-08-27T12:00:00Z",
                },
            ]
            result = adapter.process_message(json.dumps(fixtures), channel="market")
            require(result == {"inserted": 3, "duplicates": 0, "unsupported": 0}, "fixture counts wrong")
            duplicate = adapter.process_message(fixtures[0], channel="market")
            require(duplicate["duplicates"] == 1, "duplicate quote must not insert")

            events = MarketEventStore().list_events(provider="alpaca", symbol="AAPL")
            require([item.event_type for item in events] == ["quote", "trade", "bar"], "event types wrong")
            require(events[0].bid == 230.10 and events[0].ask == 230.12, "quote values wrong")
            require(events[0].exchange == "K:Q", "bid/ask exchange evidence missing")
            require(events[1].sequence == 628 and events[1].last == 230.11, "trade evidence wrong")
            require(events[2].last == 230.11 and events[2].size == 205, "bar evidence wrong")
            require(events[0].provider_timestamp.endswith("+00:00"), "provider time must normalize to UTC")
        finally:
            storage.DB_PATH = original_db_path


def test_news_fixture_is_versioned_and_deduplicated() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="alpaca-news-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "news.db")
        try:
            storage.init_db()
            adapter = AlpacaMarketDataAdapter(config())
            fixture = {
                "T": "n",
                "id": 40892639,
                "headline": "Issuer raises full-year guidance",
                "summary": "Guidance increased after results.",
                "author": "Example Newsdesk",
                "created_at": "2026-08-27T12:00:00Z",
                "updated_at": "2026-08-27T12:00:01Z",
                "url": "https://example.com/news/40892639",
                "content": "<p>Issuer raised guidance.</p>",
                "symbols": ["AAPL"],
                "source": "example-wire",
            }
            first = adapter.process_message([fixture], channel="news")
            second = adapter.process_message([fixture], channel="news")
            require(first["inserted"] == 1 and second["duplicates"] == 1, "news dedupe failed")

            update = {**fixture, "headline": "CORRECTION: Issuer confirms full-year guidance", "updated_at": "2026-08-27T12:05:00Z"}
            third = adapter.process_message([update], channel="news")
            require(third["inserted"] == 1, "material news update must create a version")
            rows = NewsEventStore().list_events(provider="alpaca")
            require([row.version for row in rows] == [1, 2], "news versions wrong")
            require(rows[1].correction_status == "corrected", "correction status missing")

            conn = sqlite3.connect(storage.DB_PATH)
            raw = conn.execute("SELECT source_payload_json FROM news_events WHERE version = 2").fetchone()[0]
            conn.close()
            require("CORRECTION" in raw and "updated_at" in raw, "news raw evidence missing")
        finally:
            storage.DB_PATH = original_db_path


def test_realtime_snapshot_prefers_fresh_stream_evidence() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="alpaca-snapshot-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "snapshot.db")
        try:
            storage.init_db()
            now = datetime.now(timezone.utc).isoformat()
            adapter = AlpacaMarketDataAdapter(config())
            adapter.process_message(
                {
                    "T": "q", "S": "AAPL", "bx": "K", "bp": 230.10, "bs": 2,
                    "ax": "Q", "ap": 230.14, "as": 1, "t": now, "c": ["R"], "z": "C",
                },
                channel="market",
            )
            service = RealtimeMarketService(MarketEventStore())
            snapshot = service.build_snapshot(["AAPL"])
            require(snapshot["connection_state"] == "live", "fresh stream quote must be live")
            quote = snapshot["quotes"][0]
            require(quote["source"] == "alpaca" and quote["feed"] == "iex", "stream provenance missing")
            require(quote["price"] == 230.12, "stream midpoint is wrong")

            stale_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            stale_adapter = AlpacaMarketDataAdapter(config())
            stale_adapter.process_message(
                {
                    "T": "q", "S": "MSFT", "bx": "K", "bp": 510.0, "bs": 1,
                    "ax": "Q", "ap": 510.2, "as": 1, "t": stale_time, "c": ["R"], "z": "C",
                },
                channel="market",
            )
            require(service._build_stream_quote("MSFT") is None, "stale stream quote must not be exposed")
        finally:
            storage.DB_PATH = original_db_path


async def test_control_and_subscription_contracts() -> None:
    adapter = AlpacaMarketDataAdapter(config())
    market = FakeWebSocket(
        [
            '[{"T":"success","msg":"connected"}]',
            '[{"T":"subscription","trades":["AAPL","SPY"],"quotes":["AAPL","SPY"],"bars":["AAPL","SPY"]}]',
        ]
    )
    await adapter._expect_control(market, "market", "connected")
    await adapter._expect_subscription(market, "market")

    news = FakeWebSocket(['[{"T":"subscription","news":["*"]}]'])
    await adapter._expect_subscription(news, "news")

    error = FakeWebSocket(['[{"T":"error","code":409,"msg":"insufficient subscription"}]'])
    try:
        await adapter._expect_control(error, "market", "connected")
    except AlpacaStreamError as exc:
        require(exc.code == 409, "provider error code must survive parsing")
        require(adapter._error_code("market", exc) == "ALPACA_SUBSCRIPTION", "error taxonomy wrong")
    else:
        raise AssertionError("provider stream error must propagate")


if __name__ == "__main__":
    test_safe_config_and_secret_free_health()
    test_official_market_fixtures_normalize_and_persist()
    test_news_fixture_is_versioned_and_deduplicated()
    test_realtime_snapshot_prefers_fresh_stream_evidence()
    asyncio.run(test_control_and_subscription_contracts())
    print("Alpaca stream adapter QA passed")
