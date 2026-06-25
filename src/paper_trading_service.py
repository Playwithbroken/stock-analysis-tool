from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import yfinance as yf

from src.storage import PortfolioManager
from src.strategy_library import StrategyLibrary

DEFAULT_PAPER_OUTCOME_HORIZONS_HOURS = (1, 24, 72, 168)


class PaperTradingService:
    def __init__(self, portfolio_manager: PortfolioManager) -> None:
        self.portfolio_manager = portfolio_manager

    def build_dashboard(self, scoreboard: Dict[str, Any], settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
        settings = settings or {}
        rules = settings.get("do_not_trade") or {}
        outcome_learning = self._build_outcome_learning_adjustments()
        playbooks = self._build_playbooks(scoreboard, rules, outcome_learning)
        trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(limit=150))
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        closed_trades = [trade for trade in trades if trade.get("status") == "closed"]
        demo_account = self._build_demo_account(trades, playbooks)
        sized_playbooks = self._attach_demo_sizing(playbooks, demo_account)
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "playbooks": sized_playbooks,
            "strategy_library": StrategyLibrary.all(),
            "strategy_readiness": StrategyLibrary.build_readiness(trades, self.portfolio_manager.list_paper_trade_outcomes(limit=800)),
            "open_trades": open_trades[:12],
            "closed_trades": closed_trades[:12],
            "stats": self._build_stats(trades),
            "setup_performance": self._build_setup_performance(closed_trades),
            "journal": self._build_journal(trades),
            "outcomes": self._build_outcome_dashboard(),
            "outcome_learning": outcome_learning,
            "rules": rules,
            "demo_account": demo_account,
            "auto_selection": self._build_auto_selection(sized_playbooks, trades, demo_account),
            "auto_learn_status": self._build_auto_learn_status(),
        }

    def _build_auto_learn_status(self) -> Dict[str, Any]:
        raw = self.portfolio_manager.get_app_setting("paper_learning_autopilot_last_run")
        if not raw:
            return {
                "status": "not_started",
                "message": "Scheduled paper auto-learn has not run yet.",
            }
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {
            "status": "unknown",
            "message": "Scheduled paper auto-learn status could not be parsed.",
        }

    def run_auto_selection(
        self,
        scoreboard: Dict[str, Any],
        settings: Dict[str, Any] | None = None,
        max_trades: int = 3,
        execute: bool = False,
        mode: str = "strict",
    ) -> Dict[str, Any]:
        dashboard = self.build_dashboard(scoreboard, settings)
        selection = dashboard.get("auto_selection", {})
        mode = "learn" if str(mode or "").lower() == "learn" else "strict"
        source_key = "exploration" if mode == "learn" else "selected"
        selected = selection.get(source_key, [])[: max(1, int(max_trades or 1))]
        if not execute:
            return {
                "status": "preview",
                "execute": False,
                "mode": mode,
                "selected": selected,
                "opened": [],
                "message": (
                    f"{len(selected)} learning candidate(s) passed the exploration gates."
                    if mode == "learn"
                    else f"{len(selected)} demo candidate(s) passed the auto-selection gates."
                ),
            }

        opened: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for candidate in selected:
            try:
                opened.append(
                    self.create_trade_from_playbook(
                        {
                            "playbook_id": candidate.get("id"),
                            "direction": candidate.get("direction") or "long",
                            "quantity": candidate.get("suggested_quantity") or 0,
                            "leverage": 1,
                            "learning_mode": mode == "learn" or bool(candidate.get("learning_mode")),
                        },
                        scoreboard,
                        settings,
                    )
                )
            except Exception as exc:
                errors.append(
                    {
                        "id": candidate.get("id"),
                        "ticker": candidate.get("ticker"),
                        "error": str(exc),
                    }
                )
        return {
            "status": "ok" if not errors else "partial",
            "execute": True,
            "mode": mode,
            "selected": selected,
            "opened": opened,
            "errors": errors,
            "message": (
                f"Opened {len(opened)} paper learning trade(s); {len(errors)} blocked during final gate."
                if mode == "learn"
                else f"Opened {len(opened)} paper trade(s); {len(errors)} blocked during final gate."
            ),
        }

    def create_trade_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade = self.portfolio_manager.create_paper_trade(payload)
        self._schedule_trade_outcomes(trade)
        return self._enrich_trade(trade)

    def create_trade_from_playbook(
        self,
        payload: Dict[str, Any],
        scoreboard: Dict[str, Any],
        settings: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        playbook_id = payload.get("playbook_id")
        direction = (payload.get("direction") or "long").lower()
        requested_quantity = float(payload.get("quantity") or 0)
        leverage = float(payload.get("leverage") or 1)
        rules = (settings or {}).get("do_not_trade") or {}
        outcome_learning = self._build_outcome_learning_adjustments()
        playbooks = self._build_playbooks(scoreboard, rules, outcome_learning)
        trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(limit=150))
        demo_account = self._build_demo_account(trades, playbooks)
        playbooks = self._attach_demo_sizing(playbooks, demo_account)
        playbook = next((item for item in playbooks if item.get("id") == playbook_id), None)
        if not playbook:
            raise ValueError("Playbook not found.")
        learning_mode = bool(payload.get("learning_mode"))
        hard_rule_reasons = [
            str(item)
            for item in playbook.get("do_not_trade_reasons", [])
            if not str(item).lower().startswith("score below minimum trade score")
        ]
        hard_demo_reasons = [
            str(item)
            for item in playbook.get("demo_block_reasons", [])
            if str(item) != "Playbook is blocked by signal rules." or hard_rule_reasons
        ]
        if playbook.get("do_not_trade_reasons") and (not learning_mode or hard_rule_reasons):
            raise ValueError("Playbook is blocked by do-not-trade rules.")
        if playbook.get("demo_block_reasons") and (not learning_mode or hard_demo_reasons):
            raise ValueError("Demo account risk gate blocks this playbook.")

        is_option = playbook.get("asset_class") == "option"
        if is_option:
            direction = playbook.get("direction") or direction
            last_price = float(playbook.get("reference_price") or 0)
        else:
            last_price = self._get_last_price(playbook.get("ticker")) or float(playbook.get("reference_price") or 0)
        if last_price <= 0:
            raise ValueError("No valid market price available for this playbook.")
        quantity = requested_quantity if requested_quantity > 0 else float(playbook.get("suggested_quantity") or 1)
        if quantity <= 0:
            raise ValueError("No valid demo quantity available for this playbook.")

        if is_option:
            stop_price = round(last_price * 0.5, 2)
            target_price = round(last_price * 2.0, 2)
        else:
            risk_buffer = float(playbook.get("risk_buffer_pct") or 3.5) / 100
            reward_buffer = float(playbook.get("reward_buffer_pct") or 7.0) / 100
            stop_price = last_price * (1 - risk_buffer) if direction == "long" else last_price * (1 + risk_buffer)
            target_price = last_price * (1 + reward_buffer) if direction == "long" else last_price * (1 - reward_buffer)
        note_playbook = dict(playbook)
        if learning_mode:
            contract_multiplier = float(playbook.get("contract_multiplier") or (100 if is_option else 1))
            risk_per_unit = last_price * (float(playbook.get("risk_buffer_pct") or 0) / 100) * contract_multiplier
            note_playbook["suggested_quantity"] = round(quantity, 6)
            note_playbook["suggested_notional_value"] = round(quantity * last_price * contract_multiplier, 2)
            note_playbook["suggested_max_loss_value"] = round(quantity * risk_per_unit, 2)
            note_playbook["learning_mode"] = True
        created = self.portfolio_manager.create_paper_trade(
            {
                "ticker": playbook["ticker"],
                "asset_class": playbook.get("asset_class") or "equity",
                "direction": direction,
                "setup_type": playbook.get("setup_type") or "signal_playbook",
                "thesis": playbook.get("thesis"),
                "entry_price": last_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "quantity": quantity,
                "confidence_score": playbook.get("score"),
                "leverage": leverage,
                "underlying_entry_price": playbook.get("underlying_reference_price") if is_option else last_price,
                "option_type": playbook.get("option_type") if is_option else None,
                "contract_multiplier": playbook.get("contract_multiplier") or (100 if is_option else 1),
                "max_holding_days": playbook.get("max_holding_days") if is_option else None,
                "notes": self._build_trade_note_snapshot(note_playbook, demo_account, is_option),
            }
        )
        self._schedule_trade_outcomes(created)
        return self._enrich_trade(created)

    def evaluate_due_outcomes(self, limit: int = 80) -> Dict[str, Any]:
        due_items = self.portfolio_manager.list_due_paper_trade_outcomes(limit=limit)
        evaluated = 0
        pending_data = 0
        errors: List[str] = []

        for item in due_items:
            outcome_id = str(item.get("id") or "")
            if not outcome_id:
                continue
            checked_at = datetime.utcnow().isoformat()
            try:
                result = self._evaluate_outcome_item(item, checked_at)
                self.portfolio_manager.update_paper_trade_outcome(outcome_id, result)
                if result.get("status") == "evaluated":
                    evaluated += 1
                elif result.get("status") == "pending_data":
                    pending_data += 1
            except Exception as exc:
                errors.append(f"{item.get('ticker') or outcome_id}: {exc}")

        return {
            "status": "ok" if not errors else "partial",
            "due": len(due_items),
            "evaluated": evaluated,
            "pending_data": pending_data,
            "errors": errors[:5],
        }

    def close_trade(
        self,
        trade_id: str,
        closed_price: Optional[float] = None,
        notes: Optional[str] = None,
        exit_reason: Optional[str] = None,
        lessons_learned: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = next((item for item in self.portfolio_manager.list_paper_trades(limit=300) if item.get("id") == trade_id), None)
        if not existing:
            raise ValueError("Trade not found.")
        if existing.get("asset_class") == "option":
            exit_price = float(closed_price or 0) or float(existing.get("entry_price") or 0)
        else:
            exit_price = float(closed_price or 0) or self._get_last_price(existing.get("ticker")) or float(existing.get("entry_price") or 0)
        if exit_price <= 0:
            raise ValueError("No valid close price available.")
        auto_error = self._classify_closed_trade_error(existing, exit_price)
        if not exit_reason and auto_error.get("exit_reason"):
            exit_reason = auto_error["exit_reason"]
        if not lessons_learned and auto_error.get("lesson"):
            lessons_learned = auto_error["lesson"]
        closed = self.portfolio_manager.close_paper_trade(trade_id, exit_price, notes, exit_reason, lessons_learned)
        if not closed:
            raise ValueError("Trade not found.")
        return self._enrich_trade(closed)

    def close_trades_on_management_exits(self, limit: int = 50) -> Dict[str, Any]:
        open_trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(status="open", limit=limit))
        closed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        exit_statuses = {"stop_hit", "target_hit"}

        for trade in open_trades:
            management = trade.get("management_plan") or {}
            status = str(management.get("status") or "")
            if status not in exit_statuses:
                skipped.append(
                    {
                        "id": trade.get("id"),
                        "ticker": trade.get("ticker"),
                        "status": status or "monitor",
                    }
                )
                continue
            current_price = trade.get("current_price")
            if current_price in (None, 0):
                errors.append(
                    {
                        "id": trade.get("id"),
                        "ticker": trade.get("ticker"),
                        "error": "Current price unavailable for managed close.",
                    }
                )
                continue
            try:
                exit_reason = f"managed_{status}"
                lesson = (
                    "Paper target reached: record whether the setup should be repeated."
                    if status == "target_hit"
                    else "Paper stop hit: review trigger quality, timing and invalidation."
                )
                notes = (
                    f"Auto-managed paper exit: {status}. "
                    f"{management.get('summary') or 'Management plan triggered.'}"
                )
                closed.append(
                    self.close_trade(
                        str(trade.get("id")),
                        closed_price=float(current_price),
                        notes=notes,
                        exit_reason=exit_reason,
                        lessons_learned=lesson,
                    )
                )
            except Exception as exc:
                errors.append(
                    {
                        "id": trade.get("id"),
                        "ticker": trade.get("ticker"),
                        "error": str(exc),
                    }
                )

        return {
            "status": "ok" if not errors else "partial",
            "checked": len(open_trades),
            "closed": closed,
            "skipped": skipped[:8],
            "errors": errors[:5],
            "policy": "Paper-only managed exits. No real-money execution.",
        }

    def update_trade_journal(
        self,
        trade_id: str,
        notes: Optional[str] = None,
        exit_reason: Optional[str] = None,
        lessons_learned: Optional[str] = None,
    ) -> Dict[str, Any]:
        updated = self.portfolio_manager.update_paper_trade_journal(
            trade_id,
            notes=notes,
            exit_reason=exit_reason,
            lessons_learned=lessons_learned,
        )
        if not updated:
            raise ValueError("Trade not found.")
        return self._enrich_trade(updated)

    def _build_playbooks(
        self,
        scoreboard: Dict[str, Any],
        rules: Dict[str, Any],
        outcome_learning: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        playbooks: List[Dict[str, Any]] = []

        for item in scoreboard.get("equities", [])[:4]:
            if not item.get("ticker"):
                continue
            direction = "long" if item.get("action") == "buy" else "short"
            score = float(item.get("total_score") or 0)
            playbooks.append(
                {
                    "id": f"equity-{item.get('ticker')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "insider_follow",
                    "title": "Insider follow-through",
                    "headline": item.get("headline"),
                    "score": score,
                    "risk_buffer_pct": 3.5 if direction == "long" else 4.0,
                    "reward_buffer_pct": 7.5,
                    "thesis": (
                        f"{item.get('source_label')} with strong {direction} bias. "
                        f"Use only if price holds after filing delay of {item.get('delay_days') if item.get('delay_days') is not None else 'offen'} days."
                    ),
                    "tags": ["long" if direction == "long" else "short", "official filing", "equity"],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in scoreboard.get("politics", [])[:3]:
            if not item.get("ticker"):
                continue
            direction = "long" if item.get("action") == "buy" else "short"
            playbooks.append(
                {
                    "id": f"politics-{item.get('ticker') or item.get('label')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "political_copy_delay",
                    "title": "Political delay setup",
                    "headline": item.get("headline"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 4.5,
                    "reward_buffer_pct": 8.5,
                    "thesis": (
                        f"Official PTR disclosure with {item.get('detail')}. "
                        "Only valid when the tape confirms after the delayed filing."
                    ),
                    "tags": ["delayed signal", "politics", direction],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in scoreboard.get("etfs", [])[:2]:
            if not item.get("ticker"):
                continue
            playbooks.append(
                {
                    "id": f"etf-{item.get('ticker')}-long",
                    "ticker": item.get("ticker"),
                    "asset_class": "etf",
                    "direction": "long",
                    "setup_type": "etf_momentum",
                    "title": "ETF momentum continuation",
                    "headline": item.get("headline"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 2.8,
                    "reward_buffer_pct": 6.0,
                    "thesis": "Liquid ETF with decent quality and momentum profile. Favor clean continuation over narrative chasing.",
                    "tags": ["etf", "momentum", "long"],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        for item in scoreboard.get("crypto", [])[:2]:
            if not item.get("ticker"):
                continue
            playbooks.append(
                {
                    "id": f"crypto-{item.get('ticker')}-long",
                    "ticker": item.get("ticker"),
                    "asset_class": "crypto",
                    "direction": "long",
                    "setup_type": "crypto_flow",
                    "title": "Crypto flow momentum",
                    "headline": item.get("headline"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 5.5,
                    "reward_buffer_pct": 11.0,
                    "thesis": "Flow-driven crypto setup. Keep leverage conservative and size by volatility, not conviction alone.",
                    "tags": ["crypto", "momentum", "long"],
                    "reference_price": self._get_last_price(item.get("ticker")),
                }
            )

        playbooks.extend(self._build_option_learning_playbooks(playbooks))
        self._apply_outcome_learning(playbooks, outcome_learning or {})

        for item in playbooks:
            item["strategy"] = StrategyLibrary.find_for_playbook(item)
            rule_state = self._get_do_not_trade_state(item, rules)
            item["do_not_trade_reasons"] = rule_state["blocked"]
            item["leverage_warnings"] = rule_state["leverage"]
            item["tradeable"] = len(rule_state["blocked"]) == 0
            item["decision_framework"] = self._build_decision_framework(item)

        return sorted(playbooks, key=lambda item: float(item.get("score") or 0), reverse=True)[:10]

    def _build_trade_note_snapshot(self, playbook: Dict[str, Any], demo_account: Dict[str, Any], is_option: bool) -> str:
        framework = playbook.get("decision_framework") or {}
        checklist = framework.get("review_questions") or []
        lines = [
            "Decision snapshot at paper entry:",
            f"Headline: {playbook.get('headline') or 'n/a'}",
            f"Setup: {playbook.get('setup_type') or 'signal_playbook'} / {playbook.get('asset_class') or 'equity'} / {playbook.get('direction') or 'long'}",
            f"Score: {playbook.get('score')}; evidence: {framework.get('evidence_level') or 'watch'}",
            f"Demo sizing: suggested qty {playbook.get('suggested_quantity')}; max loss {playbook.get('suggested_max_loss_value')} {demo_account.get('currency')}.",
            f"Trigger: {framework.get('entry_trigger') or 'Manual trigger review required.'}",
            f"Invalidation: {framework.get('invalidation') or 'Manual invalidation review required.'}",
            f"Risk plan: {framework.get('risk_plan') or 'Paper risk only.'}",
        ]
        if playbook.get("learning_mode"):
            lines.append("Learning mode: reduced-size demo exploration, not a strict top setup and not real-money ready.")
        if is_option:
            lines.append("Options gate: paper-only premium model; manually verify strike, expiry, spread, IV and max premium risk.")
        for question in checklist[:3]:
            lines.append(f"Review question: {question}")
        lines.append(framework.get("real_money_policy") or "Decision support only; no automatic real-money execution.")
        return "\n".join(str(line) for line in lines if line)

    def _build_decision_framework(self, playbook: Dict[str, Any]) -> Dict[str, Any]:
        ticker = str(playbook.get("ticker") or "asset").upper()
        asset_class = str(playbook.get("asset_class") or "equity")
        direction = str(playbook.get("direction") or "long").lower()
        setup_type = str(playbook.get("setup_type") or "signal_playbook")
        score = float(playbook.get("score") or 0)
        risk_pct = float(playbook.get("risk_buffer_pct") or 0)
        reward_pct = float(playbook.get("reward_buffer_pct") or 0)
        blocked = list(playbook.get("do_not_trade_reasons") or [])
        warnings = list(playbook.get("leverage_warnings") or [])
        is_option = asset_class == "option"
        strategy = playbook.get("strategy") or StrategyLibrary.find_for_playbook(playbook)

        direction_label = "upside" if direction in {"long", "call"} else "downside"
        entry_trigger = str(strategy.get("trigger_template") or "").format(ticker=ticker) or (
            f"{ticker} confirms {direction_label} follow-through after the signal with clean price action and volume."
        )
        invalidation = str(strategy.get("invalidation_template") or "").format(ticker=ticker) or (
            f"Thesis fails if {ticker} breaks the planned stop zone, news quality weakens, or the move is not confirmed by market breadth."
        )
        risk_plan = (
            f"Paper size only. Planned risk buffer {risk_pct}% and target buffer {reward_pct}%; no size increase after entry."
        )
        if is_option:
            entry_trigger = (
                f"Only paper-test the {direction.upper()} after the underlying confirms direction, liquidity and timing."
            )
            invalidation = (
                "Invalid if underlying momentum fades, spread is wide, IV/expiry are unattractive, or max premium risk is not documented."
            )
            risk_plan = "Defined-risk paper option only; max loss is premium, no real-money execution from this model."

        evidence_level = "watch"
        if blocked:
            evidence_level = "blocked"
        elif score >= 90:
            evidence_level = "high_quality_paper"
        elif score >= 78:
            evidence_level = "paper_candidate"

        review_questions = [
            "Is the signal still fresh and confirmed by price, volume and market context?",
            "What exact event would prove the thesis wrong?",
            "Is the position risk acceptable before opening the trade?",
        ]
        if setup_type == "political_copy_delay":
            review_questions.append("Is the political filing too delayed to still have an edge?")
        if is_option:
            review_questions.append("Were strike, expiry, spread, IV and premium risk checked manually?")

        return {
            "evidence_level": evidence_level,
            "entry_trigger": entry_trigger,
            "invalidation": invalidation,
            "risk_plan": risk_plan,
            "data_checks": [
                "Price reference available",
                "Stop and target defined",
                "No blocked learning setup" if not blocked else "Blocked reason must be resolved first",
                "Manual review required before real money",
            ],
            "review_questions": review_questions,
            "blocked_reasons": blocked,
            "warnings": warnings,
            "strategy_id": strategy.get("id"),
            "strategy_label": strategy.get("label"),
            "strategy_horizon": strategy.get("horizon"),
            "quality_gates": strategy.get("quality_gates") or [],
            "risk_notes": strategy.get("risk_notes") or [],
            "real_world_gate": strategy.get("real_world_gate"),
            "real_money_policy": "Decision support only; real-money execution requires manual review and documented risk.",
        }

    def _schedule_trade_outcomes(self, trade: Dict[str, Any]) -> int:
        trade_id = str(trade.get("id") or "")
        if not trade_id:
            return 0
        opened_at = self._parse_datetime(trade.get("opened_at")) or datetime.utcnow()
        horizons = list(DEFAULT_PAPER_OUTCOME_HORIZONS_HOURS)
        max_holding_days = int(trade.get("max_holding_days") or 0)
        if trade.get("asset_class") == "option" and max_holding_days > 0:
            horizons.append(max_holding_days * 24)
        unique_horizons = sorted({int(hour) for hour in horizons if int(hour) > 0})
        outcomes = [
            {
                "id": f"{trade_id}_{hours}h",
                "trade_id": trade_id,
                "horizon_hours": hours,
                "due_at": (opened_at + timedelta(hours=hours)).isoformat(),
                "status": "pending",
                "result": None,
                "checked_at": None,
                "check_price": None,
                "performance_pct": None,
                "notes": None,
                "error_tag": None,
            }
            for hours in unique_horizons
        ]
        return self.portfolio_manager.upsert_paper_trade_outcomes(trade_id, outcomes)

    def _evaluate_outcome_item(self, item: Dict[str, Any], checked_at: str) -> Dict[str, Any]:
        asset_class = str(item.get("asset_class") or "equity")
        direction = str(item.get("direction") or "long").lower()
        entry = float(item.get("entry_price") or 0)
        ticker = str(item.get("ticker") or "").upper()
        if entry <= 0 or not ticker:
            return {
                "status": "pending_data",
                "checked_at": checked_at,
                "notes": "Missing entry price or ticker; outcome not scored.",
            }

        if asset_class == "option":
            underlying_entry = float(item.get("underlying_entry_price") or 0)
            underlying_price = self._get_last_price(ticker)
            if underlying_entry <= 0 or underlying_price is None:
                return {
                    "status": "pending_data",
                    "checked_at": checked_at,
                    "notes": "Underlying price unavailable; option outcome not scored.",
                }
            raw_move = ((underlying_price / underlying_entry) - 1) * 100
            favorable = raw_move if direction == "call" else -raw_move
            result, error_tag, notes = self._score_paper_outcome(favorable, item)
            return {
                "status": "evaluated",
                "result": result,
                "checked_at": checked_at,
                "check_price": underlying_price,
                "performance_pct": round(favorable, 2),
                "notes": f"Underlying move model for paper {direction}: {notes}",
                "error_tag": error_tag,
            }

        current_price = self._get_last_price(ticker)
        if current_price is None:
            return {
                "status": "pending_data",
                "checked_at": checked_at,
                "notes": "Price data unavailable; outcome not scored.",
            }
        raw_move = ((current_price / entry) - 1) * 100
        favorable = -raw_move if direction == "short" else raw_move
        result, error_tag, notes = self._score_paper_outcome(favorable, item)
        return {
            "status": "evaluated",
            "result": result,
            "checked_at": checked_at,
            "check_price": current_price,
            "performance_pct": round(favorable, 2),
            "notes": notes,
            "error_tag": error_tag,
        }

    def _score_paper_outcome(self, favorable_pct: float, item: Dict[str, Any]) -> tuple[str, Optional[str], str]:
        horizon = int(item.get("horizon_hours") or 0)
        is_option = item.get("asset_class") == "option"
        hit_threshold = 1.2 if is_option else 0.8
        miss_threshold = -1.2 if is_option else -0.8
        if horizon <= 1:
            hit_threshold *= 0.5
            miss_threshold *= 0.5
        if favorable_pct >= hit_threshold:
            return "hit", None, f"Favorable move {favorable_pct:+.2f}% met the {horizon}h threshold."
        if favorable_pct <= miss_threshold:
            error_tag = self._classify_error_tag(favorable_pct, item)
            return "miss", error_tag, f"Adverse move {favorable_pct:+.2f}% missed the {horizon}h threshold."
        return "neutral", None, f"Move {favorable_pct:+.2f}% was not decisive at {horizon}h."

    def _classify_error_tag(self, favorable_pct: float, item: Dict[str, Any]) -> str:
        setup_type = str(item.get("setup_type") or "")
        asset_class = str(item.get("asset_class") or "")
        horizon = int(item.get("horizon_hours") or 0)
        if asset_class == "option" and horizon <= 24:
            return "option_timing_too_early_or_premium_decay"
        if "political" in setup_type:
            return "delayed_signal_no_follow_through"
        if "news" in setup_type:
            return "headline_no_follow_through"
        if favorable_pct < -3:
            return "thesis_invalidated_fast"
        return "weak_follow_through"

    def _classify_closed_trade_error(self, trade: Dict[str, Any], exit_price: float) -> Dict[str, str]:
        entry = float(trade.get("entry_price") or 0)
        if entry <= 0 or exit_price <= 0:
            return {}
        direction_multiplier = -1 if trade.get("direction") == "short" else 1
        pnl_pct = self._calc_return_pct(entry, exit_price, direction_multiplier, float(trade.get("leverage") or 1))
        if pnl_pct is None or pnl_pct >= 0:
            return {}
        error_tag = self._classify_error_tag(float(pnl_pct), trade)
        return {
            "exit_reason": error_tag,
            "lesson": f"Auto-classified loss: {error_tag}. Reduce score or wait for stronger confirmation next time.",
        }

    def _build_outcome_dashboard(self) -> Dict[str, Any]:
        outcomes = self.portfolio_manager.list_paper_trade_outcomes(limit=500)
        evaluated = [item for item in outcomes if item.get("status") == "evaluated"]
        pending = [item for item in outcomes if item.get("status") in {"pending", "pending_data"}]
        hits = [item for item in evaluated if item.get("result") == "hit"]
        misses = [item for item in evaluated if item.get("result") == "miss"]
        by_error: Dict[str, int] = {}
        for item in misses:
            key = str(item.get("error_tag") or "unclassified")
            by_error[key] = by_error.get(key, 0) + 1
        return {
            "summary": {
                "total": len(outcomes),
                "evaluated": len(evaluated),
                "pending": len(pending),
                "hit_rate": round((len(hits) / max(1, len(hits) + len(misses))) * 100, 1),
                "misses": len(misses),
            },
            "top_errors": [
                {"error_tag": key, "count": count}
                for key, count in sorted(by_error.items(), key=lambda item: item[1], reverse=True)[:6]
            ],
            "recent": outcomes[:12],
        }

    def _build_outcome_learning_adjustments(self) -> Dict[str, Any]:
        outcomes = self.portfolio_manager.list_paper_trade_outcomes(limit=800)
        evaluated = [item for item in outcomes if item.get("status") == "evaluated"]
        by_setup: Dict[str, List[Dict[str, Any]]] = {}
        by_asset: Dict[str, List[Dict[str, Any]]] = {}
        by_error: Dict[str, int] = {}
        for item in evaluated:
            by_setup.setdefault(str(item.get("setup_type") or "unknown"), []).append(item)
            by_asset.setdefault(str(item.get("asset_class") or "unknown"), []).append(item)
            if item.get("result") == "miss":
                key = str(item.get("error_tag") or "unclassified")
                by_error[key] = by_error.get(key, 0) + 1

        setup_adjustments: Dict[str, Dict[str, Any]] = {}
        for setup_type, rows in by_setup.items():
            misses = [item for item in rows if item.get("result") == "miss"]
            hits = [item for item in rows if item.get("result") == "hit"]
            decisive = len(hits) + len(misses)
            if decisive < 4:
                continue
            hit_rate = round((len(hits) / max(1, decisive)) * 100, 1)
            score_delta = 0
            block = False
            reason = ""
            if decisive >= 8 and hit_rate < 25:
                score_delta = -14
                block = True
                reason = f"Setup {setup_type} is blocked by paper outcomes: {hit_rate}% hit rate over {decisive} decisive checks."
            elif hit_rate < 35:
                score_delta = -8
                reason = f"Setup {setup_type} is downgraded by paper outcomes: {hit_rate}% hit rate over {decisive} decisive checks."
            elif decisive >= 8 and hit_rate >= 60:
                score_delta = 4
                reason = f"Setup {setup_type} has positive paper evidence: {hit_rate}% hit rate over {decisive} decisive checks."
            if score_delta or block:
                setup_adjustments[setup_type] = {
                    "setup_type": setup_type,
                    "evaluated": len(rows),
                    "decisive": decisive,
                    "hit_rate": hit_rate,
                    "score_delta": score_delta,
                    "block": block,
                    "reason": reason,
                }

        option_rows = by_asset.get("option", [])
        option_hits = [item for item in option_rows if item.get("result") == "hit"]
        option_misses = [item for item in option_rows if item.get("result") == "miss"]
        option_decisive = len(option_hits) + len(option_misses)
        option_hit_rate = round((len(option_hits) / max(1, option_decisive)) * 100, 1) if option_decisive else 0
        option_ready = option_decisive >= 20 and option_hit_rate >= 55
        checks_remaining = max(0, 20 - option_decisive)
        top_error_tags = [
            {"error_tag": key, "count": count}
            for key, count in sorted(by_error.items(), key=lambda item: item[1], reverse=True)[:6]
        ]
        blocked_setups = [item for item in setup_adjustments.values() if item.get("block")]
        downgraded_setups = [
            item
            for item in setup_adjustments.values()
            if not item.get("block") and float(item.get("score_delta") or 0) < 0
        ]
        upgraded_setups = [
            item
            for item in setup_adjustments.values()
            if float(item.get("score_delta") or 0) > 0
        ]

        readiness_status = "paper_only"
        readiness_label = "Paper only"
        if option_ready:
            readiness_status = "manual_review_ready"
            readiness_label = "Manual review ready"
        elif option_decisive >= 10 and option_hit_rate >= 45:
            readiness_status = "building_evidence"
            readiness_label = "Building evidence"

        review_focus: List[str] = []
        if blocked_setups:
            review_focus.append(f"Stop using blocked setup types: {', '.join(item['setup_type'] for item in blocked_setups[:3])}.")
        if downgraded_setups:
            review_focus.append(f"Reduce size or require stronger confirmation for: {', '.join(item['setup_type'] for item in downgraded_setups[:3])}.")
        if upgraded_setups:
            review_focus.append(f"Keep testing stronger setups: {', '.join(item['setup_type'] for item in upgraded_setups[:3])}.")
        if top_error_tags:
            review_focus.append(f"Main error to fix next: {top_error_tags[0]['error_tag']} ({top_error_tags[0]['count']} misses).")
        if not review_focus:
            review_focus.append("Collect more closed and auto-evaluated paper trades before changing real-money rules.")

        manual_review_checklist = [
            "Thesis is written before entry.",
            "Trigger, stop, target and invalidation are clear.",
            "Position risk is within the account guardrails.",
            "No blocked setup type is involved.",
            "For options: expiry, strike, spread and max premium risk were reviewed manually.",
        ]

        return {
            "setup_adjustments": setup_adjustments,
            "option_readiness": {
                "decisive": option_decisive,
                "hit_rate": option_hit_rate,
                "real_money_ready": option_ready,
                "status": readiness_status,
                "label": readiness_label,
                "checks_remaining": checks_remaining,
                "required_decisive": 20,
                "required_hit_rate": 55,
                "reason": (
                    "Options remain paper-only until 20 decisive checks and >=55% hit rate."
                    if not option_ready
                    else "Options have enough paper evidence for manual review, not automatic execution."
                ),
            },
            "top_error_tags": top_error_tags,
            "learning_summary": {
                "readiness_status": readiness_status,
                "readiness_label": readiness_label,
                "blocked_setups": len(blocked_setups),
                "downgraded_setups": len(downgraded_setups),
                "upgraded_setups": len(upgraded_setups),
                "review_focus": review_focus,
                "manual_review_checklist": manual_review_checklist,
                "real_money_policy": "Decision support only: no automatic real-money execution.",
            },
        }

    def _apply_outcome_learning(self, playbooks: List[Dict[str, Any]], outcome_learning: Dict[str, Any]) -> None:
        setup_adjustments = outcome_learning.get("setup_adjustments") or {}
        option_readiness = outcome_learning.get("option_readiness") or {}
        for item in playbooks:
            adjustment = setup_adjustments.get(str(item.get("setup_type") or ""))
            notes: List[str] = []
            score_delta = 0.0
            blocked = False
            if adjustment:
                score_delta += float(adjustment.get("score_delta") or 0)
                blocked = bool(adjustment.get("block"))
                if adjustment.get("reason"):
                    notes.append(str(adjustment["reason"]))
            if item.get("asset_class") == "option":
                if not option_readiness.get("real_money_ready"):
                    score_delta -= 3
                    notes.append(str(option_readiness.get("reason") or "Options remain paper-only."))
            if score_delta:
                item["raw_score"] = item.get("score")
                item["score"] = max(0, round(float(item.get("score") or 0) + score_delta, 2))
            if notes or blocked or score_delta:
                item["learning_adjustment"] = {
                    "score_delta": round(score_delta, 2),
                    "blocked": blocked,
                    "notes": notes,
                }
            if blocked:
                item["learning_blocked"] = True

    def _build_auto_selection(
        self,
        playbooks: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        demo_account: Dict[str, Any],
        max_candidates: int = 5,
    ) -> Dict[str, Any]:
        open_keys = {
            (
                str(trade.get("ticker") or "").upper(),
                str(trade.get("setup_type") or ""),
                str(trade.get("direction") or ""),
                str(trade.get("asset_class") or ""),
            )
            for trade in trades
            if trade.get("status") == "open"
        }
        min_score = float(os.getenv("PAPER_TRADING_AUTO_MIN_SCORE", "88"))
        exploration_min_score = float(os.getenv("PAPER_TRADING_EXPLORATION_MIN_SCORE", "60"))
        exploration_risk_multiplier = min(
            0.35,
            max(0.03, float(os.getenv("PAPER_TRADING_EXPLORATION_RISK_MULTIPLIER", "0.10"))),
        )
        selected: List[Dict[str, Any]] = []
        exploration: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for playbook in playbooks:
            reasons: List[str] = []
            exploration_reasons: List[str] = []
            score = float(playbook.get("score") or 0)
            key = (
                str(playbook.get("ticker") or "").upper(),
                str(playbook.get("setup_type") or ""),
                str(playbook.get("direction") or ""),
                str(playbook.get("asset_class") or ""),
            )
            framework = playbook.get("decision_framework") or {}
            hard_rule_reasons = [
                str(item)
                for item in playbook.get("do_not_trade_reasons", [])
                if not str(item).lower().startswith("score below minimum trade score")
            ]
            if score < min_score:
                reasons.append(f"score below auto minimum {min_score:.0f}")
            if score < exploration_min_score:
                exploration_reasons.append(f"score below learning minimum {exploration_min_score:.0f}")
            if playbook.get("tradeable") is False or playbook.get("demo_tradeable") is False:
                reasons.append("trade or demo risk gate blocked")
            if hard_rule_reasons:
                exploration_reasons.extend(hard_rule_reasons[:3])
            if playbook.get("demo_block_reasons"):
                reasons.extend(str(item) for item in playbook.get("demo_block_reasons")[:3])
                hard_demo_reasons = [
                    str(item)
                    for item in playbook.get("demo_block_reasons", [])
                    if str(item) != "Playbook is blocked by signal rules." or hard_rule_reasons
                ]
                exploration_reasons.extend(hard_demo_reasons[:3])
            if key in open_keys:
                reasons.append("same ticker/setup/direction already open")
                exploration_reasons.append("same ticker/setup/direction already open")
            if not playbook.get("ticker") or not playbook.get("reference_price"):
                reasons.append("missing ticker or reference price")
                exploration_reasons.append("missing ticker or reference price")
            if not framework.get("entry_trigger") or not framework.get("invalidation") or not playbook.get("thesis"):
                reasons.append("missing thesis, trigger or invalidation")
                exploration_reasons.append("missing thesis, trigger or invalidation")
            if playbook.get("asset_class") == "option":
                readiness = (demo_account.get("learning_feedback") or {}).get("option_win_rate")
                if readiness is None:
                    reasons.append("option remains paper-only and needs manual chain review")
                    exploration_reasons.append("option chain must be reviewed manually before exploration")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected):
                reasons.append("demo account open-trade slots exhausted")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected) + len(exploration):
                exploration_reasons.append("demo account open-trade slots exhausted")

            row = {
                "id": playbook.get("id"),
                "ticker": playbook.get("ticker"),
                "asset_class": playbook.get("asset_class"),
                "direction": playbook.get("direction"),
                "setup_type": playbook.get("setup_type"),
                "strategy_id": (playbook.get("strategy") or {}).get("id"),
                "strategy_label": (playbook.get("strategy") or {}).get("label"),
                "score": score,
                "title": playbook.get("title"),
                "headline": playbook.get("headline"),
                "suggested_quantity": playbook.get("suggested_quantity"),
                "suggested_notional_value": playbook.get("suggested_notional_value"),
                "suggested_max_loss_value": playbook.get("suggested_max_loss_value"),
                "learning_mode": False,
                "trigger": framework.get("entry_trigger"),
                "invalidation": framework.get("invalidation"),
                "reasons": reasons,
            }
            if reasons:
                rejected.append(row)
            else:
                selected.append(row)
            if not exploration_reasons and reasons and playbook.get("asset_class") != "option":
                learning_row = dict(row)
                learning_row["learning_mode"] = True
                learning_row["suggested_quantity"] = round(float(playbook.get("suggested_quantity") or 0) * exploration_risk_multiplier, 6)
                learning_row["suggested_notional_value"] = round(float(playbook.get("suggested_notional_value") or 0) * exploration_risk_multiplier, 2)
                learning_row["suggested_max_loss_value"] = round(float(playbook.get("suggested_max_loss_value") or 0) * exploration_risk_multiplier, 2)
                learning_row["reasons"] = [f"learning mode: reduced risk x{exploration_risk_multiplier:g}"]
                exploration.append(learning_row)
            if len(selected) >= max_candidates:
                break

        return {
            "mode": "paper_autopilot_preview",
            "min_score": min_score,
            "exploration_min_score": exploration_min_score,
            "exploration_risk_multiplier": exploration_risk_multiplier,
            "selected": selected,
            "exploration": exploration[:max_candidates],
            "rejected": rejected[:8],
            "policy": "Paper-only auto-selection. Strict mode is quality first; learn mode uses smaller demo risk to collect evidence.",
        }

    def _build_option_learning_playbooks(self, base_playbooks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        option_playbooks: List[Dict[str, Any]] = []
        for item in base_playbooks:
            score = float(item.get("score") or 0)
            price = float(item.get("reference_price") or 0)
            if item.get("asset_class") not in {"equity", "etf"} or score < 88 or price <= 5:
                continue
            direction = item.get("direction")
            option_type = "call" if direction == "long" else "put" if direction == "short" else None
            if not option_type:
                continue
            estimated_premium = round(max(0.35, price * 0.025), 2)
            option_playbooks.append(
                {
                    "id": f"option-{item.get('ticker')}-{option_type}",
                    "ticker": item.get("ticker"),
                    "asset_class": "option",
                    "direction": option_type,
                    "setup_type": f"option_{option_type}_learning",
                    "title": f"Paper {option_type.upper()} learning setup",
                    "headline": item.get("headline"),
                    "score": max(0, score - 3),
                    "risk_buffer_pct": 100.0,
                    "reward_buffer_pct": 100.0,
                    "thesis": (
                        f"Options-Demo auf {item.get('ticker')}: nur testen, wenn Underlying-These, Timing und Volumen bestaetigt sind. "
                        "Maximaler Verlust ist die Demo-Praemie; kein Real-Money-Einsatz ohne manuelle Optionskettenpruefung."
                    ),
                    "tags": ["option", option_type, "paper only", "defined risk"],
                    "reference_price": estimated_premium,
                    "underlying_reference_price": price,
                    "option_type": option_type,
                    "contract_multiplier": 100,
                    "max_holding_days": 10,
                    "quality_gate": [
                        "Underlying signal score >= 88",
                        "Price reference exists",
                        "Use only as demo option idea until IV, strike and expiry are verified",
                    ],
                }
            )
        return option_playbooks[:4]

    def _build_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        closed = [trade for trade in trades if trade.get("status") == "closed" and trade.get("realized_pnl_pct") is not None]
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        winners = [trade for trade in closed if float(trade.get("realized_pnl_pct") or 0) > 0]
        losers = [trade for trade in closed if float(trade.get("realized_pnl_pct") or 0) <= 0]
        total_realized = round(sum(float(trade.get("realized_pnl_pct") or 0) for trade in closed), 2)
        avg_open = round(
            sum(float(trade.get("unrealized_pnl_pct") or 0) for trade in open_trades) / len(open_trades),
            2,
        ) if open_trades else 0
        return {
            "total_trades": len(trades),
            "open_trades": len(open_trades),
            "closed_trades": len(closed),
            "win_rate": round((len(winners) / len(closed)) * 100, 1) if closed else 0,
            "avg_open_pnl_pct": avg_open,
            "realized_pnl_pct": total_realized,
            "best_trade_pct": round(max((float(trade.get("realized_pnl_pct") or 0) for trade in closed), default=0), 2),
            "worst_trade_pct": round(min((float(trade.get("realized_pnl_pct") or 0) for trade in closed), default=0), 2),
            "long_short_split": {
                "long": sum(1 for trade in trades if trade.get("direction") == "long"),
                "short": sum(1 for trade in trades if trade.get("direction") == "short"),
            },
            "loss_count": len(losers),
        }

    def _demo_account_config(self) -> Dict[str, Any]:
        def env_float(name: str, default: float, minimum: float = 0.0) -> float:
            try:
                value = float(os.getenv(name, str(default)).strip())
            except Exception:
                value = default
            return max(minimum, value)

        def env_int(name: str, default: int, minimum: int = 0) -> int:
            try:
                value = int(os.getenv(name, str(default)).strip())
            except Exception:
                value = default
            return max(minimum, value)

        return {
            "starting_capital": env_float("PAPER_TRADING_STARTING_CAPITAL", 500_000.0, minimum=1_000.0),
            "currency": os.getenv("PAPER_TRADING_CURRENCY", "EUR").strip().upper() or "EUR",
            "risk_per_trade_pct": env_float("PAPER_TRADING_RISK_PER_TRADE_PCT", 0.35, minimum=0.01),
            "max_open_risk_pct": env_float("PAPER_TRADING_MAX_OPEN_RISK_PCT", 3.0, minimum=0.1),
            "max_position_pct": env_float("PAPER_TRADING_MAX_POSITION_PCT", 10.0, minimum=0.1),
            "max_option_premium_pct": env_float("PAPER_TRADING_MAX_OPTION_PREMIUM_PCT", 0.75, minimum=0.01),
            "risk_per_option_trade_pct": env_float("PAPER_TRADING_RISK_PER_OPTION_TRADE_PCT", 0.25, minimum=0.01),
            "max_open_trades": env_int("PAPER_TRADING_MAX_OPEN_TRADES", 12, minimum=1),
            "mode": "paper_learning_only",
        }

    def _build_demo_account(self, trades: List[Dict[str, Any]], playbooks: List[Dict[str, Any]]) -> Dict[str, Any]:
        config = self._demo_account_config()
        starting_capital = float(config["starting_capital"])
        realized_value = sum(float(trade.get("realized_pnl_value") or 0) for trade in trades if trade.get("status") == "closed")
        unrealized_value = sum(float(trade.get("unrealized_pnl_value") or 0) for trade in trades if trade.get("status") == "open")
        equity = round(starting_capital + realized_value + unrealized_value, 2)
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        open_risk_value = round(sum(self._trade_open_risk_value(trade) for trade in open_trades), 2)
        open_exposure_value = round(
            sum(float(trade.get("entry_price") or 0) * float(trade.get("quantity") or 0) * float(trade.get("leverage") or 1) for trade in open_trades),
            2,
        )
        risk_budget = round(equity * (float(config["risk_per_trade_pct"]) / 100), 2)
        max_open_risk_value = round(equity * (float(config["max_open_risk_pct"]) / 100), 2)
        max_position_value = round(equity * (float(config["max_position_pct"]) / 100), 2)
        max_option_premium_value = round(equity * (float(config["max_option_premium_pct"]) / 100), 2)
        option_risk_budget = round(equity * (float(config["risk_per_option_trade_pct"]) / 100), 2)
        remaining_risk = round(max(0.0, max_open_risk_value - open_risk_value), 2)
        return {
            **config,
            "equity": equity,
            "realized_pnl_value": round(realized_value, 2),
            "unrealized_pnl_value": round(unrealized_value, 2),
            "open_risk_value": open_risk_value,
            "open_risk_pct": round((open_risk_value / equity) * 100, 2) if equity > 0 else 0,
            "open_exposure_value": open_exposure_value,
            "open_exposure_pct": round((open_exposure_value / equity) * 100, 2) if equity > 0 else 0,
            "risk_budget_per_trade_value": risk_budget,
            "risk_budget_per_option_trade_value": option_risk_budget,
            "max_open_risk_value": max_open_risk_value,
            "remaining_risk_value": remaining_risk,
            "max_position_value": max_position_value,
            "max_option_premium_value": max_option_premium_value,
            "open_trade_slots": max(0, int(config["max_open_trades"]) - len(open_trades)),
            "candidate_count": len(playbooks),
            "guardrails": [
                "Demo-only learning account; no automatic real-money execution.",
                "Every idea needs thesis, trigger, stop, target and post-trade journal.",
                "Calls and puts are paper-only until option chain, IV, strike, expiry and spread are checked.",
                "Real-money use requires manual review, suitability check and current market validation.",
            ],
            "learning_feedback": self._build_learning_feedback(trades),
        }

    def _attach_demo_sizing(self, playbooks: List[Dict[str, Any]], demo_account: Dict[str, Any]) -> List[Dict[str, Any]]:
        sized: List[Dict[str, Any]] = []
        for item in playbooks:
            row = dict(item)
            sizing = self._suggest_demo_sizing(row, demo_account)
            row.update(sizing)
            sized.append(row)
        return sized

    def _suggest_demo_sizing(self, playbook: Dict[str, Any], demo_account: Dict[str, Any]) -> Dict[str, Any]:
        price = float(playbook.get("reference_price") or 0)
        risk_buffer_pct = float(playbook.get("risk_buffer_pct") or 3.5)
        contract_multiplier = float(playbook.get("contract_multiplier") or 1)
        is_option = playbook.get("asset_class") == "option"
        risk_per_unit = price * (risk_buffer_pct / 100) * contract_multiplier
        risk_budget = min(
            float(
                demo_account.get("risk_budget_per_option_trade_value")
                if is_option
                else demo_account.get("risk_budget_per_trade_value")
                or 0
            ),
            float(demo_account.get("remaining_risk_value") or 0),
        )
        max_position_value = float(
            demo_account.get("max_option_premium_value")
            if is_option
            else demo_account.get("max_position_value")
            or 0
        )
        block_reasons: List[str] = []

        if price <= 0:
            block_reasons.append("No reference price for demo sizing.")
        if risk_budget <= 0:
            block_reasons.append("Open risk budget is exhausted.")
        if int(demo_account.get("open_trade_slots") or 0) <= 0:
            block_reasons.append("Maximum demo open trades reached.")
        if playbook.get("tradeable") is False:
            block_reasons.append("Playbook is blocked by signal rules.")

        quantity_by_risk = risk_budget / risk_per_unit if risk_per_unit > 0 else 0
        quantity_by_position = max_position_value / (price * contract_multiplier) if price > 0 else 0
        quantity = max(0.0, min(quantity_by_risk, quantity_by_position))
        if is_option:
            quantity = float(int(quantity))
        if quantity < 0.0001:
            block_reasons.append("Suggested quantity is too small for the configured risk budget.")

        notional = quantity * price * contract_multiplier
        max_loss = quantity * risk_per_unit
        return {
            "suggested_quantity": round(quantity, 6),
            "suggested_notional_value": round(notional, 2),
            "suggested_max_loss_value": round(max_loss, 2),
            "suggested_account_pct": round((notional / float(demo_account.get("equity") or 1)) * 100, 2),
            "suggested_risk_pct": round((max_loss / float(demo_account.get("equity") or 1)) * 100, 2),
            "contract_multiplier": contract_multiplier,
            "demo_block_reasons": block_reasons,
            "demo_tradeable": not block_reasons,
        }

    def _trade_open_risk_value(self, trade: Dict[str, Any]) -> float:
        if trade.get("status") != "open":
            return 0.0
        entry = float(trade.get("entry_price") or 0)
        stop = trade.get("stop_price")
        quantity = float(trade.get("quantity") or 0)
        leverage = float(trade.get("leverage") or 1)
        contract_multiplier = 100 if trade.get("asset_class") == "option" else 1
        if not entry or stop in (None, 0) or quantity <= 0:
            return 0.0
        return abs(entry - float(stop)) * quantity * leverage * contract_multiplier

    def _build_learning_feedback(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        closed = [trade for trade in trades if trade.get("status") == "closed" and trade.get("realized_pnl_pct") is not None]
        option_closed = [trade for trade in closed if trade.get("asset_class") == "option"]
        mistakes: Dict[str, int] = {}
        for trade in closed:
            if float(trade.get("realized_pnl_pct") or 0) >= 0:
                continue
            key = (trade.get("exit_reason") or trade.get("setup_type") or "unclassified").strip() or "unclassified"
            mistakes[key] = mistakes.get(key, 0) + 1
        option_wins = [trade for trade in option_closed if float(trade.get("realized_pnl_pct") or 0) > 0]
        return {
            "closed_trades": len(closed),
            "option_closed_trades": len(option_closed),
            "option_win_rate": round((len(option_wins) / len(option_closed)) * 100, 1) if option_closed else 0,
            "top_mistakes": [
                {"reason": reason, "count": count}
                for reason, count in sorted(mistakes.items(), key=lambda item: item[1], reverse=True)[:5]
            ],
            "next_rule": (
                "No real-money calls or puts until at least 20 paper option trades show repeatable positive expectancy."
                if len(option_closed) < 20
                else "Review option expectancy by setup before increasing demo risk."
            ),
        }

    def _build_setup_performance(self, closed_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for trade in closed_trades:
            setup_type = trade.get("setup_type") or "other"
            bucket = buckets.setdefault(
                setup_type,
                {
                    "setup_type": setup_type,
                    "trades": 0,
                    "wins": 0,
                    "avg_pnl_pct": 0.0,
                    "best_pnl_pct": None,
                    "worst_pnl_pct": None,
                },
            )
            pnl = float(trade.get("realized_pnl_pct") or 0)
            bucket["trades"] += 1
            bucket["wins"] += 1 if pnl > 0 else 0
            bucket["avg_pnl_pct"] += pnl
            bucket["best_pnl_pct"] = pnl if bucket["best_pnl_pct"] is None else max(bucket["best_pnl_pct"], pnl)
            bucket["worst_pnl_pct"] = pnl if bucket["worst_pnl_pct"] is None else min(bucket["worst_pnl_pct"], pnl)

        rows = []
        for bucket in buckets.values():
            trades = max(1, int(bucket["trades"]))
            rows.append(
                {
                    **bucket,
                    "avg_pnl_pct": round(float(bucket["avg_pnl_pct"]) / trades, 2),
                    "win_rate": round((int(bucket["wins"]) / trades) * 100, 1),
                }
            )
        rows.sort(key=lambda item: (item.get("win_rate", 0), item.get("avg_pnl_pct", 0)), reverse=True)
        return rows

    def _build_journal(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        for trade in trades[:20]:
            pnl_pct = trade.get("realized_pnl_pct")
            if pnl_pct is None:
                pnl_pct = trade.get("unrealized_pnl_pct")
            rows.append(
                {
                    "id": trade.get("id"),
                    "ticker": trade.get("ticker"),
                    "direction": trade.get("direction"),
                    "setup_type": trade.get("setup_type"),
                    "status": trade.get("status"),
                    "opened_at": trade.get("opened_at"),
                    "closed_at": trade.get("closed_at"),
                    "thesis": trade.get("thesis"),
                    "notes": trade.get("notes"),
                    "exit_reason": trade.get("exit_reason"),
                    "lessons_learned": trade.get("lessons_learned"),
                    "pnl_pct": pnl_pct,
                    "risk_reward": trade.get("risk_reward"),
                    "confidence_score": trade.get("confidence_score"),
                }
            )
        return rows

    def _enrich_trades(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched = [self._enrich_trade(trade) for trade in trades]
        enriched.sort(
            key=lambda trade: (
                0 if trade.get("status") == "open" else 1,
                trade.get("closed_at") or trade.get("opened_at") or "",
            ),
            reverse=True,
        )
        return enriched

    def _enrich_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(trade)
        entry = float(row.get("entry_price") or 0)
        quantity = float(row.get("quantity") or 0)
        leverage = float(row.get("leverage") or 1)
        is_option = row.get("asset_class") == "option"
        current_price = None if is_option else self._get_last_price(row.get("ticker"))
        row["current_price"] = current_price
        direction_multiplier = -1 if row.get("direction") == "short" else 1
        contract_multiplier = 100 if is_option else 1

        if row.get("status") == "closed":
            exit_price = float(row.get("closed_price") or 0)
            pnl_pct = self._calc_return_pct(entry, exit_price, direction_multiplier, leverage)
            row["realized_pnl_pct"] = pnl_pct
            row["realized_pnl_value"] = round(((exit_price - entry) * quantity * direction_multiplier * leverage * contract_multiplier), 2)
            row["unrealized_pnl_pct"] = None
            row["unrealized_pnl_value"] = None
        else:
            pnl_pct = self._calc_return_pct(entry, current_price, direction_multiplier, leverage) if current_price else None
            row["unrealized_pnl_pct"] = pnl_pct
            row["unrealized_pnl_value"] = (
                round(((current_price - entry) * quantity * direction_multiplier * leverage * contract_multiplier), 2)
                if current_price is not None
                else None
            )
            row["realized_pnl_pct"] = None
            row["realized_pnl_value"] = None

        row["risk_reward"] = self._calc_risk_reward(
            entry,
            row.get("stop_price"),
            row.get("target_price"),
            row.get("direction"),
        )
        if row.get("status") == "open":
            row["management_plan"] = self._build_trade_management_plan(row)
        return row

    def _build_trade_management_plan(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        entry = float(trade.get("entry_price") or 0)
        current = trade.get("current_price")
        stop = trade.get("stop_price")
        target = trade.get("target_price")
        direction = str(trade.get("direction") or "long").lower()
        if not entry or current in (None, 0):
            return {
                "status": "pending_data",
                "action": "wait",
                "summary": "Current price unavailable; keep paper trade under review.",
            }

        current_price = float(current)
        stop_price = float(stop) if stop not in (None, 0) else None
        target_price = float(target) if target not in (None, 0) else None
        favorable_pct = float(trade.get("unrealized_pnl_pct") or 0)
        risk_distance = None
        target_progress = None
        action = "hold"
        status = "monitor"
        summary = "Hold paper position while trigger remains valid."

        if stop_price is not None:
            if direction == "short":
                stop_hit = current_price >= stop_price
                risk_distance = ((stop_price - current_price) / entry) * 100
            else:
                stop_hit = current_price <= stop_price
                risk_distance = ((current_price - stop_price) / entry) * 100
            if stop_hit:
                return {
                    "status": "stop_hit",
                    "action": "close_review",
                    "summary": "Stop zone is hit or breached. Review closing the paper trade and log the lesson.",
                    "risk_distance_pct": round(risk_distance, 2),
                    "target_progress_pct": None,
                }
            if risk_distance is not None and risk_distance <= 0.6:
                status = "near_stop"
                action = "reduce_or_close_review"
                summary = "Price is close to stop. Do not add; prepare exit review if weakness continues."

        if target_price is not None:
            if direction == "short":
                target_hit = current_price <= target_price
                total_reward = max(0.0001, entry - target_price)
                achieved = entry - current_price
            else:
                target_hit = current_price >= target_price
                total_reward = max(0.0001, target_price - entry)
                achieved = current_price - entry
            target_progress = max(0.0, min(150.0, (achieved / total_reward) * 100))
            if target_hit:
                return {
                    "status": "target_hit",
                    "action": "take_profit_review",
                    "summary": "Target zone reached. Review taking profit or closing the paper trade.",
                    "risk_distance_pct": round(risk_distance, 2) if risk_distance is not None else None,
                    "target_progress_pct": round(target_progress, 1),
                }
            if target_progress >= 75 and favorable_pct > 0 and status == "monitor":
                status = "near_target"
                action = "protect_profit_review"
                summary = "Trade is near target. Review whether to protect profit or tighten the paper plan."

        if favorable_pct <= -1.5 and status == "monitor":
            status = "weak_follow_through"
            action = "thesis_check"
            summary = "Adverse follow-through. Check whether the original trigger is failing."
        elif favorable_pct >= 1.5 and status == "monitor":
            status = "working"
            action = "hold_with_plan"
            summary = "Trade is working. Hold only while invalidation remains false."

        return {
            "status": status,
            "action": action,
            "summary": summary,
            "risk_distance_pct": round(risk_distance, 2) if risk_distance is not None else None,
            "target_progress_pct": round(target_progress, 1) if target_progress is not None else None,
            "unrealized_pnl_pct": round(favorable_pct, 2),
        }

    def _get_do_not_trade_state(self, playbook: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, List[str]]:
        blocked: List[str] = []
        leverage_rules: List[str] = []
        score = float(playbook.get("score") or 0)
        min_trade_score = float(rules.get("min_score_for_new_trade") or 78)
        min_leverage_score = float(rules.get("min_score_for_leverage") or 88)
        if score < min_trade_score:
            blocked.append(f"Score below minimum trade score {min_trade_score:.0f}.")
        if playbook.get("setup_type") == "political_copy_delay":
            if score < min_trade_score + 2:
                blocked.append(f"Political delay setup needs stronger confirmation above {min_trade_score + 2:.0f}.")
        if playbook.get("asset_class") == "crypto" and playbook.get("direction") == "short":
            blocked.append("Crypto short playbooks are disabled in the current model.")
        if playbook.get("asset_class") == "crypto" and bool(rules.get("block_crypto_leverage", True)):
            leverage_rules.append("Crypto leverage is blocked in the current rule set.")
        if score < min_leverage_score:
            leverage_rules.append(f"No leverage allowed below score {min_leverage_score:.0f}.")
        if playbook.get("learning_blocked"):
            blocked.append("Paper outcome learning blocks this setup until results improve.")
        return {"blocked": blocked, "leverage": leverage_rules}

    def _calc_return_pct(self, entry_price: float, other_price: Optional[float], direction_multiplier: int, leverage: float) -> Optional[float]:
        if not entry_price or other_price in (None, 0):
            return None
        return round((((float(other_price) - entry_price) / entry_price) * 100) * direction_multiplier * leverage, 2)

    def _calc_risk_reward(
        self,
        entry_price: float,
        stop_price: Optional[float],
        target_price: Optional[float],
        direction: Optional[str],
    ) -> Optional[str]:
        if not entry_price or stop_price in (None, 0) or target_price in (None, 0):
            return None
        if direction == "short":
            risk = float(stop_price) - entry_price
            reward = entry_price - float(target_price)
        else:
            risk = entry_price - float(stop_price)
            reward = float(target_price) - entry_price
        if risk <= 0 or reward <= 0:
            return None
        return f"1:{round(reward / risk, 2)}"

    def _get_last_price(self, ticker: Optional[str]) -> Optional[float]:
        if not ticker:
            return None
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d")
            if hist.empty:
                return None
            return round(float(hist["Close"].dropna().iloc[-1]), 2)
        except Exception:
            return None

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
