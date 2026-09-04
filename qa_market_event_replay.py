from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from src.integrations.contracts import EventQuality, MarketEvent, payload_sha256
from src.market_event_store import MarketEventStore
import src.storage as storage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def event(event_id: str, received_at: str, *, stale: bool = False) -> MarketEvent:
    return MarketEvent(
        event_id=event_id,
        event_type="quote",
        provider="alpaca",
        feed="iex",
        asset_class="equity",
        symbol="AAPL",
        exchange="NASDAQ",
        provider_timestamp=received_at,
        received_at=received_at,
        normalized_at=received_at,
        sequence=int(event_id.rsplit("-", 1)[-1]),
        bid=230.0,
        ask=230.1,
        quality=EventQuality(stale=stale, reasons=("qa_stale",) if stale else ()),
    )


def test_schema_idempotency_replay_and_latest_valid() -> None:
    original_db_path = storage.DB_PATH
    with tempfile.TemporaryDirectory(prefix="market-event-qa-") as temp_dir:
        storage.DB_PATH = str(Path(temp_dir) / "events.db")
        try:
            storage.init_db()
            conn = sqlite3.connect(storage.DB_PATH)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            required = {
                "market_events",
                "news_events",
                "signal_decisions",
                "broker_orders",
                "broker_order_events",
                "broker_positions_snapshots",
                "latency_samples",
                "integration_incidents",
            }
            require(required <= tables, f"real-time schema missing: {sorted(required - tables)}")

            store = MarketEventStore()
            first = event("quote-1", "2026-08-27T12:00:00+00:00")
            second = event("quote-2", "2026-08-27T12:00:01+00:00", stale=True)
            third = event("quote-3", "2026-08-27T12:00:02+00:00")
            raw_payload = {"T": "q", "S": "AAPL", "bp": 230.0, "ap": 230.1}
            require(store.append(first, raw_payload), "first provider event must insert")
            require(not store.append(first, raw_payload), "duplicate provider event must be ignored")
            try:
                store.append(first, {**raw_payload, "bp": 229.0})
            except ValueError as exc:
                require("collision" in str(exc), "payload collision must remain diagnosable")
            else:
                raise AssertionError("same provider event ID with changed payload must not be ignored")
            result = store.append_many([second, third, third])
            require(result == {"inserted": 2, "duplicates": 1}, "batch idempotency counts wrong")

            rows = store.list_events(symbol="aapl")
            require([row.event_id for row in rows] == ["quote-1", "quote-2", "quote-3"], "replay order changed")
            require(rows[0].source_payload_hash == payload_sha256(raw_payload), "raw payload hash missing")

            replayed = []
            replay_count = store.replay(replayed.append, provider="ALPACA")
            require(replay_count == 3, "replay count wrong")
            require([row.to_dict() for row in replayed] == [row.to_dict() for row in rows], "replay is not deterministic")

            latest = store.latest_valid_event("aapl")
            require(latest is not None and latest.event_id == "quote-3", "latest valid event selection wrong")

            conn = sqlite3.connect(storage.DB_PATH)
            count = conn.execute("SELECT COUNT(*) FROM market_events").fetchone()[0]
            stored_payload = conn.execute(
                "SELECT source_payload_json FROM market_events WHERE event_id = 'quote-1'"
            ).fetchone()[0]
            conn.close()
            require(count == 3, "database contains duplicate events")
            require('"S":"AAPL"' in stored_payload, "canonical source payload was not retained")
        finally:
            storage.DB_PATH = original_db_path


if __name__ == "__main__":
    test_schema_idempotency_replay_and_latest_valid()
    print("market event replay QA passed")
