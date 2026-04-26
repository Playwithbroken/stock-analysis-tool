from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.data_fetcher import DataFetcher
from src.storage import PortfolioManager


DEFAULT_HORIZONS_HOURS = (1, 24, 72, 120)


class ForecastLearningService:
    """Tracks briefing setups as measurable forecasts and evaluates outcomes."""

    def __init__(self, portfolio_manager: PortfolioManager | None = None) -> None:
        self.portfolio_manager = portfolio_manager or PortfolioManager()

    def record_brief_forecasts(
        self,
        brief: Dict[str, Any],
        session_label: str = "global",
        delivery_key: Optional[str] = None,
        limit: int = 8,
    ) -> Dict[str, Any]:
        setups = self._collect_forecast_setups(brief, limit=max(1, int(limit)))
        generated_at = str(brief.get("generated_at") or datetime.utcnow().isoformat())
        created_at = datetime.utcnow().isoformat()
        recorded = 0
        skipped = 0

        for index, setup in enumerate(setups):
            symbol = str(setup.get("symbol") or "").strip().upper()
            if not symbol:
                skipped += 1
                continue

            entry_price = self._get_current_price(symbol)
            if entry_price is None:
                skipped += 1
                continue

            setup_id = setup.get("setup_id") or setup.get("rank") or index
            raw_key = f"{delivery_key or generated_at}:{session_label}:{symbol}:{setup_id}:{setup.get('trigger') or ''}"
            signal_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:28]
            forecast_id = f"fc_{signal_key}"
            forecast_time = self._parse_datetime(generated_at) or datetime.utcnow()
            source_label = self._infer_source(setup)
            metadata = {
                "setup_id": setup_id,
                "catalysts": setup.get("catalysts") or [],
                "congress_signal": setup.get("congress_signal"),
                "product_catalyst": setup.get("product_catalyst"),
                "decision_quality": setup.get("decision_quality"),
                "size_guidance": setup.get("size_guidance"),
            }
            forecast = {
                "id": forecast_id,
                "signal_key": signal_key,
                "symbol": symbol,
                "direction": self._normalize_direction(setup),
                "setup_type": str(setup.get("setup_type") or "briefing_setup"),
                "session_label": session_label,
                "source_label": source_label,
                "thesis": self._truncate(setup.get("thesis"), 1000),
                "trigger": self._truncate(setup.get("trigger"), 700),
                "invalidation": self._truncate(setup.get("invalidation"), 700),
                "confidence": self._safe_float(setup.get("confidence")),
                "rank_score": self._safe_float(setup.get("rank_score")),
                "expected_move": self._truncate(setup.get("expected_move"), 120),
                "entry_price": entry_price,
                "forecast_time": forecast_time.isoformat(),
                "metadata_json": json.dumps(metadata, ensure_ascii=True, default=str),
                "created_at": created_at,
            }
            outcomes = [
                {
                    "id": f"{forecast_id}_{hours}h",
                    "forecast_id": forecast_id,
                    "horizon_hours": int(hours),
                    "due_at": (forecast_time + timedelta(hours=int(hours))).isoformat(),
                    "status": "pending",
                    "result": None,
                    "checked_at": None,
                    "exit_price": None,
                    "performance_pct": None,
                    "notes": None,
                }
                for hours in DEFAULT_HORIZONS_HOURS
            ]
            if self.portfolio_manager.upsert_signal_forecast(forecast, outcomes):
                recorded += 1
            else:
                skipped += 1

        return {
            "status": "ok",
            "recorded": recorded,
            "skipped": skipped,
            "session_label": session_label,
            "delivery_key": delivery_key,
        }

    def evaluate_due_forecasts(self, limit: int = 60) -> Dict[str, Any]:
        due_items = self.portfolio_manager.list_due_signal_forecast_outcomes(limit=limit)
        evaluated = 0
        pending_data = 0
        errors: List[str] = []

        for item in due_items:
            outcome_id = str(item.get("id") or "")
            symbol = str(item.get("symbol") or "").upper()
            entry_price = self._safe_float(item.get("entry_price"))
            if not outcome_id or not symbol or not entry_price:
                continue
            current_price = self._get_current_price(symbol)
            checked_at = datetime.utcnow().isoformat()
            if current_price is None:
                pending_data += 1
                self.portfolio_manager.update_signal_forecast_outcome(
                    outcome_id,
                    {
                        "status": "pending_data",
                        "checked_at": checked_at,
                        "notes": "Price data unavailable; outcome not scored.",
                    },
                )
                continue

            performance_pct = ((current_price / entry_price) - 1) * 100
            result, notes = self._score_result(
                performance_pct,
                str(item.get("direction") or ""),
                int(item.get("horizon_hours") or 0),
            )
            try:
                self.portfolio_manager.update_signal_forecast_outcome(
                    outcome_id,
                    {
                        "status": "evaluated",
                        "result": result,
                        "checked_at": checked_at,
                        "exit_price": current_price,
                        "performance_pct": performance_pct,
                        "notes": notes,
                    },
                )
                evaluated += 1
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")

        return {
            "status": "ok" if not errors else "partial",
            "due": len(due_items),
            "evaluated": evaluated,
            "pending_data": pending_data,
            "errors": errors[:5],
        }

    def build_dashboard(self) -> Dict[str, Any]:
        forecasts = self.portfolio_manager.list_signal_forecasts(limit=240)
        outcomes = self.portfolio_manager.list_signal_forecast_outcomes(limit=1000)
        evaluated = [item for item in outcomes if item.get("status") == "evaluated"]
        pending = [item for item in outcomes if item.get("status") in {"pending", "pending_data"}]
        hits = [item for item in evaluated if item.get("result") == "hit"]
        misses = [item for item in evaluated if item.get("result") == "miss"]
        neutrals = [item for item in evaluated if item.get("result") == "neutral"]

        by_setup_type = self._group_quality(evaluated, "setup_type")
        by_source = self._group_quality(evaluated, "source_label")
        weak_setup_types = self._group_quality(evaluated, "setup_type", weakest=True)
        weak_sources = self._group_quality(evaluated, "source_label", weakest=True)
        recent = self._build_recent_forecasts(forecasts[:12], outcomes)
        pending_by_horizon = self._pending_by_horizon(pending)
        lessons = self._build_lessons(by_source, weak_sources, by_setup_type, weak_setup_types, pending_by_horizon)

        return {
            "summary": {
                "forecasts": len(forecasts),
                "outcomes": len(outcomes),
                "evaluated": len(evaluated),
                "pending": len(pending),
                "hits": len(hits),
                "misses": len(misses),
                "neutral": len(neutrals),
                "hit_rate": round((len(hits) / max(1, len(hits) + len(misses))) * 100, 1),
                "avg_performance_pct": self._avg([item.get("performance_pct") for item in evaluated]),
            },
            "by_setup_type": by_setup_type,
            "by_source": by_source,
            "weak_setup_types": weak_setup_types,
            "weak_sources": weak_sources,
            "pending_by_horizon": pending_by_horizon,
            "lessons": lessons,
            "recent_forecasts": recent,
            "last_updated": datetime.utcnow().isoformat(),
        }

    def _collect_forecast_setups(self, brief: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def add(setup: Dict[str, Any]) -> None:
            symbol = str(setup.get("symbol") or setup.get("ticker") or "").strip().upper()
            if not symbol:
                return
            setup = dict(setup)
            setup["symbol"] = symbol
            key = f"{symbol}:{setup.get('setup_type') or setup.get('direction') or setup.get('action') or ''}:{setup.get('trigger') or setup.get('thesis') or ''}"
            if key in seen:
                return
            seen.add(key)
            collected.append(setup)

        for setup in brief.get("trade_setups") or []:
            if isinstance(setup, dict):
                add(setup)
            if len(collected) >= limit:
                break

        congress_limit = 4
        for item in brief.get("congress_watch") or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            action = str(item.get("action") or item.get("direction") or item.get("setup_type") or "watch").lower()
            add(
                {
                    "symbol": symbol,
                    "direction": self._map_action_to_direction(action),
                    "setup_type": "congress_watch",
                    "setup_source": "congress_watch",
                    "source": "congress_watch",
                    "thesis": item.get("thesis")
                    or item.get("summary")
                    or item.get("reason")
                    or f"Congress/PTR signal for {symbol}.",
                    "trigger": item.get("trigger") or "Confirm with price, volume and sector reaction.",
                    "invalidation": item.get("invalidation") or "Invalidate if follow-through fails or filing context weakens.",
                    "confidence": item.get("confidence"),
                    "rank_score": item.get("impact_score") or item.get("rank_score"),
                    "expected_move": item.get("expected_move"),
                    "congress_signal": item,
                }
            )
            congress_limit -= 1
            if congress_limit <= 0:
                break

        return collected[: limit + 4]

    def _build_recent_forecasts(
        self,
        forecasts: List[Dict[str, Any]],
        outcomes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        outcome_map: Dict[str, List[Dict[str, Any]]] = {}
        for outcome in outcomes:
            outcome_map.setdefault(str(outcome.get("forecast_id")), []).append(outcome)
        recent: List[Dict[str, Any]] = []
        for forecast in forecasts:
            forecast_outcomes = sorted(
                outcome_map.get(str(forecast.get("id")), []),
                key=lambda item: int(item.get("horizon_hours") or 0),
            )
            recent.append(
                {
                    "id": forecast.get("id"),
                    "symbol": forecast.get("symbol"),
                    "direction": forecast.get("direction"),
                    "setup_type": forecast.get("setup_type"),
                    "source_label": forecast.get("source_label"),
                    "confidence": forecast.get("confidence"),
                    "entry_price": forecast.get("entry_price"),
                    "forecast_time": forecast.get("forecast_time"),
                    "thesis": forecast.get("thesis"),
                    "outcomes": [
                        {
                            "horizon_hours": item.get("horizon_hours"),
                            "status": item.get("status"),
                            "result": item.get("result"),
                            "performance_pct": item.get("performance_pct"),
                        }
                        for item in forecast_outcomes
                    ],
                }
            )
        return recent

    def _group_quality(self, outcomes: List[Dict[str, Any]], key: str, weakest: bool = False) -> List[Dict[str, Any]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for item in outcomes:
            buckets.setdefault(str(item.get(key) or "unknown"), []).append(item)
        rows = []
        for label, items in buckets.items():
            hits = [item for item in items if item.get("result") == "hit"]
            misses = [item for item in items if item.get("result") == "miss"]
            rows.append(
                {
                    "label": label,
                    "evaluated": len(items),
                    "hit_rate": round((len(hits) / max(1, len(hits) + len(misses))) * 100, 1),
                    "avg_performance_pct": self._avg([item.get("performance_pct") for item in items]),
                }
            )
        if weakest:
            return sorted(
                rows,
                key=lambda item: (item["evaluated"] < 3, item["hit_rate"], -(item["evaluated"])),
            )[:8]
        return sorted(rows, key=lambda item: (item["evaluated"], item["hit_rate"]), reverse=True)[:8]

    def _pending_by_horizon(self, pending: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: Dict[int, int] = {}
        for item in pending:
            horizon = int(item.get("horizon_hours") or 0)
            buckets[horizon] = buckets.get(horizon, 0) + 1
        return [{"horizon_hours": horizon, "count": count} for horizon, count in sorted(buckets.items())]

    def _build_lessons(
        self,
        sources: List[Dict[str, Any]],
        weak_sources: List[Dict[str, Any]],
        setup_types: List[Dict[str, Any]],
        weak_setup_types: List[Dict[str, Any]],
        pending_by_horizon: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        lessons: List[Dict[str, Any]] = []
        best_source = next((item for item in sources if item.get("evaluated", 0) >= 3), None)
        weak_source = next((item for item in weak_sources if item.get("evaluated", 0) >= 3), None)
        best_setup = next((item for item in setup_types if item.get("evaluated", 0) >= 3), None)
        weak_setup = next((item for item in weak_setup_types if item.get("evaluated", 0) >= 3), None)

        if best_source:
            lessons.append(
                {
                    "type": "promote_source",
                    "label": best_source["label"],
                    "message": f"Promote {best_source['label']}: {best_source['hit_rate']}% hit rate across {best_source['evaluated']} evaluated outcomes.",
                }
            )
        if weak_source:
            lessons.append(
                {
                    "type": "downgrade_source",
                    "label": weak_source["label"],
                    "message": f"Downgrade {weak_source['label']} until confirmed: {weak_source['hit_rate']}% hit rate across {weak_source['evaluated']} outcomes.",
                }
            )
        if best_setup:
            lessons.append(
                {
                    "type": "promote_setup",
                    "label": best_setup["label"],
                    "message": f"Setup type {best_setup['label']} is working best recently; keep it higher in briefing ranking.",
                }
            )
        if weak_setup:
            lessons.append(
                {
                    "type": "tighten_setup",
                    "label": weak_setup["label"],
                    "message": f"Setup type {weak_setup['label']} needs stricter triggers or lower confidence until performance improves.",
                }
            )
        if pending_by_horizon:
            pending_text = ", ".join(f"{item['horizon_hours']}h:{item['count']}" for item in pending_by_horizon[:4])
            lessons.append(
                {
                    "type": "pending_checks",
                    "label": "pending",
                    "message": f"Open outcome checks by horizon: {pending_text}. Do not judge these signals before the window closes.",
                }
            )
        return lessons[:6]

    def _score_result(self, performance_pct: float, direction: str, horizon_hours: int) -> tuple[str, str]:
        threshold = 0.25 if horizon_hours <= 1 else 0.5
        direction = (direction or "").lower()
        bearish = any(token in direction for token in ("short", "hedge", "avoid", "reduce"))
        watch = "watch" in direction and not bearish
        signed_move = -performance_pct if bearish else performance_pct
        if abs(signed_move) < threshold or watch:
            return "neutral", f"Move {performance_pct:+.2f}% stayed inside the confirmation band."
        if signed_move > 0:
            return "hit", f"Direction confirmed with {performance_pct:+.2f}% over {horizon_hours}h."
        return "miss", f"Direction failed with {performance_pct:+.2f}% over {horizon_hours}h."

    def _get_current_price(self, symbol: str) -> Optional[float]:
        try:
            data = DataFetcher(symbol).get_price_data_fast()
            price = self._safe_float(data.get("current_price"))
            if price and math.isfinite(price) and price > 0:
                return price
        except Exception:
            return None
        return None

    def _normalize_direction(self, setup: Dict[str, Any]) -> str:
        raw = str(setup.get("direction") or setup.get("action") or setup.get("setup_type") or "watch").strip().lower()
        if raw in {"long", "short", "hedge", "watch"}:
            return raw
        mapped = self._map_action_to_direction(raw)
        if mapped != "watch":
            return mapped
        if "hedge" in raw or "short" in raw or "avoid" in raw:
            return "hedge"
        if "long" in raw or "benefit" in raw or "winner" in raw:
            return "long"
        return "watch"

    def _map_action_to_direction(self, action: str) -> str:
        raw = (action or "").lower()
        if any(token in raw for token in ("buy", "add", "long", "accumulate", "benefit")):
            return "long"
        if any(token in raw for token in ("sell", "reduce", "short", "hedge", "avoid")):
            return "hedge"
        return "watch"

    def _infer_source(self, setup: Dict[str, Any]) -> str:
        if setup.get("congress_signal"):
            return "congress_watch"
        if setup.get("product_catalyst"):
            return "product_news"
        catalysts = " ".join(str(item) for item in (setup.get("catalysts") or []))
        if "earning" in catalysts.lower():
            return "earnings"
        return str(setup.get("setup_source") or setup.get("source") or "morning_brief")

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except Exception:
            return None

    def _truncate(self, value: Any, limit: int) -> str:
        text = str(value or "").strip()
        return text[:limit]

    def _avg(self, values: List[Any]) -> Optional[float]:
        numbers = [self._safe_float(value) for value in values]
        valid = [value for value in numbers if value is not None]
        if not valid:
            return None
        return round(sum(valid) / len(valid), 2)
