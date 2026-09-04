from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.storage import PortfolioManager


FEATURE_SCHEMA = "paper-learning-features.v2"
ATTRIBUTION_SCHEMA = "paper-learning-attribution.v2"
POLICY_VERSION = "paper-learning-policy.v2"
MIN_ADJUSTMENT_SAMPLE = 8
MIN_PROMOTION_TRADES = 30
GLOBAL_OUTCOME_TARGET = 100
MAX_SINGLE_SCORE_DELTA = 8.0
MAX_TOTAL_SCORE_DELTA = 12.0
MIN_GOOD_PROCESS_RATE = 80.0
MAX_INSTRUMENT_CONCENTRATION = 35.0
ACTIVE_MONITOR_WINDOW = 20
ACTIVE_MIN_MONITOR_TRADES = 10
ACTIVE_EMERGENCY_LOSS_STREAK = 4
ACTIVE_MIN_PROFIT_FACTOR = 0.8
ACTIVE_MAX_DRAWDOWN = 15.0


class PaperLearningService:
    """Auditable paper-only learning. It never authorizes or executes real-money trades."""

    _refresh_lock = threading.Lock()

    def __init__(self, portfolio_manager: PortfolioManager) -> None:
        self.portfolio_manager = portfolio_manager

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _as_utc_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _normalized_regime(value: Any) -> Dict[str, str]:
        regime = value if isinstance(value, dict) else {}
        raw_trend = str(regime.get("trend") or regime.get("trend_regime") or regime.get("state") or "unknown").strip().lower()
        raw_volatility = str(regime.get("volatility") or regime.get("volatility_regime") or "unknown").strip().lower()
        trend_aliases = {
            "bull": "up", "bullish": "up", "uptrend": "up", "risk_on": "up",
            "bear": "down", "bearish": "down", "downtrend": "down", "risk_off": "down",
            "sideways": "range", "neutral": "range", "flat": "range", "choppy": "range",
        }
        volatility_aliases = {
            "low_volatility": "low", "calm": "low",
            "normal_volatility": "normal", "medium": "normal", "moderate": "normal",
            "high_volatility": "high", "elevated": "high", "extreme": "high",
        }
        return {
            "trend": trend_aliases.get(raw_trend, raw_trend or "unknown"),
            "volatility": volatility_aliases.get(raw_volatility, raw_volatility or "unknown"),
        }

    @classmethod
    def _item_regime(cls, item: Dict[str, Any]) -> Dict[str, str]:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        ticket = item.get("trade_ticket") if isinstance(item.get("trade_ticket"), dict) else {}
        snapshot = ticket.get("learning_feature_snapshot") if isinstance(ticket.get("learning_feature_snapshot"), dict) else {}
        raw = (
            item.get("market_regime")
            or item.get("entry_market_regime")
            or evidence.get("market_regime")
            or snapshot.get("market_regime")
            or {}
        )
        return cls._normalized_regime(raw)

    @classmethod
    def _matches_segment(cls, item: Dict[str, Any], segment: Dict[str, Any]) -> bool:
        regime = cls._item_regime(item)
        return bool(
            (not segment.get("setup_type") or str(item.get("setup_type")) == str(segment.get("setup_type")))
            and (not segment.get("asset_class") or str(item.get("asset_class")) == str(segment.get("asset_class")))
            and (not segment.get("direction") or str(item.get("direction")) == str(segment.get("direction")))
            and (not segment.get("regime_trend") or regime["trend"] == str(segment.get("regime_trend")))
            and (not segment.get("regime_volatility") or regime["volatility"] == str(segment.get("regime_volatility")))
        )

    @classmethod
    def _experiment_boundary(
        cls,
        started_at: Any,
        trades: List[Dict[str, Any]],
        outcomes: List[Dict[str, Any]],
        segment: Dict[str, Any],
    ) -> Dict[str, Any]:
        start = cls._as_utc_datetime(started_at)
        if start is None:
            return {
                "valid": False,
                "experiment_started_at": started_at,
                "embargo_until": None,
                "purged_trade_ids": [],
                "reason": "experiment_start_invalid",
            }
        trade_by_id = {str(item.get("id")): item for item in trades}
        purged: set[str] = set()
        embargo_until = start
        for outcome in outcomes:
            trade_id = str(outcome.get("trade_id") or "")
            trade = trade_by_id.get(trade_id) or {}
            match_item = dict(outcome)
            for key in ("setup_type", "asset_class", "direction"):
                if not match_item.get(key):
                    match_item[key] = trade.get(key)
            match_item["market_regime"] = cls._item_regime(trade)
            if not cls._matches_segment(match_item, segment):
                continue
            opened = cls._as_utc_datetime(trade.get("opened_at"))
            due = cls._as_utc_datetime(outcome.get("due_at"))
            if opened is not None and opened <= start:
                purged.add(trade_id)
                if due is not None and due > embargo_until:
                    embargo_until = due
        return {
            "valid": True,
            "experiment_started_at": start.isoformat(),
            "embargo_until": embargo_until.isoformat(),
            "purged_trade_ids": sorted(purged),
            "reason": "pre_start_trade_label_windows_purged",
        }

    @staticmethod
    def _json_hash(payload: Dict[str, Any]) -> str:
        material = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @classmethod
    def _snapshot_integrity(cls, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        stored_hash = str(snapshot.get("snapshot_hash") or "")
        material = {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
        computed_hash = cls._json_hash(material) if material else None
        return {
            "status": "valid" if stored_hash and computed_hash == stored_hash else "missing" if not stored_hash else "invalid",
            "stored_hash": stored_hash or None,
            "computed_hash": computed_hash,
            "immutable": True,
        }

    @classmethod
    def _compose_trade_detail(
        cls,
        trade: Dict[str, Any],
        outcomes: List[Dict[str, Any]],
        attribution: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
        snapshot = ticket.get("learning_feature_snapshot") if isinstance(ticket.get("learning_feature_snapshot"), dict) else {}
        attribution = attribution or (cls.build_attribution(trade, outcomes) if trade.get("status") == "closed" else None)
        return {
            "schema": "paper-learning-trade-review.v2",
            "trade_id": trade.get("id"),
            "ticker": trade.get("ticker"),
            "asset_class": trade.get("asset_class"),
            "direction": trade.get("direction"),
            "setup_type": trade.get("setup_type"),
            "status": trade.get("status"),
            "opened_at": trade.get("opened_at"),
            "closed_at": trade.get("closed_at"),
            "original_plan": snapshot.get("plan") or {},
            "entry_scores": snapshot.get("scores") or {},
            "entry_market_regime": snapshot.get("market_regime") or {},
            "asset_features": snapshot.get("asset_features") or {},
            "entry_gate": snapshot.get("gate_decision") or {},
            "applied_learning_rule_ids": (snapshot.get("scores") or {}).get("active_learning_rule_ids") or [],
            "execution": {
                "entry": (ticket.get("execution_model") or {}).get("entry"),
                "exit": (ticket.get("execution_model") or {}).get("exit"),
            },
            "actual": {
                "entry_price": trade.get("entry_price"),
                "closed_price": trade.get("closed_price"),
                "exit_reason": trade.get("exit_reason"),
                "lessons_learned": trade.get("lessons_learned"),
            },
            "outcomes": sorted(outcomes, key=lambda item: str(item.get("due_at") or "")),
            "attribution": attribution,
            "snapshot_integrity": cls._snapshot_integrity(snapshot),
            "decision_scope": {
                "paper_only": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            },
        }

    def build_trade_detail(self, trade_id: str) -> Dict[str, Any]:
        trade = next(
            (item for item in self.portfolio_manager.list_paper_trades(limit=2000) if str(item.get("id")) == str(trade_id)),
            None,
        )
        if not trade:
            raise ValueError("Paper trade not found.")
        outcomes = [
            item
            for item in self.portfolio_manager.list_paper_trade_outcomes(limit=10000)
            if str(item.get("trade_id")) == str(trade_id)
        ]
        list_attributions = getattr(self.portfolio_manager, "list_paper_learning_attributions", None)
        stored = list_attributions(limit=2000) if callable(list_attributions) else []
        attribution = next((item for item in stored if str(item.get("trade_id")) == str(trade_id)), None)
        return self._compose_trade_detail(trade, outcomes, attribution)

    @classmethod
    def _build_asset_features(cls, playbook: Dict[str, Any], ticket: Dict[str, Any]) -> Dict[str, Any]:
        asset_class = str(ticket.get("asset_class") or playbook.get("asset_class") or "equity").lower()
        evidence = playbook.get("asset_evidence") if isinstance(playbook.get("asset_evidence"), dict) else {}
        market = ticket.get("market_data") if isinstance(ticket.get("market_data"), dict) else {}
        common = {
            "asset_class": asset_class,
            "source": evidence.get("source") or market.get("source"),
            "data_as_of": evidence.get("data_as_of") or market.get("data_as_of") or ticket.get("data_as_of"),
            "fallback": bool(evidence.get("fallback")),
        }
        if asset_class == "etf":
            fields = {
                **common,
                "category_or_exposure": evidence.get("category"),
                "expense_ratio": evidence.get("expense_ratio"),
                "total_assets": evidence.get("total_assets"),
                "change_1w_pct": evidence.get("change_1w_pct"),
                "replication_method": evidence.get("replication_method"),
                "fund_domicile": evidence.get("fund_domicile"),
                "distribution_policy": evidence.get("distribution_policy"),
                "tracking_difference": evidence.get("tracking_difference"),
                "trading_venue": evidence.get("trading_venue"),
            }
            required = ("category_or_exposure", "expense_ratio", "total_assets")
            research = ("replication_method", "fund_domicile", "distribution_policy", "tracking_difference", "trading_venue")
        elif asset_class == "crypto":
            pair = str(evidence.get("trading_pair") or ticket.get("instrument") or "")
            fields = {
                **common,
                "trading_pair": pair or None,
                "quote_currency": pair.rsplit("-", 1)[-1] if "-" in pair else None,
                "execution_venue": evidence.get("execution_venue"),
                "change_1w_pct": evidence.get("change_1w_pct"),
                "price": evidence.get("price") or market.get("price"),
                "weekend_context": datetime.now(timezone.utc).weekday() >= 5,
                "trades_24_7": True,
                "funding_rate": evidence.get("funding_rate"),
                "open_interest": evidence.get("open_interest"),
                "order_book_depth": evidence.get("order_book_depth"),
                "on_chain_layer": evidence.get("on_chain_layer"),
            }
            required = ("trading_pair", "price")
            research = ("execution_venue", "funding_rate", "open_interest", "order_book_depth", "on_chain_layer")
        else:
            fields = {
                **common,
                "market_cap": evidence.get("market_cap"),
                "profitability": evidence.get("profitability"),
                "debt_quality": evidence.get("debt_quality"),
                "earnings_stability": evidence.get("earnings_stability"),
                "valuation_context": evidence.get("valuation_context"),
                "revenue_growth": evidence.get("revenue_growth"),
                "price_change_1w_pct": evidence.get("change_1w") or evidence.get("change_1w_pct"),
                "volume_confirmation": evidence.get("volume_confirmation"),
                "earnings_risk": evidence.get("earnings_risk"),
            }
            required = ("market_cap",)
            research = ("profitability", "debt_quality", "earnings_stability", "valuation_context", "revenue_growth", "volume_confirmation", "earnings_risk")
        missing_required = []
        for key in required:
            value = fields.get(key)
            if value in (None, ""):
                missing_required.append(key)
                continue
            if key in {"market_cap", "total_assets", "price"}:
                numeric = cls._safe_float(value)
                if numeric is None or numeric <= 0:
                    missing_required.append(key)
        missing_research = [key for key in research if fields.get(key) in (None, "")]
        return {
            "schema_version": "paper-learning-asset-features.v1",
            "fields": fields,
            "availability": {
                "required_missing": missing_required,
                "research_missing": missing_research,
                "status": "complete" if not missing_required and not missing_research else "partial" if not missing_required else "insufficient",
                "missing_values_are_not_imputed": True,
            },
        }

    def apply_active_rules(self, playbooks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply manually promoted rules to future paper candidates, within policy caps."""
        if not hasattr(self.portfolio_manager, "list_paper_learning_rules") or not hasattr(
            self.portfolio_manager, "list_paper_learning_hypotheses"
        ):
            return playbooks
        rules = [
            item
            for item in self.portfolio_manager.list_paper_learning_rules(limit=1000)
            if str(item.get("status") or "") == "active_paper"
        ]
        hypotheses = {
            str(item.get("id")): item
            for item in self.portfolio_manager.list_paper_learning_hypotheses(limit=1000)
        }
        for playbook in playbooks:
            matching: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
            for rule in rules:
                hypothesis = hypotheses.get(str(rule.get("hypothesis_id"))) or {}
                segment = hypothesis.get("segment") if isinstance(hypothesis.get("segment"), dict) else {}
                setup_matches = not segment.get("setup_type") or str(segment.get("setup_type")) == str(
                    playbook.get("setup_type") or ""
                )
                asset_matches = not segment.get("asset_class") or str(segment.get("asset_class")) == str(
                    playbook.get("asset_class") or ""
                )
                direction_matches = not segment.get("direction") or str(segment.get("direction")) == str(
                    playbook.get("direction") or ""
                )
                candidate_regime = self._item_regime(playbook)
                trend_matches = not segment.get("regime_trend") or candidate_regime["trend"] == str(segment.get("regime_trend"))
                volatility_matches = not segment.get("regime_volatility") or candidate_regime["volatility"] == str(segment.get("regime_volatility"))
                if setup_matches and asset_matches and direction_matches and trend_matches and volatility_matches:
                    matching.append((rule, hypothesis))
            if not matching:
                continue

            applied_delta = 0.0
            risk_cap = 1.0
            rule_ids: List[str] = []
            notes: List[str] = []
            for rule, hypothesis in matching:
                proposal = rule.get("rule") if isinstance(rule.get("rule"), dict) else {}
                proposed_delta = self._safe_float(proposal.get("score_delta")) or 0.0
                proposed_delta = max(-MAX_SINGLE_SCORE_DELTA, min(MAX_SINGLE_SCORE_DELTA, proposed_delta))
                remaining = MAX_TOTAL_SCORE_DELTA - abs(applied_delta)
                if remaining <= 0:
                    break
                proposed_delta = max(-remaining, min(remaining, proposed_delta))
                applied_delta += proposed_delta
                proposed_cap = self._safe_float(proposal.get("paper_risk_multiplier_cap"))
                if proposed_cap is not None:
                    risk_cap = min(risk_cap, max(0.01, min(1.0, proposed_cap)))
                rule_ids.append(str(rule.get("id")))
                notes.append(str(hypothesis.get("statement") or "Freigegebene Paper-Lernregel."))

            playbook.setdefault("raw_score", playbook.get("score"))
            playbook["score"] = round(
                max(0.0, min(100.0, float(playbook.get("score") or 0) + applied_delta)), 2
            )
            playbook["active_learning_rule_ids"] = rule_ids
            playbook["learning_rule_risk_multiplier_cap"] = risk_cap
            playbook["learning_v2_adjustment"] = {
                "policy_version": POLICY_VERSION,
                "score_delta": round(applied_delta, 2),
                "paper_risk_multiplier_cap": risk_cap,
                "notes": notes,
                "paper_only": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            }
        return playbooks

    @classmethod
    def build_feature_snapshot(cls, playbook: Dict[str, Any], ticket: Dict[str, Any]) -> Dict[str, Any]:
        market = ticket.get("market_data") if isinstance(ticket.get("market_data"), dict) else {}
        regime = ticket.get("entry_market_regime") if isinstance(ticket.get("entry_market_regime"), dict) else {}
        validation = ticket.get("validation") if isinstance(ticket.get("validation"), dict) else {}
        learning_adjustment = playbook.get("learning_adjustment") if isinstance(playbook.get("learning_adjustment"), dict) else {}
        score_components = playbook.get("score_components")
        if not isinstance(score_components, (list, dict)):
            score_components = {
                "raw_score": playbook.get("raw_score"),
                "final_score": playbook.get("score"),
                "learning_delta": learning_adjustment.get("score_delta", 0),
            }
        execution = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        entry_execution = execution.get("entry") if isinstance(execution.get("entry"), dict) else {}
        entry_calibration = entry_execution.get("calibration") if isinstance(entry_execution.get("calibration"), dict) else {}
        benchmark = ticket.get("benchmark_data") if isinstance(ticket.get("benchmark_data"), dict) else {}
        asset_features = cls._build_asset_features(playbook, ticket)
        feature_data = {
            "schema_version": FEATURE_SCHEMA,
            "policy_version": POLICY_VERSION,
            "captured_at": ticket.get("generated_at") or datetime.now(timezone.utc).isoformat(),
            "trade_identity": {
                "ticket_id": ticket.get("ticket_id"),
                "strategy_id": ticket.get("strategy_id"),
                "setup_type": playbook.get("setup_type"),
                "asset_class": ticket.get("asset_class"),
                "instrument": ticket.get("instrument"),
                "direction": ticket.get("direction"),
                "horizon": ticket.get("horizon"),
            },
            "scores": {
                "raw_score": playbook.get("raw_score", playbook.get("score")),
                "final_score": playbook.get("score"),
                "components": score_components,
                "learning_adjustment": learning_adjustment or None,
                "active_learning_rule_ids": playbook.get("active_learning_rule_ids") or [],
                "learning_v2_adjustment": playbook.get("learning_v2_adjustment"),
            },
            "market_regime": regime,
            "market": {
                "source": market.get("source"),
                "data_as_of": market.get("data_as_of") or ticket.get("data_as_of"),
                "freshness": market.get("freshness"),
                "price": market.get("price"),
                "bid": market.get("bid"),
                "ask": market.get("ask"),
                "spread_pct": market.get("spread_pct"),
                "avg_dollar_volume": market.get("avg_dollar_volume"),
                "liquidity_status": market.get("liquidity_status"),
            },
            "benchmark": {
                "symbol": benchmark.get("symbol"),
                "entry_price": benchmark.get("entry_price"),
                "basis": benchmark.get("basis"),
                "source": benchmark.get("source"),
                "data_as_of": benchmark.get("data_as_of"),
                "status": benchmark.get("status") or "unavailable",
                "missing_values_are_not_imputed": True,
            },
            "asset_features": asset_features,
            "portfolio_context": {
                "risk_bucket": playbook.get("risk_bucket"),
                "correlation_check": playbook.get("correlation_check"),
                "account_risk_pct": ticket.get("account_risk_pct"),
                "notional_value": ticket.get("notional_value"),
                "max_loss_value": ticket.get("max_loss_value"),
            },
            "plan": {
                "thesis": ticket.get("thesis"),
                "entry_condition": ticket.get("entry_condition"),
                "entry_price": ticket.get("entry_price"),
                "stop_price": ticket.get("stop_price"),
                "target_1": ticket.get("target_1"),
                "target_2": ticket.get("target_2"),
                "invalidation": ticket.get("invalidation"),
                "risk_reward": ticket.get("risk_reward"),
                "quantity": ticket.get("quantity"),
                "max_holding_days": ticket.get("max_holding_days"),
            },
            "evidence": {
                "source_label": ticket.get("source_label"),
                "entry_source_label": ticket.get("entry_source_label"),
                "evidence_level": ticket.get("evidence_level"),
                "news_evidence": ticket.get("news_evidence"),
            },
            "execution": {
                "model_version": entry_calibration.get("model_version") or entry_execution.get("model_version"),
                "reference_price": entry_execution.get("reference_price"),
                "fill_price": entry_execution.get("fill_price"),
                "cost_bps": entry_execution.get("cost_bps"),
                "slippage_bps": entry_execution.get("slippage_bps"),
                "fee_equivalent_bps": entry_execution.get("fee_equivalent_bps"),
                "fees_value": entry_execution.get("estimated_fee_value"),
                "slippage_value": entry_execution.get("estimated_slippage_value"),
                "total_cost_value": entry_execution.get("estimated_cost_value"),
                "spread_pct": entry_execution.get("spread_pct"),
                "source": entry_execution.get("market_source"),
                "data_as_of": entry_execution.get("data_as_of"),
            },
            "missing_data_flags": sorted(set(
                [str(item) for item in validation.get("errors") or []]
                + [str(item) for item in validation.get("warnings") or []]
                + [f"asset.required.{item}" for item in asset_features["availability"]["required_missing"]]
                + [f"asset.research.{item}" for item in asset_features["availability"]["research_missing"]]
            )),
            "gate_decision": {
                "status": ticket.get("status"),
                "paper_ready": bool(ticket.get("paper_ready")),
                "minimum_trade_score": playbook.get("minimum_trade_score"),
                "blocked_reasons": validation.get("blocked_reasons") or [],
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            },
        }
        feature_data["snapshot_hash"] = cls._json_hash(feature_data)
        return feature_data

    @staticmethod
    def _wilson_interval(hits: int, total: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
        if total <= 0:
            return None, None
        p = hits / total
        denominator = 1 + (z * z / total)
        center = (p + (z * z / (2 * total))) / denominator
        margin = z * math.sqrt((p * (1 - p) / total) + (z * z / (4 * total * total))) / denominator
        return round(max(0.0, center - margin) * 100, 1), round(min(1.0, center + margin) * 100, 1)

    @classmethod
    def _performance_series_metrics(cls, values: List[float]) -> Dict[str, Any]:
        finite = [value for value in (cls._safe_float(item) for item in values) if value is not None]
        gains = sum(value for value in finite if value > 0)
        losses = abs(sum(value for value in finite if value < 0))
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        loss_streak = 0
        max_loss_streak = 0
        for value in finite:
            cumulative += value
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)
            if value < 0:
                loss_streak += 1
                max_loss_streak = max(max_loss_streak, loss_streak)
            elif value > 0:
                loss_streak = 0
        return {
            "observations": len(finite),
            "positive": sum(1 for value in finite if value > 0),
            "negative": sum(1 for value in finite if value < 0),
            "expectancy_pct": round(sum(finite) / len(finite), 3) if finite else None,
            "profit_factor": round(gains / losses, 3) if losses > 0 else (999.0 if gains > 0 else None),
            "max_drawdown_pct_points": round(max_drawdown, 3),
            "max_loss_streak": max_loss_streak,
            "cumulative_return_points": round(sum(finite), 3),
        }

    @classmethod
    def build_attribution(cls, trade: Dict[str, Any], outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
        ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
        snapshot = ticket.get("learning_feature_snapshot") if isinstance(ticket.get("learning_feature_snapshot"), dict) else {}
        plan = snapshot.get("plan") if isinstance(snapshot.get("plan"), dict) else {}
        entry = cls._safe_float(trade.get("entry_price")) or cls._safe_float(plan.get("entry_price"))
        close = cls._safe_float(trade.get("closed_price"))
        stop = cls._safe_float(trade.get("stop_price")) or cls._safe_float(plan.get("stop_price"))
        quantity = cls._safe_float(trade.get("quantity")) or 0.0
        multiplier = cls._safe_float(trade.get("contract_multiplier")) or 1.0
        direction = str(trade.get("direction") or "long").lower()
        # Calls and puts are long-premium instruments in the existing paper model.
        sign = -1.0 if direction == "short" else 1.0
        execution_model = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        entry_execution = execution_model.get("entry") if isinstance(execution_model.get("entry"), dict) else {}
        exit_execution = execution_model.get("exit") if isinstance(execution_model.get("exit"), dict) else {}
        entry_reference = cls._safe_float(entry_execution.get("reference_price"))
        exit_reference = cls._safe_float(exit_execution.get("reference_price"))
        gross_pnl_pct = None
        gross_pnl_value = None
        net_pnl_pct = None
        net_pnl_value = None
        r_multiple = None
        if entry and close and entry > 0:
            net_pnl_pct = ((close / entry) - 1.0) * 100.0 * sign
            net_pnl_value = (close - entry) * sign * quantity * multiplier
            if stop is not None and abs(entry - stop) > 1e-12:
                r_multiple = ((close - entry) * sign) / abs(entry - stop)
        if entry_reference and exit_reference and entry_reference > 0:
            gross_pnl_pct = ((exit_reference / entry_reference) - 1.0) * 100.0 * sign
            gross_pnl_value = (exit_reference - entry_reference) * sign * quantity * multiplier
        else:
            gross_pnl_pct = net_pnl_pct
            gross_pnl_value = net_pnl_value

        entry_cost = cls._safe_float(entry_execution.get("estimated_cost_value"))
        exit_cost = cls._safe_float(exit_execution.get("estimated_cost_value"))
        fees_value = sum(
            value
            for value in (
                cls._safe_float(entry_execution.get("estimated_fee_value")),
                cls._safe_float(exit_execution.get("estimated_fee_value")),
            )
            if value is not None
        )
        slippage_value = sum(
            value
            for value in (
                cls._safe_float(entry_execution.get("estimated_slippage_value")),
                cls._safe_float(exit_execution.get("estimated_slippage_value")),
            )
            if value is not None
        )
        execution_cost_value = (
            sum(value for value in (entry_cost, exit_cost) if value is not None)
            if entry_cost is not None or exit_cost is not None
            else None
        )
        cost_share_of_gross = (
            execution_cost_value / abs(gross_pnl_value) * 100
            if execution_cost_value is not None and gross_pnl_value not in (None, 0)
            else None
        )
        holding_hours = None
        try:
            opened_at = datetime.fromisoformat(str(trade.get("opened_at") or "").replace("Z", "+00:00"))
            closed_at = datetime.fromisoformat(str(trade.get("closed_at") or "").replace("Z", "+00:00"))
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=timezone.utc)
            holding_hours = max(0.0, (closed_at - opened_at).total_seconds() / 3600)
        except (TypeError, ValueError):
            holding_hours = None
        decisive = [item for item in outcomes if item.get("result") in {"hit", "miss"}]
        evaluated = [item for item in outcomes if item.get("status") == "evaluated"]
        benchmark_observations = [
            item for item in evaluated
            if cls._safe_float(item.get("benchmark_return_pct")) is not None
            and cls._safe_float(item.get("active_return_pct")) is not None
        ]
        latest_benchmark = max(
            benchmark_observations,
            key=lambda item: int(item.get("horizon_hours") or 0),
            default=None,
        )
        benchmark_return_pct = cls._safe_float((latest_benchmark or {}).get("benchmark_return_pct"))
        active_return_pct = cls._safe_float((latest_benchmark or {}).get("active_return_pct"))
        favorable = [cls._safe_float(item.get("performance_pct")) for item in evaluated]
        favorable = [value for value in favorable if value is not None]
        mfe = max(favorable) if favorable else None
        mae = min(favorable) if favorable else None
        complete_plan = bool(
            snapshot
            and plan.get("thesis")
            and plan.get("entry_condition")
            and plan.get("entry_price") not in (None, 0)
            and plan.get("stop_price") not in (None, 0)
            and plan.get("target_2") not in (None, 0)
            and plan.get("invalidation")
        )
        gate = snapshot.get("gate_decision") if isinstance(snapshot.get("gate_decision"), dict) else {}
        asset_features = snapshot.get("asset_features") if isinstance(snapshot.get("asset_features"), dict) else {}
        asset_availability = asset_features.get("availability") if isinstance(asset_features.get("availability"), dict) else {}
        asset_required_complete = bool(asset_features and not (asset_availability.get("required_missing") or []))
        journal_complete = bool(
            str(trade.get("exit_reason") or "").strip()
            and str(trade.get("lessons_learned") or "").strip()
        )
        process_good = bool(
            complete_plan
            and asset_required_complete
            and journal_complete
            and gate.get("paper_ready")
            and not gate.get("blocked_reasons")
        )
        outcome_good = net_pnl_pct is not None and net_pnl_pct > 0
        if net_pnl_pct is None:
            outcome_quality = "insufficient_evidence"
            process_quality = "insufficient_evidence" if not snapshot else ("good_process_open_outcome" if process_good else "bad_process_open_outcome")
        else:
            outcome_quality = "profitable" if net_pnl_pct > 0.15 else "loss" if net_pnl_pct < -0.15 else "neutral"
            process_quality = (
                "good_process_good_outcome" if process_good and outcome_good
                else "good_process_bad_outcome" if process_good
                else "bad_process_good_outcome" if outcome_good
                else "bad_process_bad_outcome"
            )
        primary_error = None
        secondary: List[str] = []
        if not snapshot:
            primary_error = "data_quality.feature_snapshot_missing"
        elif not asset_required_complete:
            primary_error = "data_quality.asset_features_missing"
        elif not complete_plan:
            primary_error = "process.rule_violation"
        elif net_pnl_pct is not None and net_pnl_pct < -0.15:
            tags = [str(item.get("error_tag") or "") for item in outcomes if item.get("result") == "miss"]
            if any("headline" in tag for tag in tags):
                primary_error = "news.reaction_faded"
            elif str(trade.get("asset_class")) == "option":
                primary_error = "option.timing_or_decay"
            elif str(trade.get("asset_class")) == "crypto" and str((snapshot.get("market_regime") or {}).get("session") or "").lower() == "weekend":
                primary_error = "crypto.weekend_liquidity"
            else:
                primary_error = "signal.no_follow_through"
        if mae is not None and mae < -3:
            secondary.append("risk.adverse_excursion")
        snapshot_execution = snapshot.get("execution") if isinstance(snapshot.get("execution"), dict) else {}
        entry_cost_bps = cls._safe_float(entry_execution.get("cost_bps"))
        if entry_cost_bps is None:
            entry_cost_bps = cls._safe_float(snapshot_execution.get("cost_bps"))
        exit_cost_bps = cls._safe_float(exit_execution.get("cost_bps"))
        round_trip_cost_bps = (
            sum(value for value in (entry_cost_bps, exit_cost_bps) if value is not None)
            if entry_cost_bps is not None or exit_cost_bps is not None
            else None
        )
        if execution_cost_value is not None and gross_pnl_value is not None and execution_cost_value >= abs(gross_pnl_value):
            secondary.append("liquidity.slippage_dominated")
        target = cls._safe_float(trade.get("target_price")) or cls._safe_float(plan.get("target_2"))
        target_reached = bool(
            close is not None
            and target is not None
            and ((sign > 0 and close >= target) or (sign < 0 and close <= target))
        )
        stop_reached = bool(
            close is not None
            and stop is not None
            and ((sign > 0 and close <= stop) or (sign < 0 and close >= stop))
        )
        return {
            "trade_id": trade.get("id"),
            "schema_version": ATTRIBUTION_SCHEMA,
            "outcome_quality": outcome_quality,
            "process_quality": process_quality,
            "primary_error": primary_error,
            "secondary_errors": sorted(set(secondary)),
            "metrics": {
                "gross_pnl_pct": round(gross_pnl_pct, 3) if gross_pnl_pct is not None else None,
                "gross_pnl_value": round(gross_pnl_value, 2) if gross_pnl_value is not None else None,
                "net_pnl_pct": round(net_pnl_pct, 3) if net_pnl_pct is not None else None,
                "net_pnl_value": round(net_pnl_value, 2) if net_pnl_value is not None else None,
                "r_multiple": round(r_multiple, 3) if r_multiple is not None else None,
                "mfe_pct": round(mfe, 3) if mfe is not None else None,
                "mae_pct": round(mae, 3) if mae is not None else None,
                "holding_hours": round(holding_hours, 2) if holding_hours is not None else None,
                "evaluated_outcomes": len(evaluated),
                "decisive_outcomes": len(decisive),
                "entry_cost_bps": entry_cost_bps,
                "exit_cost_bps": exit_cost_bps,
                "round_trip_cost_bps": round(round_trip_cost_bps, 2) if round_trip_cost_bps is not None else None,
                "execution_cost_value": round(execution_cost_value, 2) if execution_cost_value is not None else None,
                "fees_value": round(fees_value, 2) if execution_cost_value is not None else None,
                "slippage_value": round(slippage_value, 2) if execution_cost_value is not None else None,
                "cost_share_of_gross_pct": round(cost_share_of_gross, 2) if cost_share_of_gross is not None else None,
                "target_reached": target_reached,
                "stop_reached": stop_reached,
                "benchmark_return_pct": round(benchmark_return_pct, 3) if benchmark_return_pct is not None else None,
                "active_return_pct": round(active_return_pct, 3) if active_return_pct is not None else None,
                "benchmark_horizon_hours": int((latest_benchmark or {}).get("horizon_hours") or 0) or None,
                "benchmark_observations": len(benchmark_observations),
            },
            "evidence": {
                "feature_schema": snapshot.get("schema_version"),
                "snapshot_hash": snapshot.get("snapshot_hash"),
                "strategy_id": (snapshot.get("trade_identity") or {}).get("strategy_id"),
                "setup_type": (snapshot.get("trade_identity") or {}).get("setup_type") or trade.get("setup_type"),
                "asset_class": (snapshot.get("trade_identity") or {}).get("asset_class") or trade.get("asset_class"),
                "direction": (snapshot.get("trade_identity") or {}).get("direction") or trade.get("direction"),
                "score": (snapshot.get("scores") or {}).get("final_score"),
                "market_regime": snapshot.get("market_regime") or {},
                "asset_features": asset_features,
                "complete_plan": complete_plan,
                "asset_required_complete": asset_required_complete,
                "journal_complete": journal_complete,
                "paper_gate_passed": bool(gate.get("paper_ready")),
                "outcome_ids": [item.get("id") for item in outcomes],
                "mfe_mae_basis": "evaluated scheduled outcome observations; not an intraperiod tick path",
                "benchmark_status": "available" if latest_benchmark else "unavailable",
                "benchmark_symbol": (latest_benchmark or {}).get("benchmark_symbol") or (snapshot.get("benchmark") or {}).get("symbol"),
                "benchmark_timing_policy": "Latest evaluated scheduled horizon; not presented as exact close-to-close alpha.",
                "execution_cost_method": "reference-price gross P&L compared with conservative simulated fill P&L; costs are not subtracted twice",
                "causality_policy": "Error labels are deterministic attribution hypotheses, not causal proof.",
            },
        }

    @classmethod
    def _segment_rows(cls, outcomes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for item in outcomes:
            if item.get("status") != "evaluated":
                continue
            setup = str(item.get("setup_type") or "unknown")
            asset = str(item.get("asset_class") or "unknown")
            grouped.setdefault((setup, asset), []).append(item)
        rows: List[Dict[str, Any]] = []
        for (setup, asset), items in grouped.items():
            hits = sum(1 for item in items if item.get("result") == "hit")
            misses = sum(1 for item in items if item.get("result") == "miss")
            decisive = hits + misses
            lower, upper = cls._wilson_interval(hits, decisive)
            performance = [cls._safe_float(item.get("performance_pct")) for item in items]
            performance = [value for value in performance if value is not None]
            rows.append({
                "segment": {"setup_type": setup, "asset_class": asset},
                "sample_size": len(items),
                "decisive": decisive,
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hits / decisive * 100, 1) if decisive else None,
                "hit_rate_interval": {"lower": lower, "upper": upper},
                "avg_performance_pct": round(sum(performance) / len(performance), 3) if performance else None,
                "adjustment_eligible": decisive >= MIN_ADJUSTMENT_SAMPLE,
            })
        return sorted(rows, key=lambda row: (-row["decisive"], str(row["segment"])))

    @classmethod
    def _attribution_segment_rows(cls, attributions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate closed trades once each; scheduled horizons never inflate the trade sample."""
        grouped: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = {}
        for item in attributions:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            setup = str(item.get("setup_type") or evidence.get("setup_type") or "unknown")
            asset = str(item.get("asset_class") or evidence.get("asset_class") or "unknown")
            direction = str(item.get("direction") or evidence.get("direction") or "unknown")
            regime = cls._item_regime(item)
            grouped.setdefault((setup, asset, direction, regime["trend"], regime["volatility"]), []).append(item)
        rows: List[Dict[str, Any]] = []
        for (setup, asset, direction, regime_trend, regime_volatility), items in grouped.items():
            trade_returns: List[float] = []
            wins: List[float] = []
            losses: List[float] = []
            r_values: List[float] = []
            mfe_values: List[float] = []
            mae_values: List[float] = []
            cost_shares: List[float] = []
            active_returns: List[float] = []
            instrument_counts: Dict[str, int] = {}
            good_process = 0
            for item in items:
                metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
                net_return = cls._safe_float(metrics.get("net_pnl_pct"))
                if net_return is not None:
                    trade_returns.append(net_return)
                    if net_return > 0.15:
                        wins.append(net_return)
                    elif net_return < -0.15:
                        losses.append(net_return)
                for values, key in (
                    (r_values, "r_multiple"),
                    (mfe_values, "mfe_pct"),
                    (mae_values, "mae_pct"),
                    (cost_shares, "cost_share_of_gross_pct"),
                    (active_returns, "active_return_pct"),
                ):
                    value = cls._safe_float(metrics.get(key))
                    if value is not None:
                        values.append(value)
                if str(item.get("process_quality") or "").startswith("good_process"):
                    good_process += 1
                instrument = str(item.get("ticker") or "unknown")
                instrument_counts[instrument] = instrument_counts.get(instrument, 0) + 1
            decisive = len(wins) + len(losses)
            lower, upper = cls._wilson_interval(len(wins), decisive)
            gains = sum(wins)
            loss_total = abs(sum(losses))
            profit_factor = round(gains / loss_total, 3) if loss_total > 0 else (999.0 if gains > 0 else None)
            expectancy = round(sum(trade_returns) / len(trade_returns), 3) if trade_returns else None
            concentration = (
                round(max(instrument_counts.values(), default=0) / len(items) * 100, 1)
                if items
                else None
            )
            regime_complete = regime_trend != "unknown" and regime_volatility != "unknown"
            rows.append({
                "segment": {
                    "setup_type": setup,
                    "asset_class": asset,
                    "direction": direction,
                    "regime_trend": regime_trend,
                    "regime_volatility": regime_volatility,
                },
                "sample_unit": "closed_trade",
                "sample_size": len(items),
                "decisive": decisive,
                "hits": len(wins),
                "misses": len(losses),
                "hit_rate": round(len(wins) / decisive * 100, 1) if decisive else None,
                "hit_rate_interval": {"lower": lower, "upper": upper, "method": "wilson_95"},
                "avg_win_pct": round(sum(wins) / len(wins), 3) if wins else None,
                "avg_loss_pct": round(sum(losses) / len(losses), 3) if losses else None,
                "expectancy_pct": expectancy,
                "profit_factor": profit_factor,
                "avg_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
                "avg_mfe_pct": round(sum(mfe_values) / len(mfe_values), 3) if mfe_values else None,
                "avg_mae_pct": round(sum(mae_values) / len(mae_values), 3) if mae_values else None,
                "avg_cost_share_pct": round(sum(cost_shares) / len(cost_shares), 2) if cost_shares else None,
                "avg_active_return_pct": round(sum(active_returns) / len(active_returns), 3) if active_returns else None,
                "benchmark_coverage_pct": round(len(active_returns) / len(items) * 100, 1) if items else 0.0,
                "good_process_rate": round(good_process / len(items) * 100, 1) if items else None,
                "largest_instrument_concentration_pct": concentration,
                "trade_ids": [item.get("trade_id") for item in items],
                "outcome_ids": sorted({
                    str(outcome_id)
                    for item in items
                    for outcome_id in ((item.get("evidence") or {}).get("outcome_ids") or [])
                    if outcome_id
                }),
                "regime_complete": regime_complete,
                "adjustment_eligible": decisive >= MIN_ADJUSTMENT_SAMPLE and regime_complete,
                "edge_status": (
                    "regime_unknown"
                    if not regime_complete
                    else "small_sample"
                    if decisive < MIN_ADJUSTMENT_SAMPLE
                    else "weak"
                    if expectancy is not None and expectancy <= 0
                    else "provisional_positive"
                ),
                "paper_only": True,
            })
        return sorted(rows, key=lambda row: (-row["decisive"], str(row["segment"])))

    @classmethod
    def build_hypotheses(cls, segments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hypotheses: List[Dict[str, Any]] = []
        for row in segments:
            decisive = int(row.get("decisive") or 0)
            hit_rate = cls._safe_float(row.get("hit_rate"))
            if decisive < MIN_ADJUSTMENT_SAMPLE or hit_rate is None or hit_rate >= 35 or row.get("regime_complete") is not True:
                continue
            segment = row.get("segment") or {}
            statement = (
                f"{segment.get('setup_type')} in {segment.get('asset_class')} ({segment.get('direction') or 'alle Richtungen'}) "
                f"bei Trend {segment.get('regime_trend')} und Volatilitaet {segment.get('regime_volatility')} "
                "zeigt zu wenig bestaetigtes Follow-through."
            )
            proposed_rule = {
                "action": "reduce_paper_score_and_require_confirmation",
                "score_delta": -min(MAX_SINGLE_SCORE_DELTA, 4.0 if hit_rate >= 25 else 8.0),
                "paper_risk_multiplier_cap": 0.25,
                "hard_risk_caps_unchanged": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            }
            fingerprint_payload = {"segment": segment, "action": proposed_rule["action"], "policy": POLICY_VERSION}
            fingerprint = cls._json_hash(fingerprint_payload)
            created_at = datetime.now(timezone.utc)
            hypotheses.append({
                "id": f"plh_{fingerprint[:24]}",
                "fingerprint": fingerprint,
                "strategy_id": None,
                "segment": segment,
                "statement": statement,
                "evidence": {
                    "sample_size": row.get("sample_size"),
                    "decisive": decisive,
                    "hit_rate": hit_rate,
                    "hit_rate_interval": row.get("hit_rate_interval"),
                    "expectancy_pct": row.get("expectancy_pct"),
                    "profit_factor": row.get("profit_factor"),
                    "trade_ids": row.get("trade_ids") or [],
                    "outcome_ids": row.get("outcome_ids") or [],
                    "sample_unit": row.get("sample_unit") or "evaluated_outcome",
                    "future_shadow_required": True,
                },
                "proposed_rule": proposed_rule,
                "expected_effect": "Weniger schwache Paper-Einstiege und geringerer segmentbezogener Drawdown.",
                "alternative_explanation": (
                    "Das Muster kann durch Marktregime, Instrumentkonzentration, Kosten oder Zufall statt durch das Setup selbst entstehen."
                ),
                "possible_downside": "Eine strengere Bestätigung kann profitable frühe Einstiege auslassen.",
                "minimum_future_test_trades": MIN_PROMOTION_TRADES,
                "uncertainty": "medium" if decisive >= 20 else "high",
                "status": "proposed",
                "created_at": created_at.isoformat(),
                "expires_at": (created_at + timedelta(days=180)).isoformat(),
            })
        return hypotheses

    def refresh_learning_state(self) -> Dict[str, Any]:
        if not self._refresh_lock.acquire(blocking=False):
            return {
                "schema": "paper-learning-refresh.v2",
                "status": "busy",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "retryable": True,
                "idempotent": True,
                "concurrency_guard": "process_local_non_blocking",
                "paper_only": True,
            }
        try:
            return self._refresh_learning_state_observed()
        finally:
            self._refresh_lock.release()

    def _refresh_learning_state_observed(self) -> Dict[str, Any]:
        run_id = f"plrun_{uuid.uuid4().hex[:20]}"
        started_at = datetime.now(timezone.utc).isoformat()
        started_clock = time.perf_counter()
        set_setting = getattr(self.portfolio_manager, "set_app_setting", None)
        persist_run = getattr(self.portfolio_manager, "upsert_paper_learning_run", None)
        running = {
            "schema": "paper-learning-refresh.v2",
            "run_id": run_id,
            "status": "running",
            "started_at": started_at,
            "retryable": True,
            "paper_only": True,
        }
        if callable(set_setting):
            set_setting("paper_learning_v2_last_result", json.dumps(running, ensure_ascii=True))
            set_setting("paper_learning_v2_last_started_at", started_at)
        if callable(persist_run):
            persist_run(running)
        try:
            result = self._refresh_learning_state_once()
            completed = {
                **result,
                "run_id": run_id,
                "started_at": started_at,
                "duration_ms": round((time.perf_counter() - started_clock) * 1000, 2),
                "retryable": True,
                "idempotent": True,
                "paper_only": True,
            }
            if callable(set_setting):
                set_setting("paper_learning_v2_last_result", json.dumps(completed, ensure_ascii=True))
                set_setting("paper_learning_v2_last_success_at", str(completed.get("checked_at") or ""))
                set_setting("paper_learning_v2_last_error", "")
            if callable(persist_run):
                persist_run(completed)
            return completed
        except Exception as exc:
            failed = {
                "schema": "paper-learning-refresh.v2",
                "run_id": run_id,
                "status": "error",
                "started_at": started_at,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": round((time.perf_counter() - started_clock) * 1000, 2),
                "error_type": exc.__class__.__name__,
                "error": str(exc)[:1000],
                "retryable": True,
                "idempotent": True,
                "paper_only": True,
            }
            if callable(set_setting):
                set_setting("paper_learning_v2_last_result", json.dumps(failed, ensure_ascii=True))
                set_setting("paper_learning_v2_last_error", f"{exc.__class__.__name__}: {str(exc)[:900]}")
            if callable(persist_run):
                persist_run(failed)
            raise

    def _refresh_learning_state_once(self) -> Dict[str, Any]:
        trades = self.portfolio_manager.list_paper_trades(limit=1000)
        outcomes = self.portfolio_manager.list_paper_trade_outcomes(limit=4000)
        outcomes_by_trade: Dict[str, List[Dict[str, Any]]] = {}
        for outcome in outcomes:
            outcomes_by_trade.setdefault(str(outcome.get("trade_id") or ""), []).append(outcome)
        attributed = 0
        for trade in trades:
            if trade.get("status") != "closed":
                continue
            attribution = self.build_attribution(trade, outcomes_by_trade.get(str(trade.get("id")), []))
            store_attribution = getattr(self.portfolio_manager, "upsert_paper_learning_attribution", None)
            if callable(store_attribution):
                store_attribution(attribution)
            attributed += 1
        list_attributions = getattr(self.portfolio_manager, "list_paper_learning_attributions", None)
        stored_attributions = list_attributions(limit=1000) if callable(list_attributions) else []
        segments = self._attribution_segment_rows(stored_attributions) if stored_attributions else self._segment_rows(outcomes)
        created_hypotheses: List[Dict[str, Any]] = []
        for hypothesis in self.build_hypotheses(segments):
            store_hypothesis = getattr(self.portfolio_manager, "upsert_paper_learning_hypothesis", None)
            ensure_shadow = getattr(self.portfolio_manager, "ensure_paper_learning_shadow_rule", None)
            if callable(store_hypothesis):
                stored = store_hypothesis(hypothesis)
                if callable(ensure_shadow):
                    ensure_shadow(stored)
                created_hypotheses.append(stored)
        shadow_evaluation = self._evaluate_shadow_rules(trades, outcomes)
        active_monitoring = self._monitor_active_rules(trades, outcomes)
        result = {
            "schema": "paper-learning-refresh.v2",
            "status": "ok",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "closed_trades_attributed": attributed,
            "segments": len(segments),
            "hypotheses": len(created_hypotheses),
            "shadow_evaluation": shadow_evaluation,
            "active_monitoring": active_monitoring,
        }
        return result

    def _monitor_active_rules(
        self,
        trades: List[Dict[str, Any]],
        outcomes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        list_rules = getattr(self.portfolio_manager, "list_paper_learning_rules", None)
        update_rule = getattr(self.portfolio_manager, "update_paper_learning_rule_status", None)
        if not callable(list_rules) or not callable(update_rule):
            return {"status": "not_persistent", "monitored_rules": 0, "auto_paused": 0, "alerts": []}
        active_rules = [
            item for item in list_rules(limit=500)
            if str(item.get("status") or "") == "active_paper"
        ]
        outcomes_by_trade: Dict[str, List[Dict[str, Any]]] = {}
        for outcome in outcomes:
            outcomes_by_trade.setdefault(str(outcome.get("trade_id") or ""), []).append(outcome)
        alerts: List[Dict[str, Any]] = []
        auto_paused = 0
        for rule in active_rules:
            rule_id = str(rule.get("id") or "")
            applied: List[Tuple[Dict[str, Any], float, Dict[str, Any]]] = []
            for trade in trades:
                if trade.get("status") != "closed":
                    continue
                ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
                snapshot = ticket.get("learning_feature_snapshot") if isinstance(ticket.get("learning_feature_snapshot"), dict) else {}
                scores = snapshot.get("scores") if isinstance(snapshot.get("scores"), dict) else {}
                applied_ids = scores.get("active_learning_rule_ids") if isinstance(scores.get("active_learning_rule_ids"), list) else []
                if rule_id not in {str(item) for item in applied_ids}:
                    continue
                attribution = self.build_attribution(trade, outcomes_by_trade.get(str(trade.get("id") or ""), []))
                pnl = self._safe_float((attribution.get("metrics") or {}).get("net_pnl_pct"))
                if pnl is not None:
                    applied.append((trade, pnl, attribution))
            applied.sort(key=lambda item: str(item[0].get("closed_at") or item[0].get("opened_at") or ""))
            window = applied[-ACTIVE_MONITOR_WINDOW:]
            values = [item[1] for item in window]
            metrics = self._performance_series_metrics(values)
            trailing_loss_streak = 0
            for value in reversed(values):
                if value < 0:
                    trailing_loss_streak += 1
                else:
                    break
            observations = len(values)
            expectancy = self._safe_float(metrics.get("expectancy_pct"))
            profit_factor = self._safe_float(metrics.get("profit_factor"))
            drawdown = self._safe_float(metrics.get("max_drawdown_pct_points")) or 0.0
            emergency = observations >= ACTIVE_EMERGENCY_LOSS_STREAK and trailing_loss_streak >= ACTIVE_EMERGENCY_LOSS_STREAK
            enough_sample = observations >= ACTIVE_MIN_MONITOR_TRADES
            pause_reasons: List[str] = []
            if emergency:
                pause_reasons.append("trailing_loss_streak")
            if enough_sample and expectancy is not None and expectancy <= 0:
                pause_reasons.append("non_positive_expectancy")
            if enough_sample and profit_factor is not None and profit_factor < ACTIVE_MIN_PROFIT_FACTOR:
                pause_reasons.append("profit_factor_below_floor")
            if enough_sample and drawdown > ACTIVE_MAX_DRAWDOWN:
                pause_reasons.append("drawdown_limit_exceeded")
            evaluation = rule.get("evaluation") if isinstance(rule.get("evaluation"), dict) else {}
            benchmark = (
                ((evaluation.get("champion_challenger") or {}).get("challenger") or {})
                if isinstance(evaluation.get("champion_challenger"), dict)
                else {}
            )
            benchmark_expectancy = self._safe_float(benchmark.get("expectancy_pct"))
            warning_reasons: List[str] = []
            if (
                enough_sample
                and benchmark_expectancy is not None
                and benchmark_expectancy > 0
                and expectancy is not None
                and expectancy < benchmark_expectancy * 0.5
            ):
                warning_reasons.append("expectancy_below_half_of_shadow_benchmark")
            monitored_at = datetime.now(timezone.utc).isoformat()
            monitor = {
                "schema": "paper-learning-active-monitor.v1",
                "status": "auto_paused" if pause_reasons else "warning" if warning_reasons else "healthy" if enough_sample else "collecting",
                "monitored_at": monitored_at,
                "window_size": ACTIVE_MONITOR_WINDOW,
                "observations": observations,
                "minimum_observations": ACTIVE_MIN_MONITOR_TRADES,
                "metrics": metrics,
                "trailing_loss_streak": trailing_loss_streak,
                "pause_reasons": pause_reasons,
                "warning_reasons": warning_reasons,
                "thresholds": {
                    "emergency_loss_streak": ACTIVE_EMERGENCY_LOSS_STREAK,
                    "minimum_profit_factor": ACTIVE_MIN_PROFIT_FACTOR,
                    "maximum_drawdown_pct_points": ACTIVE_MAX_DRAWDOWN,
                },
                "trade_ids": [str(item[0].get("id") or "") for item in window],
                "paper_only": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            }
            updated_evaluation = {**evaluation, "live_monitor": monitor}
            if not pause_reasons:
                update_rule(rule_id, "active_paper", updated_evaluation)
                if warning_reasons:
                    alerts.append({"rule_id": rule_id, "severity": "warning", "reasons": warning_reasons})
                continue
            monitor["reactivation_policy"] = "Create and validate a new shadow-rule version; direct rollback to active is blocked."
            updated = update_rule(rule_id, "paused", updated_evaluation)
            reason = "Automatic paper safety pause: " + ", ".join(pause_reasons)
            audit = self.portfolio_manager.record_decision_audit(
                event_type="paper_learning_rule_change",
                subject=rule_id,
                decision="paused",
                data_as_of=monitored_at,
                source_status="internal_paper_evidence",
                sources=[],
                model_version="paper-learning-engine.v2",
                rule_version=POLICY_VERSION,
                user_action="paper_learning_rule_auto_pause",
                payload={"before": rule, "after": updated, "reason": reason, "monitor": monitor},
            )
            record_history = getattr(self.portfolio_manager, "record_paper_learning_rule_history", None)
            if callable(record_history):
                record_history(
                    rule_id=rule_id,
                    action="auto_pause",
                    before=rule,
                    after=updated or {},
                    reason=reason,
                    audit_event_id=str(audit.get("event_hash") or audit.get("id") or "") or None,
                )
            alerts.append({"rule_id": rule_id, "severity": "critical", "reasons": pause_reasons})
            auto_paused += 1
        return {
            "status": "ok",
            "monitored_rules": len(active_rules),
            "auto_paused": auto_paused,
            "alerts": alerts,
            "paper_only": True,
        }

    def _evaluate_shadow_rules(
        self,
        trades: List[Dict[str, Any]],
        outcomes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        list_rules = getattr(self.portfolio_manager, "list_paper_learning_rules", None)
        list_hypotheses = getattr(self.portfolio_manager, "list_paper_learning_hypotheses", None)
        update_rule = getattr(self.portfolio_manager, "update_paper_learning_rule_status", None)
        if not all(callable(item) for item in (list_rules, list_hypotheses, update_rule)):
            return {"status": "not_persistent", "evaluated_rules": 0, "eligible": 0}
        rules = list_rules(limit=500)
        hypotheses = {str(item.get("id")): item for item in list_hypotheses(limit=500)}
        trade_by_id = {str(item.get("id")): item for item in trades}
        global_decisive = sum(1 for item in outcomes if item.get("result") in {"hit", "miss"})
        evaluated_rules = 0
        eligible_count = 0
        for rule in rules:
            if rule.get("status") not in {"shadow", "eligible_for_paper_review"}:
                continue
            hypothesis = hypotheses.get(str(rule.get("hypothesis_id"))) or {}
            segment = hypothesis.get("segment") if isinstance(hypothesis.get("segment"), dict) else {}
            started_at = str(rule.get("started_at") or rule.get("created_at") or "")
            boundary = self._experiment_boundary(started_at, trades, outcomes, segment)
            embargo_until = self._as_utc_datetime(boundary.get("embargo_until"))
            future_outcomes: List[Dict[str, Any]] = []
            excluded_by_embargo: set[str] = set()
            for outcome in outcomes:
                if outcome.get("status") != "evaluated":
                    continue
                linked_trade = trade_by_id.get(str(outcome.get("trade_id") or "")) or {}
                checked_at = self._as_utc_datetime(outcome.get("checked_at"))
                due_at = self._as_utc_datetime(outcome.get("due_at"))
                opened_at = self._as_utc_datetime(linked_trade.get("opened_at"))
                if (
                    checked_at is None
                    or due_at is None
                    or opened_at is None
                    or embargo_until is None
                    or checked_at < due_at
                    or opened_at <= embargo_until
                ):
                    if opened_at is not None and embargo_until is not None and opened_at <= embargo_until:
                        excluded_by_embargo.add(str(linked_trade.get("id") or outcome.get("trade_id") or ""))
                    continue
                match_item = {**linked_trade, **outcome, "market_regime": self._item_regime(linked_trade)}
                if not self._matches_segment(match_item, segment):
                    continue
                future_outcomes.append(outcome)
            hits = sum(1 for item in future_outcomes if item.get("result") == "hit")
            misses = sum(1 for item in future_outcomes if item.get("result") == "miss")
            decisive = hits + misses
            future_trade_ids = {str(item.get("trade_id")) for item in future_outcomes}
            future_closed = [
                trade_by_id[trade_id]
                for trade_id in future_trade_ids
                if trade_id in trade_by_id and trade_by_id[trade_id].get("status") == "closed"
            ]
            pnl_values: List[float] = []
            future_attributions: List[Dict[str, Any]] = []
            attribution_by_trade: Dict[str, Dict[str, Any]] = {}
            for trade in future_closed:
                attribution = self.build_attribution(
                    trade,
                    [item for item in future_outcomes if str(item.get("trade_id")) == str(trade.get("id"))],
                )
                pnl = self._safe_float((attribution.get("metrics") or {}).get("net_pnl_pct"))
                if pnl is not None:
                    pnl_values.append(pnl)
                future_attributions.append(attribution)
                attribution_by_trade[str(trade.get("id"))] = attribution

            proposal = rule.get("rule") if isinstance(rule.get("rule"), dict) else {}
            proposed_delta = self._safe_float(proposal.get("score_delta")) or 0.0
            proposed_delta = max(-MAX_SINGLE_SCORE_DELTA, min(MAX_SINGLE_SCORE_DELTA, proposed_delta))
            proposed_risk_cap = self._safe_float(proposal.get("paper_risk_multiplier_cap"))
            risk_cap = max(0.01, min(1.0, proposed_risk_cap if proposed_risk_cap is not None else 1.0))
            comparison_rows: List[Dict[str, Any]] = []
            champion_values: List[float] = []
            challenger_values: List[float] = []
            comparison_complete = True
            for trade in sorted(future_closed, key=lambda item: str(item.get("opened_at") or "")):
                attribution = attribution_by_trade.get(str(trade.get("id"))) or {}
                pnl = self._safe_float((attribution.get("metrics") or {}).get("net_pnl_pct"))
                ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
                snapshot = ticket.get("learning_feature_snapshot") if isinstance(ticket.get("learning_feature_snapshot"), dict) else {}
                entry_score = self._safe_float((snapshot.get("scores") or {}).get("final_score"))
                minimum_score = self._safe_float((snapshot.get("gate_decision") or {}).get("minimum_trade_score"))
                comparable = pnl is not None and entry_score is not None and minimum_score is not None
                comparison_complete = comparison_complete and comparable
                adjusted_score = entry_score + proposed_delta if entry_score is not None else None
                challenger_selected = bool(comparable and adjusted_score is not None and adjusted_score >= minimum_score)
                champion_value = pnl if pnl is not None else 0.0
                challenger_value = (pnl * risk_cap) if pnl is not None and challenger_selected else 0.0
                champion_values.append(champion_value)
                challenger_values.append(challenger_value)
                comparison_rows.append({
                    "trade_id": trade.get("id"),
                    "opened_at": trade.get("opened_at"),
                    "entry_score": entry_score,
                    "minimum_score": minimum_score,
                    "challenger_score": round(adjusted_score, 2) if adjusted_score is not None else None,
                    "challenger_selected": challenger_selected,
                    "champion_return_pct": pnl,
                    "challenger_risk_adjusted_return_pct": round(challenger_value, 3),
                    "comparable": comparable,
                })
            champion_metrics = self._performance_series_metrics(champion_values)
            challenger_metrics = self._performance_series_metrics(challenger_values)
            profit_factor = self._safe_float(challenger_metrics.get("profit_factor"))
            expectancy = self._safe_float(challenger_metrics.get("expectancy_pct"))
            max_drawdown = self._safe_float(challenger_metrics.get("max_drawdown_pct_points")) or 0.0
            champion_expectancy = self._safe_float(champion_metrics.get("expectancy_pct"))
            expectancy_delta = (
                round(expectancy - champion_expectancy, 3)
                if expectancy is not None and champion_expectancy is not None
                else None
            )
            challenger_not_worse = bool(
                comparison_complete
                and expectancy_delta is not None
                and expectancy_delta >= 0
                and float(challenger_metrics.get("max_drawdown_pct_points") or 0)
                <= float(champion_metrics.get("max_drawdown_pct_points") or 0)
            )
            good_process_count = sum(
                1
                for item in future_attributions
                if str(item.get("process_quality") or "").startswith("good_process")
            )
            good_process_rate = (
                round(good_process_count / len(future_attributions) * 100, 1)
                if future_attributions
                else None
            )
            data_integrity_ok = bool(
                future_attributions
                and all(
                    not str(item.get("primary_error") or "").startswith("data_quality.")
                    and (item.get("evidence") or {}).get("snapshot_hash")
                    for item in future_attributions
                )
            )
            instrument_counts: Dict[str, int] = {}
            for trade in future_closed:
                instrument = str(trade.get("ticker") or trade.get("instrument") or "unknown")
                instrument_counts[instrument] = instrument_counts.get(instrument, 0) + 1
            largest_instrument_count = max(instrument_counts.values(), default=0)
            instrument_concentration = (
                round(largest_instrument_count / len(future_closed) * 100, 1)
                if future_closed
                else None
            )
            promotion_checks = {
                "global_outcomes": global_decisive >= GLOBAL_OUTCOME_TARGET,
                "future_decisive": decisive >= MIN_PROMOTION_TRADES,
                "future_closed_trades": len(future_closed) >= MIN_PROMOTION_TRADES,
                "profit_factor": profit_factor is not None and profit_factor >= 1.2,
                "positive_expectancy": expectancy is not None and expectancy > 0,
                "drawdown": max_drawdown <= 15.0,
                "process_quality": good_process_rate is not None and good_process_rate >= MIN_GOOD_PROCESS_RATE,
                "data_integrity": data_integrity_ok,
                "instrument_concentration": (
                    instrument_concentration is not None
                    and instrument_concentration <= MAX_INSTRUMENT_CONCENTRATION
                ),
                "future_only_holdout": True,
                "purge_embargo": boundary.get("valid") is True,
                "champion_challenger": challenger_not_worse,
            }
            promotion_blockers = [key for key, passed in promotion_checks.items() if not passed]
            eligible = not promotion_blockers
            evaluation = {
                "schema": "paper-learning-shadow-evaluation.v2",
                "evaluation_mode": "future_only_segment_shadow",
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "experiment_started_at": started_at,
                "future_decisive": decisive,
                "future_closed_trades": len(future_closed),
                "global_decisive_outcomes": global_decisive,
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hits / decisive * 100, 1) if decisive else None,
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "max_drawdown_pct": round(max_drawdown, 3),
                "drawdown_ok": max_drawdown <= 15.0,
                "good_process_rate": good_process_rate,
                "minimum_good_process_rate": MIN_GOOD_PROCESS_RATE,
                "data_integrity_ok": data_integrity_ok,
                "largest_instrument_concentration_pct": instrument_concentration,
                "maximum_instrument_concentration_pct": MAX_INSTRUMENT_CONCENTRATION,
                "promotion_checks": promotion_checks,
                "promotion_blockers": promotion_blockers,
                "eligible_for_paper_review": eligible,
                "future_data_only": True,
                "pre_existing_trades_excluded": True,
                "purge_embargo": boundary,
                "champion_challenger": {
                    "schema": "paper-learning-champion-challenger.v1",
                    "comparison_mode": "same_future_candidates_counterfactual_paper_filter",
                    "comparison_complete": comparison_complete,
                    "proposed_score_delta": proposed_delta,
                    "paper_risk_multiplier_cap": risk_cap,
                    "champion": champion_metrics,
                    "challenger": {
                        **challenger_metrics,
                        "selected_trades": sum(1 for item in comparison_rows if item.get("challenger_selected")),
                        "rejected_trades": sum(1 for item in comparison_rows if item.get("comparable") and not item.get("challenger_selected")),
                    },
                    "expectancy_delta_pct": expectancy_delta,
                    "challenger_not_worse": challenger_not_worse,
                    "rows": comparison_rows,
                    "causality_policy": "Counterfactual paper comparison on the same future candidates; not causal proof.",
                },
                "excluded_trade_ids_by_embargo": sorted(item for item in excluded_by_embargo if item),
                "excluded_trade_count_by_embargo": len([item for item in excluded_by_embargo if item]),
                "paper_only": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            }
            target_status = "eligible_for_paper_review" if eligible else "shadow"
            update_rule(rule["id"], target_status, evaluation)
            evaluated_rules += 1
            eligible_count += 1 if eligible else 0
        return {"status": "ok", "evaluated_rules": evaluated_rules, "eligible": eligible_count}

    def build_dashboard(self) -> Dict[str, Any]:
        trades = self.portfolio_manager.list_paper_trades(limit=1000)
        outcomes = self.portfolio_manager.list_paper_trade_outcomes(limit=4000)
        list_attributions = getattr(self.portfolio_manager, "list_paper_learning_attributions", None)
        list_hypotheses = getattr(self.portfolio_manager, "list_paper_learning_hypotheses", None)
        list_rules = getattr(self.portfolio_manager, "list_paper_learning_rules", None)
        list_runs = getattr(self.portfolio_manager, "list_paper_learning_runs", None)
        list_rule_history = getattr(self.portfolio_manager, "list_paper_learning_rule_history", None)
        attributions = list_attributions(limit=1000) if callable(list_attributions) else []
        hypotheses = list_hypotheses(limit=200) if callable(list_hypotheses) else []
        rules = list_rules(limit=200) if callable(list_rules) else []
        recent_runs = list_runs(limit=20) if callable(list_runs) else []
        rule_history = list_rule_history(limit=50) if callable(list_rule_history) else []
        segments = self._attribution_segment_rows(attributions) if attributions else self._segment_rows(outcomes)
        closed = [trade for trade in trades if trade.get("status") == "closed"]
        decisive = [item for item in outcomes if item.get("result") in {"hit", "miss"}]
        good_process = sum(1 for item in attributions if str(item.get("process_quality") or "").startswith("good_process"))
        missing_snapshot = sum(1 for item in attributions if item.get("primary_error") == "data_quality.feature_snapshot_missing")
        missing_asset_features = sum(1 for item in attributions if item.get("primary_error") == "data_quality.asset_features_missing")
        missing_market_regime = sum(
            1 for item in attributions
            if "unknown" in self._item_regime(item).values()
        )
        missing_journal = [
            trade
            for trade in closed
            if not str(trade.get("exit_reason") or "").strip()
            or not str(trade.get("lessons_learned") or "").strip()
        ]
        due_reader = getattr(self.portfolio_manager, "list_due_paper_trade_outcomes", None)
        due_outcomes = due_reader(limit=1000) if callable(due_reader) else []
        pending_outcomes = [
            item for item in outcomes if str(item.get("status") or "") in {"pending", "pending_data"}
        ]
        last_result: Dict[str, Any] = {}
        get_setting = getattr(self.portfolio_manager, "get_app_setting", None)
        if callable(get_setting):
            try:
                parsed = json.loads(get_setting("paper_learning_v2_last_result", "{}") or "{}")
                last_result = parsed if isinstance(parsed, dict) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                last_result = {}
        last_checked_at = last_result.get("checked_at")
        last_started_at = last_result.get("started_at")
        last_observed_at = last_checked_at or last_started_at
        last_run_age_minutes = None
        if last_observed_at:
            try:
                checked = datetime.fromisoformat(str(last_observed_at).replace("Z", "+00:00"))
                if checked.tzinfo is None:
                    checked = checked.replace(tzinfo=timezone.utc)
                last_run_age_minutes = max(
                    0,
                    int((datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds() // 60),
                )
            except (TypeError, ValueError):
                last_run_age_minutes = None
        eligible_rules = [item for item in rules if item.get("status") == "eligible_for_paper_review"]
        monitored_warnings = [
            item for item in rules
            if ((item.get("evaluation") or {}).get("live_monitor") or {}).get("status") in {"warning", "auto_paused"}
        ]
        if due_outcomes:
            next_action = {
                "code": "evaluate_due_outcomes",
                "priority": "high",
                "title": f"{len(due_outcomes)} fällige Outcomes auswerten",
                "detail": "Nur bereits fällige Zeitfenster werden geprüft; der Lauf ist idempotent.",
            }
        elif missing_journal:
            next_action = {
                "code": "complete_journals",
                "priority": "high",
                "title": f"{len(missing_journal)} Lernjournale vervollständigen",
                "detail": "Exit-Grund und Lektion fehlen; ohne sie bleibt die Prozessbewertung unvollständig.",
            }
        elif monitored_warnings:
            next_action = {
                "code": "review_active_rule_drift",
                "priority": "high",
                "title": f"{len(monitored_warnings)} Lernregeln wegen Drift prüfen",
                "detail": "Automatisch pausierte Regeln bleiben deaktiviert; betroffene Regeln müssen als neue Shadow-Version validiert werden.",
            }
        elif eligible_rules:
            next_action = {
                "code": "review_eligible_rules",
                "priority": "medium",
                "title": f"{len(eligible_rules)} Shadow-Regeln manuell prüfen",
                "detail": "Eine Freigabe wirkt weiterhin ausschließlich auf zukünftige Paper-Trades.",
            }
        elif len(decisive) < GLOBAL_OUTCOME_TARGET:
            next_action = {
                "code": "collect_evidence",
                "priority": "normal",
                "title": f"Noch {GLOBAL_OUTCOME_TARGET - len(decisive)} entscheidende Outcomes sammeln",
                "detail": "Nur qualifizierte Setups handeln; keine Trades allein zum Erreichen der Stichprobe öffnen.",
            }
        else:
            next_action = {
                "code": "monitor_learning",
                "priority": "normal",
                "title": "Lernregeln und Regimeverteilung überwachen",
                "detail": "Neue Änderungen weiterhin zuerst mit zukünftigen Shadow-Daten testen.",
            }
        top_errors: Dict[str, int] = {}
        for item in attributions:
            key = str(item.get("primary_error") or "unclassified")
            top_errors[key] = top_errors.get(key, 0) + 1
        trade_by_id = {str(item.get("id")): item for item in trades}
        outcomes_by_trade: Dict[str, List[Dict[str, Any]]] = {}
        for outcome in outcomes:
            outcomes_by_trade.setdefault(str(outcome.get("trade_id") or ""), []).append(outcome)
        recent_trade_reviews = []
        for attribution in attributions[:8]:
            trade_id = str(attribution.get("trade_id") or "")
            trade = trade_by_id.get(trade_id)
            if trade:
                recent_trade_reviews.append(
                    self._compose_trade_detail(trade, outcomes_by_trade.get(trade_id, []), attribution)
                )
        return {
            "schema": "paper-learning-dashboard.v2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "paper_trades": len(trades),
                "closed_trades": len(closed),
                "decisive_outcomes": len(decisive),
                "global_outcome_target": GLOBAL_OUTCOME_TARGET,
                "global_outcomes_remaining": max(0, GLOBAL_OUTCOME_TARGET - len(decisive)),
                "attributed_trades": len(attributions),
                "good_process_rate": round(good_process / len(attributions) * 100, 1) if attributions else None,
                "missing_feature_snapshots": missing_snapshot,
                "missing_asset_features": missing_asset_features,
                "missing_market_regime": missing_market_regime,
                "shadow_rules": sum(1 for rule in rules if rule.get("status") == "shadow"),
                "active_paper_rules": sum(1 for rule in rules if rule.get("status") == "active_paper"),
                "active_monitor_warnings": len(monitored_warnings),
            },
            "segments": segments,
            "top_errors": [
                {"error": key, "count": count}
                for key, count in sorted(top_errors.items(), key=lambda item: item[1], reverse=True)[:8]
            ],
            "recent_attributions": attributions[:20],
            "recent_trade_reviews": recent_trade_reviews,
            "hypotheses": hypotheses[:20],
            "rules": rules[:20],
            "rule_history": rule_history,
            "recent_runs": recent_runs,
            "operations": {
                "status": (
                    "action_required"
                    if due_outcomes or missing_journal
                    else "review"
                    if eligible_rules
                    else "collecting_evidence"
                ),
                "last_run": {
                    "checked_at": last_checked_at,
                    "started_at": last_started_at,
                    "run_id": last_result.get("run_id"),
                    "age_minutes": last_run_age_minutes,
                    "status": last_result.get("status") or "not_started",
                    "duration_ms": last_result.get("duration_ms"),
                    "retryable": last_result.get("retryable"),
                    "attributed": last_result.get("closed_trades_attributed"),
                    "error": last_result.get("error"),
                },
                "due_outcomes": len(due_outcomes),
                "pending_outcomes": len(pending_outcomes),
                "open_trades": sum(1 for trade in trades if trade.get("status") == "open"),
                "missing_journals": len(missing_journal),
                "eligible_rules": len(eligible_rules),
                "blockers": [
                    item
                    for item in (
                        f"{len(due_outcomes)} fällige Outcomes" if due_outcomes else None,
                        f"{len(missing_journal)} unvollständige Journale" if missing_journal else None,
                        f"{missing_snapshot} fehlende Entry-Snapshots" if missing_snapshot else None,
                        f"{missing_asset_features} unvollständige Asset-Datensätze" if missing_asset_features else None,
                        f"{missing_market_regime} fehlende Marktregime" if missing_market_regime else None,
                    )
                    if item
                ],
                "next_action": next_action,
                "paper_only": True,
            },
            "policy": {
                "version": POLICY_VERSION,
                "min_adjustment_sample": MIN_ADJUSTMENT_SAMPLE,
                "min_promotion_trades": MIN_PROMOTION_TRADES,
                "max_single_score_delta": MAX_SINGLE_SCORE_DELTA,
                "max_total_score_delta": MAX_TOTAL_SCORE_DELTA,
                "min_good_process_rate": MIN_GOOD_PROCESS_RATE,
                "max_instrument_concentration_pct": MAX_INSTRUMENT_CONCENTRATION,
                "active_monitor_window": ACTIVE_MONITOR_WINDOW,
                "active_min_monitor_trades": ACTIVE_MIN_MONITOR_TRADES,
                "active_emergency_loss_streak": ACTIVE_EMERGENCY_LOSS_STREAK,
                "active_min_profit_factor": ACTIVE_MIN_PROFIT_FACTOR,
                "active_max_drawdown_pct_points": ACTIVE_MAX_DRAWDOWN,
                "paper_only": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
                "message": "Learning changes require future shadow evidence; hard risk caps never change.",
            },
        }

    def rollback_preview(self, rule_id: str) -> Dict[str, Any]:
        rules = self.portfolio_manager.list_paper_learning_rules(limit=1000)
        rule = next((item for item in rules if str(item.get("id")) == str(rule_id)), None)
        if not rule:
            raise ValueError("Paper learning rule not found.")
        list_history = getattr(self.portfolio_manager, "list_paper_learning_rule_history", None)
        if not callable(list_history):
            raise ValueError("Paper learning rule history is unavailable.")
        history = list_history(rule_id=rule_id, limit=1)
        if not history:
            raise ValueError("No previous rule state is available for rollback.")
        source = history[0]
        previous = source.get("before") if isinstance(source.get("before"), dict) else {}
        restore_status = str(previous.get("status") or "").strip()
        restore_evaluation = previous.get("evaluation") if isinstance(previous.get("evaluation"), dict) else {}
        if not restore_status:
            raise ValueError("The previous rule state is incomplete and cannot be restored.")
        return {
            "status": "ok",
            "rule_id": str(rule_id),
            "current": {
                "status": rule.get("status"),
                "version": rule.get("version"),
                "evaluation": rule.get("evaluation") if isinstance(rule.get("evaluation"), dict) else {},
            },
            "restore": {
                "status": restore_status,
                "version": previous.get("version", rule.get("version")),
                "evaluation": restore_evaluation,
            },
            "source_history_id": source.get("id"),
            "source_action": source.get("action"),
            "paper_only": True,
            "real_money_execution_allowed": False,
            "automatic_execution_allowed": False,
        }

    def review_rule(self, rule_id: str, action: str, reason: str = "") -> Dict[str, Any]:
        review_reason = str(reason or "").strip()
        if len(review_reason) < 8:
            raise ValueError("A manual rule decision requires a review reason with at least 8 characters.")
        rules = self.portfolio_manager.list_paper_learning_rules(limit=1000)
        rule = next((item for item in rules if str(item.get("id")) == str(rule_id)), None)
        if not rule:
            raise ValueError("Paper learning rule not found.")
        normalized = str(action or "").strip().lower()
        target_by_action = {
            "pause": "paused",
            "reject": "rejected",
            "activate_paper": "active_paper",
        }
        if normalized not in {*target_by_action, "rollback", "restart_shadow"}:
            raise ValueError("Unsupported paper learning rule action.")
        if normalized == "restart_shadow":
            if str(rule.get("status") or "") != "paused":
                raise ValueError("Only a paused paper rule can restart as a new shadow version.")
            create_version = getattr(self.portfolio_manager, "create_paper_learning_rule_version", None)
            if not callable(create_version):
                raise ValueError("Paper learning rule versioning is unavailable.")
            created = create_version(rule_id)
            audit = self.portfolio_manager.record_decision_audit(
                event_type="paper_learning_rule_change",
                subject=str(created.get("id") or rule_id),
                decision="shadow",
                data_as_of=datetime.now(timezone.utc).isoformat(),
                source_status="internal_paper_evidence",
                sources=[],
                model_version="paper-learning-engine.v2",
                rule_version=POLICY_VERSION,
                user_action="paper_learning_rule_restart_shadow",
                payload={
                    "before": rule,
                    "after": created,
                    "reason": review_reason,
                    "supersedes_rule_id": rule_id,
                    "real_money_execution_allowed": False,
                    "automatic_execution_allowed": False,
                },
            )
            record_history = getattr(self.portfolio_manager, "record_paper_learning_rule_history", None)
            history = record_history(
                rule_id=rule_id,
                action=normalized,
                before=rule,
                after=created,
                reason=review_reason,
                audit_event_id=str(audit.get("event_hash") or audit.get("id") or "") or None,
            ) if callable(record_history) else None
            return {"status": "ok", "rule": created, "audit": audit, "history": history, "supersedes_rule_id": rule_id}
        baseline = rule.get("baseline") if isinstance(rule.get("baseline"), dict) else {}
        evaluation = rule.get("evaluation") if isinstance(rule.get("evaluation"), dict) else {}
        rollback = self.rollback_preview(rule_id) if normalized == "rollback" else None
        target = str((rollback or {}).get("restore", {}).get("status") or target_by_action.get(normalized) or "")
        if rollback and target == "active_paper" and rollback.get("source_action") == "auto_pause":
            raise ValueError(
                "An automatic paper safety pause cannot be rolled back to active. "
                "Create and validate a new shadow-rule version instead."
            )
        if target == "active_paper":
            decisive = int(evaluation.get("future_decisive") or 0)
            closed_trades = int(evaluation.get("future_closed_trades") or 0)
            profit_factor = self._safe_float(evaluation.get("profit_factor"))
            expectancy = self._safe_float(evaluation.get("expectancy"))
            drawdown_ok = evaluation.get("drawdown_ok") is True
            promotion_checks = evaluation.get("promotion_checks") if isinstance(evaluation.get("promotion_checks"), dict) else {}
            required_checks = {
                "global_outcomes",
                "future_decisive",
                "future_closed_trades",
                "profit_factor",
                "positive_expectancy",
                "drawdown",
                "process_quality",
                "data_integrity",
                "instrument_concentration",
                "future_only_holdout",
                "purge_embargo",
                "champion_challenger",
            }
            if (
                decisive < MIN_PROMOTION_TRADES
                or closed_trades < MIN_PROMOTION_TRADES
                or profit_factor is None
                or profit_factor < 1.2
                or expectancy is None
                or expectancy <= 0
                or not drawdown_ok
                or any(promotion_checks.get(check) is not True for check in required_checks)
            ):
                raise ValueError(
                    "Rule remains shadow-only: 30 future decisive checks and closed trades, "
                    "100 global outcomes, profit factor >=1.20, positive expectancy, drawdown, "
                    "process quality, data integrity, concentration and holdout gates are required."
                )
        updated_evaluation = (
            dict((rollback or {}).get("restore", {}).get("evaluation") or {})
            if rollback
            else {
                **evaluation,
                "review_reason": review_reason[:1000],
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "baseline_at_review": baseline,
                "paper_only": True,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            }
        )
        updated = self.portfolio_manager.update_paper_learning_rule_status(rule_id, target, updated_evaluation)
        audit = self.portfolio_manager.record_decision_audit(
            event_type="paper_learning_rule_change",
            subject=rule_id,
            decision=target,
            data_as_of=datetime.now(timezone.utc).isoformat(),
            source_status="internal_paper_evidence",
            sources=[],
            model_version="paper-learning-engine.v2",
            rule_version=POLICY_VERSION,
            user_action=f"paper_learning_rule_{normalized}",
            payload={
                "before": rule,
                "after": updated,
                "reason": review_reason,
                "real_money_execution_allowed": False,
                "automatic_execution_allowed": False,
            },
        )
        record_history = getattr(self.portfolio_manager, "record_paper_learning_rule_history", None)
        history = None
        if callable(record_history):
            history = record_history(
                rule_id=rule_id,
                action=normalized,
                before=rule,
                after=updated or {},
                reason=review_reason,
                audit_event_id=str(audit.get("event_hash") or audit.get("id") or "") or None,
            )
        return {"status": "ok", "rule": updated, "audit": audit, "history": history, "rollback": rollback}
