from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional

import src.storage as storage


LATENCY_SEGMENTS = frozenset(
    {"provider_to_receive", "normalize", "signal", "risk", "submit_ack", "fill", "telegram"}
)


def _percentile(values: Iterable[float], percentile: float) -> Optional[float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return round(ordered[index], 2)


class LatencyMonitorService:
    def record(
        self,
        *,
        provider: str,
        service: str,
        segment: str,
        latency_ms: float,
        status: str = "ok",
        symbol: Optional[str] = None,
        correlation_id: Optional[str] = None,
        observed_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_segment = str(segment or "").strip().lower()
        if normalized_segment not in LATENCY_SEGMENTS:
            raise ValueError(f"unsupported latency segment: {normalized_segment}")
        value = float(latency_ms)
        if not math.isfinite(value) or value < 0:
            raise ValueError("latency_ms must be finite and non-negative")
        timestamp = observed_at or datetime.now(timezone.utc).isoformat()
        conn = storage._connect_db()
        try:
            cursor = conn.execute(
                """
                INSERT INTO latency_samples (
                    correlation_id, provider, service, segment, latency_ms,
                    status, symbol, observed_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correlation_id,
                    str(provider or "unknown").strip().lower(),
                    str(service or "unknown").strip().lower(),
                    normalized_segment,
                    round(value, 3),
                    str(status or "ok").strip().lower(),
                    str(symbol or "").strip().upper() or None,
                    timestamp,
                    json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                ),
            )
            if int(cursor.lastrowid or 0) % 500 == 0:
                try:
                    retention_hours = max(1, int(os.getenv("LATENCY_RETENTION_HOURS", "168")))
                except (TypeError, ValueError):
                    retention_hours = 168
                cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
                conn.execute("DELETE FROM latency_samples WHERE observed_at < ?", (cutoff.isoformat(),))
            conn.commit()
            return {"id": cursor.lastrowid, "segment": normalized_segment, "latency_ms": round(value, 3)}
        finally:
            conn.close()

    def snapshot(self, *, window_minutes: int = 60) -> Dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(window_minutes)))
        conn = storage._connect_db(row_factory=True)
        try:
            rows = conn.execute(
                "SELECT * FROM latency_samples WHERE observed_at >= ? ORDER BY observed_at ASC, id ASC",
                (since.isoformat(),),
            ).fetchall()
        finally:
            conn.close()
        groups: Dict[str, List[Any]] = {}
        for row in rows:
            groups.setdefault(str(row["segment"]), []).append(row)
        segments: Dict[str, Any] = {}
        for segment in sorted(LATENCY_SEGMENTS):
            items = groups.get(segment, [])
            values = [float(item["latency_ms"]) for item in items]
            budget = self.budget_ms(segment)
            violations = sum(1 for value in values if value > budget)
            segments[segment] = {
                "samples": len(values),
                "p50_ms": _percentile(values, 0.50),
                "p95_ms": _percentile(values, 0.95),
                "p99_ms": _percentile(values, 0.99),
                "max_ms": round(max(values), 2) if values else None,
                "budget_ms": budget,
                "violations": violations,
                "status": "not_observed" if not values else "degraded" if violations else "ok",
            }
        return {
            "schema": "latency-monitor.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_minutes": max(1, int(window_minutes)),
            "sample_count": len(rows),
            "segments": segments,
        }

    @staticmethod
    def budget_ms(segment: str) -> float:
        defaults = {
            "provider_to_receive": 2000.0,
            "normalize": 100.0,
            "signal": 500.0,
            "risk": 250.0,
            "submit_ack": 2000.0,
            "fill": 5000.0,
            "telegram": 5000.0,
        }
        key = f"LATENCY_BUDGET_{segment.upper()}_MS"
        try:
            return max(1.0, float(os.getenv(key, str(defaults[segment]))))
        except (TypeError, ValueError):
            return defaults[segment]
