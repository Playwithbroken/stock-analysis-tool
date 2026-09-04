from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import uuid
from typing import Any, Dict, Optional

import src.storage as storage


FAST_PAPER_STATE_KEY = "fast_paper_safety_state_v1"


class FastPaperSafetyService:
    def __init__(self, portfolio_manager: Any):
        self.portfolio_manager = portfolio_manager

    def status(self) -> Dict[str, Any]:
        raw = self.portfolio_manager.get_app_setting(FAST_PAPER_STATE_KEY, "{}") or "{}"
        try:
            state = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            state = {}
        return {
            "schema": "fast-paper-safety.v1",
            "enabled": os.getenv("FAST_PAPER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
            "paused": bool(state.get("paused", False)),
            "reason": state.get("reason"),
            "component": state.get("component"),
            "paused_at": state.get("paused_at"),
            "incident_id": state.get("incident_id"),
            "updated_at": state.get("updated_at"),
        }

    def pause(self, reason: str, *, component: str, provider: Optional[str] = None) -> Dict[str, Any]:
        current = self.status()
        now = datetime.now(timezone.utc).isoformat()
        if current["paused"] and current.get("reason") == reason and current.get("component") == component:
            return current
        incident_id = str(uuid.uuid4())
        state = {
            "paused": True,
            "reason": str(reason),
            "component": str(component),
            "provider": str(provider or "") or None,
            "paused_at": now,
            "incident_id": incident_id,
            "updated_at": now,
        }
        self.portfolio_manager.set_app_setting(FAST_PAPER_STATE_KEY, json.dumps(state, sort_keys=True))
        conn = storage._connect_db()
        try:
            conn.execute(
                """
                INSERT INTO integration_incidents (
                    id, provider, component, incident_type, severity, status,
                    summary, details_json, opened_at, resolved_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    provider,
                    component,
                    "fast_paper_auto_pause",
                    "critical",
                    "open",
                    str(reason),
                    json.dumps({"automatic": True, "paper_only": True}, sort_keys=True),
                    now,
                    None,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.status()

    def enforce_not_paused(self) -> None:
        state = self.status()
        if state["enabled"] and state["paused"]:
            raise ValueError(
                "Fast-paper kill switch blocks this entry: "
                + str(state.get("reason") or "market integration is paused")
            )

    def monitor_stream(self, stream_health: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
        state = self.status()
        if not state["enabled"] or state["paused"]:
            return state
        market = stream_health.get("market") if isinstance(stream_health.get("market"), dict) else {}
        if stream_health.get("state") != "live" or not market.get("connected") or not market.get("subscribed"):
            return self.pause("alpaca_market_stream_not_live", component="market_stream", provider="alpaca")
        last_message = market.get("last_transport_ok_at") or market.get("last_message_at")
        try:
            parsed = datetime.fromisoformat(str(last_message).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return self.pause("alpaca_market_heartbeat_missing", component="market_stream", provider="alpaca")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        try:
            limit = max(1.0, float(os.getenv("MARKET_STREAM_DISCONNECT_KILL_SECONDS", "5")))
        except (TypeError, ValueError):
            limit = 5.0
        if (current - parsed).total_seconds() > limit:
            return self.pause("alpaca_market_stream_stale", component="market_stream", provider="alpaca")
        return state
