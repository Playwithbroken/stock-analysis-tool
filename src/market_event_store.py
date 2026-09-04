from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Dict, Iterable, List, Optional

from src.integrations.contracts import MarketEvent, canonical_json
import src.storage as storage


class MarketEventStore:
    """Append-only, idempotent persistence and deterministic replay for market events."""

    def append(self, event: MarketEvent, source_payload: Optional[Dict[str, Any]] = None) -> bool:
        raw_payload = dict(source_payload or {})
        event_to_store = event.with_source_payload(raw_payload) if raw_payload else event
        values = event_to_store.to_dict()
        quality_json = canonical_json(values["quality"])
        raw_payload_json = canonical_json(raw_payload)

        conn = storage._connect_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO market_events (
                    provider, event_id, schema_version, event_type, feed, asset_class,
                    symbol, exchange, provider_timestamp, received_at, normalized_at,
                    sequence, bid, ask, last, size, quality_json,
                    source_payload_hash, source_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_to_store.provider,
                    event_to_store.event_id,
                    event_to_store.schema_version,
                    event_to_store.event_type,
                    event_to_store.feed,
                    event_to_store.asset_class,
                    event_to_store.symbol,
                    event_to_store.exchange,
                    event_to_store.provider_timestamp,
                    event_to_store.received_at,
                    event_to_store.normalized_at,
                    event_to_store.sequence,
                    event_to_store.bid,
                    event_to_store.ask,
                    event_to_store.last,
                    event_to_store.size,
                    quality_json,
                    event_to_store.source_payload_hash,
                    raw_payload_json,
                ),
            )
            inserted = cursor.rowcount == 1
            if not inserted and event_to_store.source_payload_hash:
                existing = cursor.execute(
                    "SELECT source_payload_hash FROM market_events WHERE provider = ? AND event_id = ?",
                    (event_to_store.provider, event_to_store.event_id),
                ).fetchone()
                existing_hash = existing[0] if existing else None
                if existing_hash and existing_hash != event_to_store.source_payload_hash:
                    raise ValueError(
                        "provider event ID collision: identical provider/event_id has a different payload hash"
                    )
            conn.commit()
            return inserted
        finally:
            conn.close()

    def append_many(self, events: Iterable[MarketEvent]) -> Dict[str, int]:
        inserted = 0
        duplicates = 0
        for event in events:
            if self.append(event):
                inserted += 1
            else:
                duplicates += 1
        return {"inserted": inserted, "duplicates": duplicates}

    def list_events(
        self,
        *,
        provider: Optional[str] = None,
        symbol: Optional[str] = None,
        event_type: Optional[str] = None,
        after_received_at: Optional[str] = None,
        limit: int = 1000,
    ) -> List[MarketEvent]:
        clauses: List[str] = []
        params: List[Any] = []
        if provider:
            clauses.append("provider = ?")
            params.append(str(provider).strip().lower())
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).strip().upper())
        if event_type:
            clauses.append("event_type = ?")
            params.append(str(event_type).strip().lower())
        if after_received_at:
            clauses.append("received_at >= ?")
            params.append(str(after_received_at))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 10000))
        params.append(safe_limit)

        conn = storage._connect_db(row_factory=True)
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM market_events
                {where_sql}
                ORDER BY received_at ASC, id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    def replay(
        self,
        consumer: Callable[[MarketEvent], None],
        **filters: Any,
    ) -> int:
        events = self.list_events(**filters)
        for event in events:
            consumer(event)
        return len(events)

    def latest_valid_event(self, symbol: str, event_type: str = "quote") -> Optional[MarketEvent]:
        events = self._latest_events(symbol, event_type)
        for event in events:
            quality = event.quality
            if not (quality.stale or quality.sequence_gap or quality.crossed_market or quality.fallback):
                return event
        return None

    def latest_event(self, symbol: str, event_type: str = "quote") -> Optional[MarketEvent]:
        events = self._latest_events(symbol, event_type, limit=1)
        return events[0] if events else None

    def _latest_events(self, symbol: str, event_type: str, limit: int = 100) -> List[MarketEvent]:
        conn = storage._connect_db(row_factory=True)
        try:
            rows = conn.execute(
                """
                SELECT * FROM market_events
                WHERE symbol = ? AND event_type = ?
                ORDER BY received_at DESC, id DESC
                LIMIT ?
                """,
                (
                    str(symbol).strip().upper(),
                    str(event_type).strip().lower(),
                    max(1, min(int(limit), 1000)),
                ),
            ).fetchall()
            return [self._row_to_event(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> MarketEvent:
        return MarketEvent.from_dict(
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "provider": row["provider"],
                "feed": row["feed"],
                "asset_class": row["asset_class"],
                "symbol": row["symbol"],
                "exchange": row["exchange"],
                "provider_timestamp": row["provider_timestamp"],
                "received_at": row["received_at"],
                "normalized_at": row["normalized_at"],
                "sequence": row["sequence"],
                "bid": row["bid"],
                "ask": row["ask"],
                "last": row["last"],
                "size": row["size"],
                "quality": json.loads(row["quality_json"] or "{}"),
                "source_payload_hash": row["source_payload_hash"],
                "schema_version": row["schema_version"],
            }
        )
