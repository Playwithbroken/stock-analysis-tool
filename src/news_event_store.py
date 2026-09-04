from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, Dict, List, Optional

from src.integrations.contracts import NewsEvent, canonical_json, payload_sha256
import src.storage as storage


class NewsEventStore:
    """Versioned, idempotent storage for provider-native news events."""

    def append(self, event: NewsEvent, source_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raw_payload = dict(source_payload or {})
        incoming_hash = payload_sha256(raw_payload) if raw_payload else event.source_payload_hash
        conn = storage._connect_db(row_factory=True)
        try:
            latest = conn.execute(
                """
                SELECT version, source_payload_hash
                FROM news_events
                WHERE provider = ? AND event_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (event.provider, event.event_id),
            ).fetchone()
            if latest and incoming_hash and latest["source_payload_hash"] == incoming_hash:
                return {"inserted": False, "duplicate": True, "version": int(latest["version"])}

            version = int(latest["version"]) + 1 if latest else max(1, int(event.version))
            correction_status = event.correction_status
            if latest and correction_status == "original":
                correction_status = "updated"
            stored = replace(
                event,
                version=version,
                correction_status=correction_status,
                source_payload_hash=incoming_hash,
            )
            cursor = conn.execute(
                """
                INSERT INTO news_events (
                    provider, event_id, schema_version, publisher, headline, source_url,
                    published_at, received_at, normalized_at, symbols_json, version,
                    correction_status, source_payload_hash, source_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.provider,
                    stored.event_id,
                    stored.schema_version,
                    stored.publisher,
                    stored.headline,
                    stored.source_url,
                    stored.published_at,
                    stored.received_at,
                    stored.normalized_at,
                    canonical_json({"symbols": list(stored.symbols)}),
                    stored.version,
                    stored.correction_status,
                    stored.source_payload_hash,
                    canonical_json(raw_payload),
                ),
            )
            conn.commit()
            return {"inserted": cursor.rowcount == 1, "duplicate": False, "version": version}
        finally:
            conn.close()

    def list_events(self, *, provider: Optional[str] = None, limit: int = 500) -> List[NewsEvent]:
        clauses = "WHERE provider = ?" if provider else ""
        params: List[Any] = [str(provider).strip().lower()] if provider else []
        params.append(max(1, min(int(limit), 5000)))
        conn = storage._connect_db(row_factory=True)
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM news_events
                {clauses}
                ORDER BY received_at ASC, id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
            result: List[NewsEvent] = []
            for row in rows:
                symbols_payload = json.loads(row["symbols_json"] or "{}")
                result.append(
                    NewsEvent(
                        event_id=row["event_id"],
                        provider=row["provider"],
                        publisher=row["publisher"],
                        headline=row["headline"],
                        source_url=row["source_url"],
                        published_at=row["published_at"],
                        received_at=row["received_at"],
                        normalized_at=row["normalized_at"],
                        symbols=tuple(symbols_payload.get("symbols") or ()),
                        version=row["version"],
                        correction_status=row["correction_status"],
                        source_payload_hash=row["source_payload_hash"],
                        schema_version=row["schema_version"],
                    )
                )
            return result
        finally:
            conn.close()

