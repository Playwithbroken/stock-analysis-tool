from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import yfinance as yf

from src.storage import PortfolioManager
from src.strategy_library import StrategyLibrary
from src.performance_metrics import build_trade_performance

DEFAULT_PAPER_OUTCOME_HORIZONS_HOURS = (1, 24, 72, 168)

COMMODITY_LEVERAGE_PROXIES = [
    {
        "ticker": "GLD",
        "label": "Gold",
        "theme": "gold_safe_haven",
        "headline": "Gold leverage paper setup: inflation, real yields and risk-off flows",
        "score": 84,
    },
    {
        "ticker": "USO",
        "label": "Oil",
        "theme": "oil_supply_demand",
        "headline": "Oil leverage paper setup: supply shock, OPEC and geopolitical risk",
        "score": 82,
    },
    {
        "ticker": "XLE",
        "label": "Energy equities",
        "theme": "energy_equity_beta",
        "headline": "Energy leverage paper setup: oil beta through liquid energy equities",
        "score": 80,
    },
]


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
        autopilot_settings = self.portfolio_manager.get_paper_autopilot_settings()
        strategy_readiness = StrategyLibrary.build_readiness(
            trades,
            self.portfolio_manager.list_paper_trade_outcomes(limit=800),
        )
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "playbooks": sized_playbooks,
            "strategy_library": StrategyLibrary.all(),
            "strategy_readiness": strategy_readiness,
            "open_trades": open_trades[:12],
            "closed_trades": closed_trades[:12],
            "stats": self._build_stats(trades, float(demo_account.get("starting_capital") or 0)),
            "setup_performance": self._build_setup_performance(closed_trades),
            "entry_source_performance": self._build_entry_source_performance(closed_trades),
            "journal": self._build_journal(trades),
            "outcomes": self._build_outcome_dashboard(),
            "outcome_learning": outcome_learning,
            "rules": rules,
            "demo_account": demo_account,
            "paper_autopilot_settings": autopilot_settings,
            "auto_selection": self._build_auto_selection(
                sized_playbooks,
                trades,
                demo_account,
                strategy_readiness,
                autopilot_settings=autopilot_settings,
            ),
            "auto_learn_status": self._build_auto_learn_status(),
        }

    def build_demo_account_snapshot(self) -> Dict[str, Any]:
        trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(limit=300))
        return self._build_demo_account(trades, [])

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
        raw_mode = str(mode or "").lower()
        mode = raw_mode if raw_mode in {"strict", "learn", "aggressive_learning"} else "strict"
        source_key = "aggressive_exploration" if mode == "aggressive_learning" else "exploration" if mode == "learn" else "selected"
        selected = selection.get(source_key, [])[: max(1, int(max_trades or 1))]
        selected_capital = self._summarize_candidate_capital(selected)
        blocker_summary = selection.get("blocker_summary") if isinstance(selection.get("blocker_summary"), dict) else {}
        no_trade_message = self._auto_selection_no_trade_message(mode, blocker_summary)
        preview_message = (
            no_trade_message
            if not selected
            else f"{len(selected)} aggressive Learning-Kandidaten erfuellen die erweiterten Paper-Gates: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
            if mode == "aggressive_learning"
            else f"{len(selected)} Learning-Kandidaten erfuellen die Exploration-Gates: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
            if mode == "learn"
            else f"{len(selected)} Demo-Kandidaten erfuellen die Auto-Selection-Gates: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
        )
        if not execute:
            return {
                "status": "preview",
                "execute": False,
                "mode": mode,
                "selected": selected,
                "selected_capital": selected_capital,
                "opened": [],
                "rejected_count": selection.get("rejected_count"),
                "blocker_summary": blocker_summary,
                "message": preview_message,
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
                            # Recalculate size against the account after every prior auto entry.
                            "quantity": 0,
                            "leverage": 1,
                            "learning_mode": mode in {"learn", "aggressive_learning"} or bool(candidate.get("learning_mode")),
                            "risk_multiplier_override": candidate.get("risk_multiplier"),
                            "alert_source_label": "Paper-Autopilot",
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
        execution_message = (
            no_trade_message
            if not selected and not opened
            else f"{len(opened)} aggressive Paper-Learning-Trades eroeffnet; {len(errors)} im finalen Gate geblockt. Geplant: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
            if mode == "aggressive_learning"
            else f"{len(opened)} Paper-Learning-Trades eroeffnet; {len(errors)} im finalen Gate geblockt. Geplant: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
            if mode == "learn"
            else f"{len(opened)} Paper-Trades eroeffnet; {len(errors)} im finalen Gate geblockt. Geplant: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
        )
        return {
            "status": "ok" if not errors else "partial",
            "execute": True,
            "mode": mode,
            "selected": selected,
            "selected_capital": selected_capital,
            "opened": opened,
            "errors": errors,
            "rejected_count": selection.get("rejected_count"),
            "blocker_summary": blocker_summary,
            "demo_account_after": self.build_demo_account_snapshot() if opened else dashboard.get("demo_account", {}),
            "message": execution_message,
        }

    def _summarize_candidate_capital(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        notional = sum(float(item.get("suggested_notional_value") or 0) for item in candidates)
        max_loss = sum(float(item.get("suggested_max_loss_value") or 0) for item in candidates)
        return {
            "count": len(candidates),
            "notional_value": round(notional, 2),
            "max_loss_value": round(max_loss, 2),
        }

    def _auto_selection_no_trade_message(self, mode: str, blocker_summary: Dict[str, Any]) -> str:
        label = "Aggressive Learning" if mode == "aggressive_learning" else "Learning" if mode == "learn" else "Strict"
        next_best = blocker_summary.get("next_best_rejected") if isinstance(blocker_summary, dict) else None
        if isinstance(next_best, dict) and next_best.get("ticker"):
            reason_values = next_best.get("display_reasons") or next_best.get("reasons") or []
            reasons = " / ".join(str(item).strip().rstrip(".") for item in reason_values[:2])
            next_action = str(next_best.get("next_action") or "").strip().rstrip(".")
            parts = [f"0 {label}-Paper-Kandidaten erfüllen die Gates. Nächster Kandidat: {next_best.get('ticker')}"]
            if reasons:
                parts.append(f"Geblockt durch {reasons}")
            if next_action:
                parts.append(f"Nächster Schritt: {next_action}")
            return ". ".join(parts) + "."
        top_reasons = blocker_summary.get("top_reasons") if isinstance(blocker_summary, dict) else []
        if top_reasons:
            reason = str((top_reasons[0] or {}).get("display_reason") or (top_reasons[0] or {}).get("reason") or "Quality-Gates")
            return f"0 {label}-Paper-Kandidaten erfüllen die Gates. Hauptblocker: {reason}."
        return f"0 {label}-Paper-Kandidaten erfüllen die Gates. Erst auf ein saubereres Setup warten, bevor Demo-Risiko geöffnet wird."

    def _auto_rejection_display_reason(self, reason: str) -> str:
        text = str(reason or "").strip()
        lower = text.lower()
        if "score below auto minimum" in lower:
            return "Score unter Auto-Minimum 88"
        if "score below minimum trade score" in lower:
            return "Score unter Mindestqualität 78"
        if "same ticker/setup/direction already open" in lower:
            return "gleicher Ticker/Setup/Richtung läuft bereits"
        if "missing paper journal" in lower:
            return "fehlendes Paper-Journal"
        if "risk review" in lower:
            return "Paper-Konto im Risiko-Review"
        if "exit actions open" in lower:
            return "offene Exit-Aktionen zuerst prüfen"
        if "daily paper loss limit reached" in lower:
            return "Tagesverlust-Limit erreicht"
        if "paper loss streak cooldown is active" in lower:
            return "Cooldown nach Verlustserie aktiv"
        if "paper risk circuit" in lower:
            return "Paper-Risk-Circuit aktiv"
        if "open risk budget is exhausted" in lower:
            return "offenes Risikobudget ausgeschöpft"
        if "gross exposure budget is exhausted" in lower:
            return "maximale Gesamt-Exposure erreicht"
        if "demo cash capacity is exhausted" in lower:
            return "kein freies Demo-Cash"
        if "ticker exposure budget is exhausted" in lower:
            return "maximale Ticker-Exposure erreicht"
        if "option premium budget is exhausted" in lower:
            return "maximale offene Optionspraemie erreicht"
        if "open-trade slots exhausted" in lower or "maximum demo open trades reached" in lower:
            return "maximale Anzahl offener Demo-Trades erreicht"
        if "missing ticker or reference price" in lower:
            return "Ticker oder Referenzkurs fehlt"
        if "market_data_timestamp_missing" in lower or "market_snapshot_missing" in lower:
            return "Marktzeitpunkt oder Snapshot fehlt"
        if "market_data_stale" in lower:
            return "Marktdaten sind zu alt"
        if "market_liquidity_too_thin" in lower:
            return "Liquiditaet liegt unter dem Paper-Mindestwert"
        if "trade ticket is not paper ready" in lower:
            return "Trade-Ticket ist noch nicht Paper-ready"
        if "missing thesis, trigger or invalidation" in lower:
            return "These, Trigger oder Invalidierung fehlt"
        if "option remains paper-only" in lower or "option chain" in lower or "option bleibt paper-only" in lower or "optionskette" in lower:
            return "Option bleibt Paper-only bis zur manuellen Optionskettenprüfung"
        if "paper outcome learning blocks" in lower or "paper-ergebnisse" in lower:
            return "Paper-Learning blockiert dieses Setup"
        if "demo risk gate blocked" in lower:
            return "Demo-Risiko-Gate blockiert"
        if "trade signal rules blocked" in lower:
            return "Signal-Regeln blockieren dieses Playbook"
        if "strict-signalregel:" in lower:
            return text
        if "signalregel:" in lower:
            return text
        return text

    def create_trade_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade = self.portfolio_manager.create_paper_trade(payload)
        self._schedule_trade_outcomes(trade)
        return self._enrich_trade(trade)

    def validate_leverage_product_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._validate_leverage_product_data(payload)

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
        entry_source_label = str(payload.get("alert_source_label") or "Paper-Autopilot")
        playbook = {**playbook, "entry_source_label": entry_source_label}
        learning_mode = bool(payload.get("learning_mode"))
        risk_multiplier_override = payload.get("risk_multiplier_override")
        product_data_validation = {"valid": True, "errors": [], "warnings": [], "data": {}}
        if playbook.get("leverage_product_type"):
            product_data_validation = self._validate_leverage_product_data(payload.get("product_data") or {})
            if not product_data_validation["valid"]:
                raise ValueError(
                    "Leveraged product data gate blocks this paper trade: "
                    + ", ".join(product_data_validation["errors"])
                )
            playbook = {
                **playbook,
                "leveraged_product": product_data_validation["data"],
                "product_data_warnings": product_data_validation["warnings"],
            }
        hard_rule_reasons = [
            str(item)
            for item in playbook.get("do_not_trade_reasons", [])
            if not str(item).lower().startswith("score below minimum trade score")
        ]
        hard_demo_reasons = [
            str(item)
            for item in playbook.get("demo_block_reasons", [])
            if (
                (str(item) != "Playbook is blocked by signal rules." and not str(item).startswith("Strict-Signalregel:"))
                or hard_rule_reasons
            )
        ]
        if playbook.get("do_not_trade_reasons") and (not learning_mode or hard_rule_reasons):
            raise ValueError("Playbook is blocked by do-not-trade rules.")
        if playbook.get("demo_block_reasons") and (not learning_mode or hard_demo_reasons):
            raise ValueError("Demo account risk gate blocks this playbook.")

        is_option = playbook.get("asset_class") == "option"
        if is_option:
            execution_market = self._get_market_snapshot(playbook.get("ticker"))
            execution_blockers = self._market_snapshot_blockers(execution_market)
            if execution_blockers:
                raise ValueError(f"Underlying market data gate blocks this option playbook: {', '.join(execution_blockers)}")
            direction = playbook.get("direction") or direction
            underlying_price = float(execution_market.get("price") or 0)
            last_price = round(
                float((playbook.get("leveraged_product") or {}).get("ask") or max(0.35, underlying_price * 0.025)),
                4,
            )
            playbook = {
                **playbook,
                "reference_price": last_price,
                "underlying_reference_price": underlying_price,
                "data_as_of": execution_market.get("data_as_of"),
                "market_data": execution_market,
            }
        else:
            execution_market = self._get_market_snapshot(playbook.get("ticker"))
            execution_blockers = self._market_snapshot_blockers(execution_market)
            if execution_blockers:
                raise ValueError(f"Market data gate blocks this playbook: {', '.join(execution_blockers)}")
            last_price = float(execution_market.get("price") or 0)
            playbook = {
                **playbook,
                "reference_price": last_price,
                "data_as_of": execution_market.get("data_as_of"),
                "market_data": execution_market,
            }
        if last_price <= 0:
            raise ValueError("No valid market price available for this playbook.")
        entry_reference_price = last_price
        entry_execution = self._simulate_execution_fill(
            reference_price=entry_reference_price,
            direction=direction,
            phase="entry",
            asset_class=str(playbook.get("asset_class") or "equity"),
            market_data=playbook.get("market_data") or {},
            quantity=0,
            contract_multiplier=float(playbook.get("contract_multiplier") or (100 if is_option else 1)),
        )
        last_price = float(entry_execution["fill_price"])
        playbook = {
            **playbook,
            "reference_price": last_price,
            "execution_model": {"entry": entry_execution},
        }
        final_sizing = self._suggest_demo_sizing(playbook, demo_account, risk_multiplier_override if learning_mode else None)
        if final_sizing.get("demo_tradeable") is False:
            raise ValueError("Demo account risk gate blocks the refreshed market snapshot.")
        max_quantity = float(final_sizing.get("suggested_quantity") or 0)
        if requested_quantity > max_quantity + 1e-9:
            raise ValueError("Requested quantity exceeds the current demo risk cap.")
        quantity = requested_quantity if requested_quantity > 0 else max_quantity
        if quantity <= 0:
            raise ValueError("No valid demo quantity available for this playbook.")
        entry_execution = self._simulate_execution_fill(
            reference_price=entry_reference_price,
            direction=direction,
            phase="entry",
            asset_class=str(playbook.get("asset_class") or "equity"),
            market_data=playbook.get("market_data") or {},
            quantity=quantity,
            contract_multiplier=float(playbook.get("contract_multiplier") or (100 if is_option else 1)),
        )
        playbook["execution_model"] = {"entry": entry_execution}

        if is_option:
            stop_price = round(last_price * 0.5, 2)
            target_price = round(last_price * 2.0, 2)
        else:
            risk_buffer = float(playbook.get("risk_buffer_pct") or 3.5) / 100
            reward_buffer = float(playbook.get("reward_buffer_pct") or 7.0) / 100
            stop_price = last_price * (1 - risk_buffer) if direction == "long" else last_price * (1 + risk_buffer)
            target_price = last_price * (1 + reward_buffer) if direction == "long" else last_price * (1 - reward_buffer)
        note_playbook = {**playbook, **final_sizing}
        note_playbook["trade_ticket"] = self._build_trade_ticket(note_playbook, demo_account)
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
                "trade_ticket": note_playbook.get("trade_ticket") or {},
            }
        )
        self._schedule_trade_outcomes(created)
        enriched = self._enrich_trade(created)
        enriched["playbook_id"] = playbook_id
        enriched["source_playbook"] = {
            "id": playbook.get("id"),
            "ticker": playbook.get("ticker"),
            "asset_class": playbook.get("asset_class"),
            "direction": direction,
            "setup_type": playbook.get("setup_type"),
            "strategy_id": (playbook.get("strategy") or {}).get("id"),
            "strategy_label": (playbook.get("strategy") or {}).get("label"),
            "strategy_context": self._strategy_context_for_playbook(
                playbook,
                StrategyLibrary.build_readiness(
                    trades,
                    self.portfolio_manager.list_paper_trade_outcomes(limit=800),
                ),
            ),
            "trigger": (playbook.get("decision_framework") or {}).get("entry_trigger"),
            "invalidation": (playbook.get("decision_framework") or {}).get("invalidation"),
            "suggested_max_loss_value": note_playbook.get("suggested_max_loss_value"),
            "trade_ticket": note_playbook.get("trade_ticket") or {},
        }
        return enriched

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
        ticket = existing.get("trade_ticket") if isinstance(existing.get("trade_ticket"), dict) else {}
        entry_execution = (ticket.get("execution_model") or {}).get("entry") if isinstance(ticket.get("execution_model"), dict) else None
        exit_market: Dict[str, Any] = {}
        if existing.get("asset_class") == "option":
            exit_reference = float(closed_price or 0) or float(existing.get("entry_price") or 0)
            exit_market = ticket.get("market_data") if isinstance(ticket.get("market_data"), dict) else {}
        else:
            exit_market = self._get_market_snapshot(existing.get("ticker"))
            exit_reference = float(closed_price or 0) or float(exit_market.get("price") or 0) or float(existing.get("entry_price") or 0)
        if exit_reference <= 0:
            raise ValueError("No valid close price available.")
        exit_execution = None
        exit_price = exit_reference
        if isinstance(entry_execution, dict):
            exit_execution = self._simulate_execution_fill(
                reference_price=exit_reference,
                direction=str(existing.get("direction") or "long"),
                phase="exit",
                asset_class=str(existing.get("asset_class") or "equity"),
                market_data=exit_market,
                quantity=float(existing.get("quantity") or 0),
                contract_multiplier=float(existing.get("contract_multiplier") or (100 if existing.get("asset_class") == "option" else 1)),
            )
            exit_price = float(exit_execution["fill_price"])
            ticket = {
                **ticket,
                "execution_model": {
                    **(ticket.get("execution_model") or {}),
                    "exit": exit_execution,
                },
            }
        auto_outcome = self._classify_closed_trade_outcome(existing, exit_price)
        if not exit_reason and auto_outcome.get("exit_reason"):
            exit_reason = auto_outcome["exit_reason"]
        if not lessons_learned and auto_outcome.get("lesson"):
            lessons_learned = auto_outcome["lesson"]
        closed = self.portfolio_manager.close_paper_trade(
            trade_id,
            exit_price,
            notes,
            exit_reason,
            lessons_learned,
            ticket,
        )
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
            "policy": "Nur gemanagte Paper-Exits. Keine Echtgeld-Ausführung.",
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
            market_fields = self._market_reference_fields(item.get("ticker"))
            playbooks.append(
                {
                    "id": f"equity-{item.get('ticker')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "insider_follow",
                    "title": "Insider follow-through",
                    "headline": item.get("headline"),
                    "source_label": item.get("source_label"),
                    "score": score,
                    "risk_buffer_pct": 3.5 if direction == "long" else 4.0,
                    "reward_buffer_pct": 7.5,
                    "thesis": (
                        f"{item.get('source_label')} with strong {direction} bias. "
                        f"Use only if price holds after filing delay of {item.get('delay_days') if item.get('delay_days') is not None else 'offen'} days."
                    ),
                    "tags": ["long" if direction == "long" else "short", "official filing", "equity"],
                    **market_fields,
                }
            )

        for item in scoreboard.get("politics", [])[:3]:
            if not item.get("ticker"):
                continue
            direction = "long" if item.get("action") == "buy" else "short"
            market_fields = self._market_reference_fields(item.get("ticker"))
            playbooks.append(
                {
                    "id": f"politics-{item.get('ticker') or item.get('label')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "political_copy_delay",
                    "title": "Political delay setup",
                    "headline": item.get("headline"),
                    "source_label": item.get("source_label") or "official PTR disclosure",
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 4.5,
                    "reward_buffer_pct": 8.5,
                    "thesis": (
                        f"Official PTR disclosure with {item.get('detail')}. "
                        "Only valid when the tape confirms after the delayed filing."
                    ),
                    "tags": ["delayed signal", "politics", direction],
                    **market_fields,
                }
            )

        for item in scoreboard.get("etfs", [])[:2]:
            if not item.get("ticker"):
                continue
            market_fields = self._market_reference_fields(item.get("ticker"))
            playbooks.append(
                {
                    "id": f"etf-{item.get('ticker')}-long",
                    "ticker": item.get("ticker"),
                    "asset_class": "etf",
                    "direction": "long",
                    "setup_type": "etf_momentum",
                    "title": "ETF momentum continuation",
                    "headline": item.get("headline"),
                    "source_label": item.get("source_label"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 2.8,
                    "reward_buffer_pct": 6.0,
                    "thesis": "Liquid ETF with decent quality and momentum profile. Favor clean continuation over narrative chasing.",
                    "tags": ["etf", "momentum", "long"],
                    **market_fields,
                }
            )

        for item in scoreboard.get("crypto", [])[:2]:
            if not item.get("ticker"):
                continue
            market_fields = self._market_reference_fields(item.get("ticker"))
            playbooks.append(
                {
                    "id": f"crypto-{item.get('ticker')}-long",
                    "ticker": item.get("ticker"),
                    "asset_class": "crypto",
                    "direction": "long",
                    "setup_type": "crypto_flow",
                    "title": "Crypto flow momentum",
                    "headline": item.get("headline"),
                    "source_label": item.get("source_label"),
                    "score": item.get("total_score"),
                    "risk_buffer_pct": 5.5,
                    "reward_buffer_pct": 11.0,
                    "thesis": "Flow-driven crypto setup. Keep leverage conservative and size by volatility, not conviction alone.",
                    "tags": ["crypto", "momentum", "long"],
                    **market_fields,
                }
            )

        playbooks.extend(self._build_commodity_leverage_playbooks())
        playbooks.extend(self._build_option_learning_playbooks(playbooks))
        self._apply_outcome_learning(playbooks, outcome_learning or {})

        for item in playbooks:
            item["strategy"] = StrategyLibrary.find_for_playbook(item)
            rule_state = self._get_do_not_trade_state(item, rules)
            item["do_not_trade_reasons"] = rule_state["blocked"]
            item["leverage_warnings"] = rule_state["leverage"]
            item["tradeable"] = len(rule_state["blocked"]) == 0
            item["decision_framework"] = self._build_decision_framework(item)

        return sorted(playbooks, key=lambda item: float(item.get("score") or 0), reverse=True)[:16]

    def _build_trade_note_snapshot(self, playbook: Dict[str, Any], demo_account: Dict[str, Any], is_option: bool) -> str:
        framework = playbook.get("decision_framework") or {}
        ticket = playbook.get("trade_ticket") or {}
        checklist = framework.get("review_questions") or []
        lines = [
            "Entscheidungs-Snapshot beim Paper-Einstieg:",
            f"Headline: {playbook.get('headline') or 'n/a'}",
            f"Setup: {playbook.get('setup_type') or 'signal_playbook'} / {playbook.get('asset_class') or 'equity'} / {playbook.get('direction') or 'long'}",
            f"Score: {playbook.get('score')}; Beweisniveau: {framework.get('evidence_level') or 'watch'}",
            f"Demo-Größe: vorgeschlagene Menge {playbook.get('suggested_quantity')}; max. Verlust {playbook.get('suggested_max_loss_value')} {demo_account.get('currency')}.",
            f"Trigger: {framework.get('entry_trigger') or 'Manuelle Trigger-Prüfung erforderlich.'}",
            f"Invalidierung: {framework.get('invalidation') or 'Manuelle Invalidierungsprüfung erforderlich.'}",
            f"Risikoplan: {framework.get('risk_plan') or 'Nur Paper-Risiko.'}",
            f"Ticket: Schema {ticket.get('schema_version') or 'n/a'} / Status {ticket.get('status') or 'n/a'} / Paper-ready {bool(ticket.get('paper_ready'))} / Echtgeld-ready {bool(ticket.get('real_money_ready'))}.",
        ]
        if playbook.get("learning_mode"):
            lines.append("Lernmodus: reduzierte Demo-Position, kein strenges Top-Setup und nicht Echtgeld-bereit.")
        if is_option:
            lines.append("Options-Gate: nur Paper-Premienmodell; Strike, Laufzeit, Spread, IV und maximalen Prämienverlust manuell prüfen.")
        if playbook.get("product_data_required"):
            lines.append("Hebelprodukt-Daten vor Echtgeld: " + " | ".join(str(item) for item in playbook.get("product_data_required", [])[:5]))
        if playbook.get("leveraged_product"):
            product = playbook.get("leveraged_product") or {}
            lines.append(
                "Geprueftes Hebelprodukt: "
                f"{product.get('product_type') or 'product'} | Emittent {product.get('issuer') or 'n/a'} | "
                f"Strike/KO {product.get('strike_or_knockout_level') or 'n/a'} | "
                f"Bid/Ask {product.get('bid')}/{product.get('ask')} | Spread {product.get('spread_pct')}%."
            )
        for question in checklist[:3]:
            lines.append(f"Prüffrage: {question}")
        lines.append(framework.get("real_money_policy") or "Nur Entscheidungsrahmen; keine automatische Echtgeld-Ausführung.")
        return "\n".join(str(line) for line in lines if line)

    def _validate_leverage_product_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload if isinstance(payload, dict) else {}
        errors: List[str] = []
        warnings: List[str] = []

        product_type = str(payload.get("product_type") or "option_certificate").strip().lower()
        issuer = str(payload.get("issuer") or "").strip()
        expiry = str(payload.get("expiry") or "").strip()
        acknowledged = bool(payload.get("overnight_risk_ack"))

        def number_field(name: str) -> Optional[float]:
            value = payload.get(name)
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors.append(f"{name}_missing_or_invalid")
                return None
            if number <= 0:
                errors.append(f"{name}_must_be_positive")
                return None
            return number

        strike_or_ko = number_field("strike_or_knockout_level")
        bid = number_field("bid")
        ask = number_field("ask")
        distance_to_ko = None
        if payload.get("distance_to_knockout_pct") not in (None, ""):
            try:
                distance_to_ko = float(payload.get("distance_to_knockout_pct"))
            except (TypeError, ValueError):
                errors.append("distance_to_knockout_pct_invalid")

        if not issuer:
            errors.append("issuer_required")
        if not expiry:
            errors.append("expiry_required")
        else:
            parsed_expiry = self._parse_datetime(expiry)
            if not parsed_expiry:
                errors.append("expiry_invalid")
            elif parsed_expiry.date() <= datetime.utcnow().date():
                errors.append("expiry_must_be_future")

        spread_pct = None
        if bid is not None and ask is not None:
            if ask < bid:
                errors.append("ask_must_be_greater_or_equal_bid")
            mid = (bid + ask) / 2 if bid + ask > 0 else 0
            spread_pct = round(((ask - bid) / mid) * 100, 2) if mid > 0 else None
            if spread_pct is not None and spread_pct > 12:
                errors.append("spread_too_wide_over_12_pct")
            elif spread_pct is not None and spread_pct > 6:
                warnings.append("spread_wide_over_6_pct")

        if product_type in {"knockout", "ko", "turbo"}:
            if distance_to_ko is None:
                errors.append("distance_to_knockout_pct_required")
            elif distance_to_ko < 5:
                errors.append("knockout_distance_below_5_pct")
        if not acknowledged:
            errors.append("overnight_risk_ack_required")

        return {
            "valid": not errors,
            "errors": self._dedupe_reason_list(errors),
            "warnings": self._dedupe_reason_list(warnings),
            "data": {
                "product_type": product_type,
                "issuer": issuer,
                "expiry": expiry,
                "strike_or_knockout_level": strike_or_ko,
                "bid": bid,
                "ask": ask,
                "spread_pct": spread_pct,
                "distance_to_knockout_pct": distance_to_ko,
                "overnight_risk_ack": acknowledged,
                "validated_at": datetime.utcnow().isoformat(),
            },
        }

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
        is_commodity_leverage = str(playbook.get("setup_type") or "").startswith("commodity_")
        strategy = playbook.get("strategy") or StrategyLibrary.find_for_playbook(playbook)

        direction_label = "Aufwärtsbewegung" if direction in {"long", "call"} else "Abwärtsbewegung"
        entry_trigger = str(strategy.get("trigger_template") or "").format(ticker=ticker) or (
            f"{ticker} bestätigt die {direction_label} nach dem Signal mit sauberer Preisreaktion und Volumen."
        )
        invalidation = str(strategy.get("invalidation_template") or "").format(ticker=ticker) or (
            f"These ist ungültig, wenn {ticker} die geplante Stop-Zone bricht, Newsqualität nachlässt oder die Marktbreite die Bewegung nicht bestätigt."
        )
        risk_plan = (
            f"Nur Paper-Größe. Geplanter Risikopuffer {risk_pct}% und Zielpuffer {reward_pct}%; keine Positionsvergrößerung nach Einstieg."
        )
        if is_option:
            entry_trigger = (
                f"{direction.upper()} nur als Paper-Test, nachdem Underlying, Liquidität und Timing bestätigt sind."
            )
            invalidation = (
                "Ungültig, wenn Underlying-Momentum nachlässt, Spread breit ist, IV/Laufzeit unattraktiv sind oder maximaler Prämienverlust nicht dokumentiert ist."
            )
            risk_plan = "Nur Paper-Option mit definiertem Risiko; maximaler Verlust ist die Prämie, keine Echtgeld-Ausführung aus diesem Modell."

        if is_commodity_leverage:
            underlying = playbook.get("underlying_asset") or ticker
            proxy = playbook.get("underlying_proxy") or ticker
            entry_trigger = (
                f"{underlying} Hebel-Proxy {proxy}: Paper-Test nur, wenn Makro-Nachricht, Future/Spot-Reaktion "
                "und ETF-Volumen dieselbe Richtung bestaetigen."
            )
            invalidation = (
                "Ungueltig, wenn die Makro-Nachricht zurueckgenommen wird, der Future/Spot-Markt nicht bestaetigt, "
                "Spread/IV unattraktiv ist oder das echte Hebelprodukt zu nah am Knockout liegt."
            )
            risk_plan = (
                "Nur Paper-Hebelproxy. Maximaler Verlust ist im Modell die Praemie; echte Optionsscheine/Knockouts "
                "brauchen Strike/Knockout, Laufzeit, Spread, Emittent und Overnight-Risiko vor jeder Real-Money-Pruefung."
            )

        evidence_level = "watch"
        if blocked:
            evidence_level = "blocked"
        elif score >= 90:
            evidence_level = "high_quality_paper"
        elif score >= 78:
            evidence_level = "paper_candidate"

        review_questions = [
            "Ist das Signal noch frisch und durch Preis, Volumen und Marktumfeld bestätigt?",
            "Welches konkrete Ereignis macht die These ungültig?",
            "Ist das Positionsrisiko vor Eröffnung akzeptabel?",
        ]
        if setup_type == "political_copy_delay":
            review_questions.append("Ist das politische Filing zu verspätet, um noch Edge zu haben?")
        if is_option:
            review_questions.append("Wurden Strike, Laufzeit, Spread, IV und Prämienrisiko manuell geprüft?")

        return {
            "evidence_level": evidence_level,
            "entry_trigger": entry_trigger,
            "invalidation": invalidation,
            "risk_plan": risk_plan,
            "data_checks": [
                "Preisreferenz vorhanden",
                "Stop und Ziel definiert",
                "Kein geblocktes Lernsetup beteiligt" if not blocked else "Blocker muss zuerst gelöst werden",
                "Manuelle Prüfung vor Echtgeld erforderlich",
            ],
            "review_questions": review_questions,
            "blocked_reasons": blocked,
            "warnings": warnings,
            "strategy_id": strategy.get("id"),
            "strategy_label": strategy.get("label"),
            "strategy_horizon": strategy.get("horizon"),
            "quality_gates": strategy.get("quality_gates") or [],
            "risk_notes": strategy.get("risk_notes") or [],
            "product_data_required": playbook.get("product_data_required") or [],
            "real_world_gate": strategy.get("real_world_gate"),
            "real_money_policy": "Nur Entscheidungsrahmen; Echtgeld-Ausführung erfordert manuelle Prüfung und dokumentiertes Risiko.",
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

        current_market = self._get_market_snapshot(ticker)
        current_reference = current_market.get("price")
        if current_reference is None:
            return {
                "status": "pending_data",
                "checked_at": checked_at,
                "notes": "Price data unavailable; outcome not scored.",
            }
        ticket = item.get("trade_ticket") if isinstance(item.get("trade_ticket"), dict) else {}
        execution_model = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        current_price = float(current_reference)
        execution_note = ""
        if isinstance(execution_model.get("entry"), dict):
            exit_execution = self._simulate_execution_fill(
                reference_price=current_price,
                direction=direction,
                phase="exit",
                asset_class=asset_class,
                market_data=current_market,
                quantity=float(item.get("quantity") or 0),
                contract_multiplier=float(item.get("contract_multiplier") or 1),
            )
            current_price = float(exit_execution["fill_price"])
            execution_note = f" Conservative exit fill includes {exit_execution['cost_bps']} bps execution cost."
        raw_move = ((current_price / entry) - 1) * 100
        favorable = -raw_move if direction == "short" else raw_move
        result, error_tag, notes = self._score_paper_outcome(favorable, item)
        return {
            "status": "evaluated",
            "result": result,
            "checked_at": checked_at,
            "check_price": current_price,
            "performance_pct": round(favorable, 2),
            "notes": f"{notes}{execution_note}",
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

    def _classify_closed_trade_outcome(self, trade: Dict[str, Any], exit_price: float) -> Dict[str, str]:
        entry = float(trade.get("entry_price") or 0)
        if entry <= 0 or exit_price <= 0:
            return {}
        direction_multiplier = -1 if trade.get("direction") == "short" else 1
        pnl_pct = self._calc_return_pct(entry, exit_price, direction_multiplier, float(trade.get("leverage") or 1))
        if pnl_pct is None:
            return {}
        if pnl_pct > 0:
            target = trade.get("target_price")
            target_price = float(target) if target not in (None, 0) else None
            target_hit = False
            if target_price is not None:
                target_hit = exit_price <= target_price if trade.get("direction") == "short" else exit_price >= target_price
            exit_reason = "target_or_profit_taken" if target_hit else "profitable_discretionary_exit"
            return {
                "exit_reason": exit_reason,
                "lesson": (
                    f"Auto-classified win: {exit_reason}. Repeat only if the same trigger, risk/reward and market context are present."
                ),
            }
        if abs(float(pnl_pct)) < 0.15:
            return {
                "exit_reason": "flat_exit",
                "lesson": "Auto-classified flat exit. Check whether time in trade, signal quality or opportunity cost justified the entry.",
            }
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
                reason = f"Setup {setup_type} wird durch Paper-Ergebnisse geblockt: {hit_rate}% Trefferquote über {decisive} klare Prüfungen."
            elif hit_rate < 35:
                score_delta = -8
                reason = f"Setup {setup_type} wird durch Paper-Ergebnisse herabgestuft: {hit_rate}% Trefferquote über {decisive} klare Prüfungen."
            elif decisive >= 8 and hit_rate >= 60:
                score_delta = 4
                reason = f"Setup {setup_type} hat positive Paper-Beweise: {hit_rate}% Trefferquote über {decisive} klare Prüfungen."
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
        readiness_label = "nur Paper"
        if option_ready:
            readiness_status = "manual_review_ready"
            readiness_label = "manuelle Prüfung bereit"
        elif option_decisive >= 10 and option_hit_rate >= 45:
            readiness_status = "building_evidence"
            readiness_label = "Beweise sammeln"

        review_focus: List[str] = []
        if blocked_setups:
            review_focus.append(f"Geblockte Setup-Typen nicht mehr nutzen: {', '.join(item['setup_type'] for item in blocked_setups[:3])}.")
        if downgraded_setups:
            review_focus.append(f"Positionsgröße reduzieren oder stärkere Bestätigung verlangen für: {', '.join(item['setup_type'] for item in downgraded_setups[:3])}.")
        if upgraded_setups:
            review_focus.append(f"Stärkere Setups weiter testen: {', '.join(item['setup_type'] for item in upgraded_setups[:3])}.")
        if top_error_tags:
            review_focus.append(f"Nächster Hauptfehler zum Verbessern: {top_error_tags[0]['error_tag']} ({top_error_tags[0]['count']} Fehlschläge).")
        if not review_focus:
            review_focus.append("Mehr geschlossene und automatisch geprüfte Paper-Trades sammeln, bevor Echtgeld-Regeln verändert werden.")

        manual_review_checklist = [
            "These wurde vor Einstieg schriftlich festgehalten.",
            "Trigger, Stop, Ziel und Invalidierung sind klar.",
            "Positionsrisiko liegt innerhalb der Konto-Leitplanken.",
            "Kein geblockter Setup-Typ ist beteiligt.",
            "Bei Optionen: Laufzeit, Strike, Spread und maximaler Prämienverlust wurden manuell geprüft.",
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
                    "Optionen bleiben nur Paper, bis 20 klare Prüfungen und >=55% Trefferquote erreicht sind."
                    if not option_ready
                    else "Optionen haben genug Paper-Beweise für manuelle Prüfung, nicht für automatische Ausführung."
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
                "real_money_policy": "Nur Entscheidungsrahmen: keine automatische Echtgeld-Ausführung.",
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
                    notes.append(str(option_readiness.get("reason") or "Optionen bleiben nur Paper."))
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

    def _strategy_context_for_playbook(
        self,
        playbook: Dict[str, Any],
        readiness_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        strategy = playbook.get("strategy") or StrategyLibrary.find_for_playbook(playbook)
        strategy_id = str(strategy.get("id") or "")
        readiness = next(
            (item for item in readiness_rows if str(item.get("id") or "") == strategy_id),
            {},
        )
        performance = readiness.get("performance") if isinstance(readiness.get("performance"), dict) else {}
        return {
            "id": strategy_id,
            "label": strategy.get("label"),
            "status": readiness.get("status") or "not_started",
            "recommendation": readiness.get("recommendation") or "collect_first_trade",
            "real_world_ready": bool(readiness.get("real_world_ready")),
            "paper_trades": readiness.get("paper_trades") or 0,
            "decisive_checks": readiness.get("decisive_checks") or 0,
            "hit_rate": readiness.get("hit_rate") or 0,
            "profit_factor": performance.get("profit_factor"),
            "expectancy_value": performance.get("expectancy_value"),
            "evidence_label": performance.get("evidence_label"),
            "sample_size": performance.get("sample_size") or 0,
            "minimum_usable_sample": performance.get("minimum_usable_sample") or 30,
            "readiness_gaps": (readiness.get("readiness_gaps") or [])[:3],
            "next_step": readiness.get("next_step") or "Paper-Beweise sammeln.",
        }

    def _build_auto_selection(
        self,
        playbooks: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        demo_account: Dict[str, Any],
        strategy_readiness: List[Dict[str, Any]] | None = None,
        max_candidates: int = 5,
        autopilot_settings: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if autopilot_settings is None and hasattr(self, "portfolio_manager"):
            autopilot_settings = self.portfolio_manager.get_paper_autopilot_settings()
        autopilot_settings = autopilot_settings or {
            "strict_min_score": 88,
            "learning_min_score": 60,
            "aggressive_min_score": 52,
            "learning_risk_multiplier": 0.10,
            "aggressive_risk_multiplier": 0.25,
        }
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
        min_score = float(autopilot_settings.get("strict_min_score") or os.getenv("PAPER_TRADING_AUTO_MIN_SCORE", "88"))
        exploration_min_score = float(
            autopilot_settings.get("learning_min_score") or os.getenv("PAPER_TRADING_EXPLORATION_MIN_SCORE", "60")
        )
        aggressive_min_score = float(
            autopilot_settings.get("aggressive_min_score") or os.getenv("PAPER_TRADING_AGGRESSIVE_LEARNING_MIN_SCORE", "52")
        )
        exploration_risk_multiplier = min(
            0.35,
            max(
                0.03,
                float(
                    autopilot_settings.get("learning_risk_multiplier")
                    or os.getenv("PAPER_TRADING_EXPLORATION_RISK_MULTIPLIER", "0.10")
                ),
            ),
        )
        aggressive_risk_multiplier = min(
            0.65,
            max(
                exploration_risk_multiplier,
                float(
                    autopilot_settings.get("aggressive_risk_multiplier")
                    or os.getenv("PAPER_TRADING_AGGRESSIVE_LEARNING_RISK_MULTIPLIER", "0.25")
                ),
            ),
        )
        selected: List[Dict[str, Any]] = []
        exploration: List[Dict[str, Any]] = []
        aggressive_exploration: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for playbook in playbooks:
            reasons: List[str] = []
            exploration_reasons: List[str] = []
            aggressive_reasons: List[str] = []
            score = float(playbook.get("score") or 0)
            key = (
                str(playbook.get("ticker") or "").upper(),
                str(playbook.get("setup_type") or ""),
                str(playbook.get("direction") or ""),
                str(playbook.get("asset_class") or ""),
            )
            framework = playbook.get("decision_framework") or {}
            ticket = playbook.get("trade_ticket") if isinstance(playbook.get("trade_ticket"), dict) else {}
            ticket_validation = ticket.get("validation") if isinstance(ticket.get("validation"), dict) else {}
            ticket_errors = [str(item) for item in ticket_validation.get("errors") or []]
            ticket_blockers = [str(item) for item in ticket_validation.get("blocked_reasons") or []]
            ticket_only_score_blocked = bool(ticket_blockers) and all(
                "score below minimum trade score" in item.lower() or item.startswith("Strict-Signalregel:")
                for item in ticket_blockers
            )
            strategy_context = self._strategy_context_for_playbook(playbook, strategy_readiness or [])
            hard_rule_reasons = [
                str(item)
                for item in playbook.get("do_not_trade_reasons", [])
                if not str(item).lower().startswith("score below minimum trade score")
            ]
            rule_reasons = [str(item) for item in playbook.get("do_not_trade_reasons", [])]
            if score < min_score:
                reasons.append(f"score below auto minimum {min_score:.0f}")
            if score < exploration_min_score:
                exploration_reasons.append(f"score below learning minimum {exploration_min_score:.0f}")
            if score < aggressive_min_score:
                aggressive_reasons.append(f"score below aggressive learning minimum {aggressive_min_score:.0f}")
            if playbook.get("tradeable") is False:
                reasons.extend(rule_reasons[:3] or ["trade signal rules blocked this playbook"])
            if playbook.get("demo_tradeable") is False and not playbook.get("demo_block_reasons"):
                reasons.append("demo risk gate blocked")
            if hard_rule_reasons:
                exploration_reasons.extend(hard_rule_reasons[:3])
                aggressive_reasons.extend(hard_rule_reasons[:3])
            if playbook.get("demo_block_reasons"):
                demo_reasons = [
                    str(item)
                    for item in playbook.get("demo_block_reasons", [])
                    if str(item) != "Playbook is blocked by signal rules."
                ]
                reasons.extend(demo_reasons[:3])
                hard_demo_reasons = [
                    str(item)
                    for item in playbook.get("demo_block_reasons", [])
                    if (
                        (str(item) != "Playbook is blocked by signal rules." and not str(item).startswith("Strict-Signalregel:"))
                        or hard_rule_reasons
                    )
                ]
                exploration_reasons.extend(hard_demo_reasons[:3])
                aggressive_reasons.extend(hard_demo_reasons[:3])
            if key in open_keys:
                reasons.append("same ticker/setup/direction already open")
                exploration_reasons.append("same ticker/setup/direction already open")
                aggressive_reasons.append("same ticker/setup/direction already open")
            if not playbook.get("ticker") or not playbook.get("reference_price"):
                reasons.append("missing ticker or reference price")
                exploration_reasons.append("missing ticker or reference price")
                aggressive_reasons.append("missing ticker or reference price")
            if not framework.get("entry_trigger") or not framework.get("invalidation") or not playbook.get("thesis"):
                reasons.append("missing thesis, trigger or invalidation")
                exploration_reasons.append("missing thesis, trigger or invalidation")
                aggressive_reasons.append("missing thesis, trigger or invalidation")
            ticket_reasons = [f"trade ticket invalid: {item}" for item in ticket_errors]
            if ticket_reasons:
                reasons.extend(ticket_reasons)
                exploration_reasons.extend(ticket_reasons)
                aggressive_reasons.extend(ticket_reasons)
            elif ticket.get("paper_ready") is not True:
                reasons.append("trade ticket is not paper ready")
                if not ticket_only_score_blocked:
                    aggressive_reasons.append("trade ticket is not paper ready")
            if playbook.get("asset_class") == "option":
                readiness = (demo_account.get("learning_feedback") or {}).get("option_win_rate")
                if readiness is None:
                    reasons.append("Option bleibt Paper-only und braucht manuelle Optionskettenprüfung")
                    exploration_reasons.append("Optionskette muss vor Exploration manuell geprüft werden")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected):
                reasons.append("demo account open-trade slots exhausted")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected) + len(exploration):
                exploration_reasons.append("demo account open-trade slots exhausted")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected) + len(exploration) + len(aggressive_exploration):
                aggressive_reasons.append("demo account open-trade slots exhausted")
            if playbook.get("asset_class") == "option" and not aggressive_reasons:
                aggressive_reasons.append("Optionskette muss vor aggressive Learning manuell geprueft werden")

            row = {
                "id": playbook.get("id"),
                "ticker": playbook.get("ticker"),
                "asset_class": playbook.get("asset_class"),
                "direction": playbook.get("direction"),
                "setup_type": playbook.get("setup_type"),
                "strategy_id": (playbook.get("strategy") or {}).get("id"),
                "strategy_label": (playbook.get("strategy") or {}).get("label"),
                "strategy_context": strategy_context,
                "score": score,
                "auto_score_gap": round(max(0.0, min_score - score), 1),
                "learning_score_gap": round(max(0.0, exploration_min_score - score), 1),
                "aggressive_learning_score_gap": round(max(0.0, aggressive_min_score - score), 1),
                "title": playbook.get("title"),
                "headline": playbook.get("headline"),
                "suggested_quantity": playbook.get("suggested_quantity"),
                "suggested_notional_value": playbook.get("suggested_notional_value"),
                "suggested_max_loss_value": playbook.get("suggested_max_loss_value"),
                "learning_mode": False,
                "trigger": framework.get("entry_trigger"),
                "invalidation": framework.get("invalidation"),
                "trade_ticket": playbook.get("trade_ticket") or {},
                "reasons": self._dedupe_reason_list(reasons),
                "learning_block_reasons": self._dedupe_reason_list(exploration_reasons),
                "aggressive_learning_block_reasons": self._dedupe_reason_list(aggressive_reasons),
            }
            row["display_reasons"] = [self._auto_rejection_display_reason(reason) for reason in row["reasons"]]
            row["learning_block_display_reasons"] = [
                self._auto_rejection_display_reason(reason)
                for reason in row["learning_block_reasons"]
            ]
            row["aggressive_learning_block_display_reasons"] = [
                self._auto_rejection_display_reason(reason)
                for reason in row["aggressive_learning_block_reasons"]
            ]
            row["next_action"] = self._auto_rejection_next_action(row["reasons"])
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
                learning_row["risk_multiplier"] = exploration_risk_multiplier
                learning_row["reasons"] = [f"learning mode: reduced risk x{exploration_risk_multiplier:g}"]
                exploration.append(learning_row)
            if not aggressive_reasons and reasons and playbook.get("asset_class") != "option":
                aggressive_row = dict(row)
                aggressive_row["learning_mode"] = True
                aggressive_row["aggressive_learning_mode"] = True
                aggressive_row["suggested_quantity"] = round(float(playbook.get("suggested_quantity") or 0) * aggressive_risk_multiplier, 6)
                aggressive_row["suggested_notional_value"] = round(float(playbook.get("suggested_notional_value") or 0) * aggressive_risk_multiplier, 2)
                aggressive_row["suggested_max_loss_value"] = round(float(playbook.get("suggested_max_loss_value") or 0) * aggressive_risk_multiplier, 2)
                aggressive_row["risk_multiplier"] = aggressive_risk_multiplier
                aggressive_row["reasons"] = [f"aggressive learning mode: reduced risk x{aggressive_risk_multiplier:g}"]
                aggressive_exploration.append(aggressive_row)
            if len(selected) >= max_candidates:
                break

        return {
            "mode": "paper_autopilot_preview",
            "min_score": min_score,
            "exploration_min_score": exploration_min_score,
            "aggressive_learning_min_score": aggressive_min_score,
            "exploration_risk_multiplier": exploration_risk_multiplier,
            "aggressive_learning_risk_multiplier": aggressive_risk_multiplier,
            "selected": selected,
            "exploration": exploration[:max_candidates],
            "aggressive_exploration": aggressive_exploration[: max(8, max_candidates)],
            "rejected": rejected[:8],
            "rejected_count": len(rejected),
            "blocker_summary": self._summarize_auto_rejections(rejected),
            "interesting_now": self._build_interesting_now(selected, exploration, aggressive_exploration, rejected),
            "settings": autopilot_settings,
            "policy": "Paper-only Auto-Auswahl. Strict-Modus priorisiert Qualität; Lernmodus nutzt kleineres Demo-Risiko zum Sammeln von Beweisen.",
        }

    def _build_interesting_now(
        self,
        selected: List[Dict[str, Any]],
        exploration: List[Dict[str, Any]],
        aggressive_exploration: List[Dict[str, Any]],
        rejected: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for source, items, weight in (
            ("strict", selected, 1000),
            ("learn", exploration, 700),
            ("aggressive_learning", aggressive_exploration, 500),
            ("watch", rejected, 0),
        ):
            for item in items:
                if not item.get("ticker"):
                    continue
                rows.append(
                    {
                        "ticker": item.get("ticker"),
                        "asset_class": item.get("asset_class"),
                        "direction": item.get("direction"),
                        "setup_type": item.get("setup_type"),
                        "source": source,
                        "score": item.get("score"),
                        "title": item.get("title") or item.get("headline"),
                        "trigger": item.get("trigger"),
                        "invalidation": item.get("invalidation"),
                        "suggested_notional_value": item.get("suggested_notional_value"),
                        "suggested_max_loss_value": item.get("suggested_max_loss_value"),
                        "sort_score": weight + float(item.get("score") or 0),
                    }
                )
        deduped: Dict[str, Dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: float(item.get("sort_score") or 0), reverse=True):
            key = str(row.get("ticker") or "").upper()
            if key and key not in deduped:
                row.pop("sort_score", None)
                deduped[key] = row
        return list(deduped.values())[:8]

    def _summarize_auto_rejections(self, rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
        reason_counts: Dict[str, int] = {}
        for item in rejected:
            for reason in item.get("reasons") or []:
                label = str(reason or "").strip()
                if not label:
                    continue
                reason_counts[label] = reason_counts.get(label, 0) + 1

        top_reasons = [
            {"reason": reason, "display_reason": self._auto_rejection_display_reason(reason), "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
        ]
        blocker_groups: Dict[str, Dict[str, Any]] = {}
        for reason, count in reason_counts.items():
            category = self._auto_rejection_category(reason)
            group = blocker_groups.setdefault(
                category,
                {
                    "category": category,
                    "label": self._auto_rejection_category_label(category),
                    "count": 0,
                    "reasons": [],
                },
            )
            group["count"] += count
            if len(group["reasons"]) < 3:
                group["reasons"].append(self._auto_rejection_display_reason(reason))
        blocker_groups_list = sorted(
            blocker_groups.values(),
            key=lambda item: (-int(item.get("count") or 0), str(item.get("label") or "")),
        )[:4]
        next_best = None
        if rejected:
            actionable_rejected = [
                item
                for item in rejected
                if "same ticker/setup/direction already open" not in {str(reason) for reason in item.get("reasons") or []}
            ]
            next_pool = actionable_rejected or rejected
            next_best = max(next_pool, key=lambda item: float(item.get("score") or 0))
            next_best_reasons = (next_best.get("reasons") or [])[:3]
            next_best_category = self._auto_rejection_category(next_best_reasons[0] if next_best_reasons else "")
            next_best = {
                "ticker": next_best.get("ticker"),
                "direction": next_best.get("direction"),
                "setup_type": next_best.get("setup_type"),
                "score": next_best.get("score"),
                "auto_score_gap": next_best.get("auto_score_gap"),
                "learning_score_gap": next_best.get("learning_score_gap"),
                "reasons": next_best_reasons,
                "display_reasons": (
                    next_best.get("display_reasons")
                    or [self._auto_rejection_display_reason(reason) for reason in (next_best.get("reasons") or [])]
                )[:3],
                "learning_block_reasons": (next_best.get("learning_block_reasons") or [])[:3],
                "learning_block_display_reasons": (
                    next_best.get("learning_block_display_reasons")
                    or [self._auto_rejection_display_reason(reason) for reason in (next_best.get("learning_block_reasons") or [])]
                )[:3],
                "next_action": next_best.get("next_action"),
                "blocker_category": next_best_category,
                "blocker_label": self._auto_rejection_category_label(next_best_category),
                "missing_to_trade": self._auto_rejection_missing_to_trade(next_best_reasons),
                "source": "best_fixable" if actionable_rejected else "best_overall",
            }

        return {
            "checked": len(rejected),
            "top_reasons": top_reasons,
            "blocker_groups": blocker_groups_list,
            "next_best_rejected": next_best,
            "duplicate_blocked_count": sum(
                1
                for item in rejected
                if "same ticker/setup/direction already open" in {str(reason) for reason in item.get("reasons") or []}
            ),
        }

    def _auto_rejection_category(self, reason: str) -> str:
        lower = str(reason or "").lower()
        if "missing paper journal" in lower:
            return "journal"
        if "risk review" in lower or "exit actions open" in lower or "paper risk circuit" in lower:
            return "risk_review"
        if any(
            marker in lower
            for marker in (
                "open risk budget is exhausted",
                "gross exposure budget is exhausted",
                "demo cash capacity is exhausted",
                "ticker exposure budget is exhausted",
                "option premium budget is exhausted",
                "open-trade slots exhausted",
                "maximum demo open trades",
            )
        ):
            return "capacity"
        if "same ticker/setup/direction already open" in lower:
            return "duplicate"
        if "score below" in lower:
            return "score"
        if "missing ticker or reference price" in lower or "trade ticket invalid" in lower:
            return "data"
        if "missing thesis, trigger or invalidation" in lower:
            return "setup_quality"
        if "option" in lower or "optionskette" in lower:
            return "options_review"
        if "paper outcome learning blocks" in lower or "paper-ergebnisse" in lower:
            return "learning_block"
        return "quality_gate"

    def _auto_rejection_category_label(self, category: str) -> str:
        labels = {
            "journal": "Journal zuerst",
            "risk_review": "Risiko pruefen",
            "capacity": "Kapazitaet voll",
            "duplicate": "Duplikat offen",
            "score": "Score zu niedrig",
            "data": "Daten fehlen",
            "setup_quality": "Setup unvollstaendig",
            "options_review": "Optionscheck fehlt",
            "learning_block": "Lernen blockiert",
            "quality_gate": "Quality-Gate",
        }
        return labels.get(str(category or ""), "Quality-Gate")

    def _auto_rejection_missing_to_trade(self, reasons: List[str]) -> str:
        text = " | ".join(str(reason or "").lower() for reason in reasons)
        if "score below auto minimum" in text:
            return "Score 88+ oder staerkere Preis-/Volumenbestaetigung"
        if "score below minimum trade score" in text:
            return "Score 78+ und bessere Signalqualitaet"
        if "missing thesis, trigger or invalidation" in text:
            return "These, Trigger und Invalidierung voll dokumentieren"
        if "missing ticker or reference price" in text:
            return "Kursdaten oder Ticker-Zuordnung reparieren"
        if "same ticker/setup/direction already open" in text:
            return "Bestehenden Paper-Trade managen statt doppeln"
        if "paper risk circuit" in text:
            return "Cooldown abwarten und Verlustserie pruefen, bevor ein neuer Entry startet"
        if "risk review" in text or "exit actions open" in text:
            return "Offene Trades pruefen und Risk-Review beenden"
        if "gross exposure budget is exhausted" in text:
            return "Gesamt-Exposure durch Schliessen oder Verkleinern bestehender Trades reduzieren"
        if "demo cash capacity is exhausted" in text:
            return "Demo-Cash durch Schliessen bestehender Positionen freigeben"
        if "ticker exposure budget is exhausted" in text:
            return "Ticker-Konzentration reduzieren, bevor derselbe Ticker erneut gewichtet wird"
        if "option premium budget is exhausted" in text:
            return "Offene Optionspraemie reduzieren, bevor ein weiterer Options-Trade startet"
        if "open risk budget is exhausted" in text or "open-trade slots exhausted" in text:
            return "Risiko oder Slots freimachen"
        if "missing paper journal" in text:
            return "Fehlende Journale abschliessen"
        if "option" in text or "optionskette" in text:
            return "Strike, Laufzeit, Spread und IV manuell pruefen"
        if "paper outcome learning blocks" in text or "paper-ergebnisse" in text:
            return "Erst bessere Paper-Ergebnisse sammeln"
        return "Trigger, Risiko und Lern-Gates muessen sauber sein"

    def _auto_rejection_next_action(self, reasons: List[str]) -> str:
        text = " | ".join(str(reason or "").lower() for reason in reasons)
        if "missing paper journal" in text:
            return "Erst fehlende Paper-Journale abschließen; danach darf der Lernloop wieder neue Trades öffnen."
        if "paper risk circuit" in text:
            return "Keine neuen Entries: Circuit-Breaker abwarten und die letzten Verlusttrades journalisieren."
        if "risk review" in text or "exit actions open" in text:
            return "Erst offene Paper-Trades prüfen, Stop/Target bestätigen und Risk-Review abschließen."
        if "gross exposure budget is exhausted" in text:
            return "Kein neuer Entry: Gesamt-Exposure am Limit; erst Kapital freigeben."
        if "demo cash capacity is exhausted" in text:
            return "Kein neuer Entry: es ist kein freies Demo-Cash verfuegbar."
        if "ticker exposure budget is exhausted" in text:
            return "Kein neuer Entry in diesem Ticker: bestehende Konzentration zuerst reduzieren."
        if "option premium budget is exhausted" in text:
            return "Keine weitere Option: das aggregierte Praemienbudget ist ausgeschoepft."
        if "open risk budget is exhausted" in text or "open-trade slots exhausted" in text:
            return "Kein neuer Entry: Risiko oder Slots freimachen, bevor neue Exposure aufgebaut wird."
        if "same ticker/setup/direction already open" in text:
            return "Kein Duplikat eröffnen; bestehenden Paper-Trade managen oder schließen."
        if "score below auto minimum" in text:
            return "Auf Score 88+ warten oder stärkere Bestätigung durch Preis, Volumen und Newsqualität verlangen."
        if "score below minimum trade score" in text:
            return "Nicht handeln; Setup braucht erst Score 78+ und bessere Signalqualität."
        if "missing ticker or reference price" in text:
            return "Erst Kursdaten laden oder Ticker/Asset-Zuordnung prüfen."
        if "missing thesis, trigger or invalidation" in text:
            return "Erst These, Einstiegstrigger und Invalidierung vollständig dokumentieren."
        if "option remains paper-only" in text or "option chain" in text or "option bleibt paper-only" in text or "optionskette" in text:
            return "Optionskette, Strike, Laufzeit, Spread und IV manuell prüfen; bis dahin nur Paper."
        if "paper outcome learning blocks" in text or "paper-ergebnisse" in text:
            return "Setup erst wieder nutzen, wenn neue Paper-Ergebnisse die Fehlerquote verbessern."
        return "Setup beobachten; erst handeln, wenn Trigger, Risiko und Lern-Gates sauber erfüllt sind."

    def _dedupe_reason_list(self, reasons: List[str]) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        for reason in reasons:
            label = str(reason or "").strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(label)
        return result

    def _build_commodity_leverage_playbooks(self) -> List[Dict[str, Any]]:
        playbooks: List[Dict[str, Any]] = []
        for proxy in COMMODITY_LEVERAGE_PROXIES:
            ticker = str(proxy["ticker"])
            market_fields = self._market_reference_fields(ticker)
            underlying_price = float(market_fields.get("reference_price") or 0)
            if underlying_price <= 0:
                continue
            estimated_premium = round(max(0.45, underlying_price * 0.022), 2)
            for option_type, bias, score_penalty in (("call", "long", 0), ("put", "short", 3)):
                score = max(0, float(proxy["score"]) - score_penalty)
                playbooks.append(
                    {
                        "id": f"commodity-option-{ticker}-{option_type}",
                        "ticker": ticker,
                        "asset_class": "option",
                        "direction": option_type,
                        "setup_type": f"commodity_{option_type}_leverage_learning",
                        "title": f"{proxy['label']} {option_type.upper()} leverage paper setup",
                        "headline": proxy["headline"],
                        "source_label": "commodity proxy paper model",
                        "score": score,
                        "risk_buffer_pct": 100.0,
                        "reward_buffer_pct": 120.0,
                        "thesis": (
                            f"{proxy['label']} paper-only Hebelidee ueber den liquiden Proxy {ticker}. "
                            f"Richtung {bias}; nur sinnvoll, wenn Makro-Trigger, Future/Spot-Bestaetigung und Volumen zusammenpassen."
                        ),
                        "tags": ["commodity", "leverage", proxy["theme"], option_type, "paper only"],
                        "reference_price": estimated_premium,
                        "underlying_reference_price": underlying_price,
                        "option_type": option_type,
                        "contract_multiplier": 100,
                        "max_holding_days": 7,
                        "leverage_product_type": "defined_risk_option_or_certificate_proxy",
                        "underlying_asset": proxy["label"],
                        "underlying_proxy": ticker,
                        "quality_gate": [
                            "Macro trigger is verified by at least one reliable source",
                            "Underlying proxy price and liquidity are fresh",
                            "No real-money warrant/knockout without broker product data",
                            "Max loss is premium in this paper model",
                        ],
                        "product_data_required": [
                            "Strike or knockout level",
                            "Expiry",
                            "Spread and issuer/broker quote",
                            "Implied volatility or product pricing premium",
                            "Overnight gap and issuer risk",
                        ],
                        "market_data": market_fields.get("market_data") or {},
                        "data_as_of": market_fields.get("data_as_of"),
                    }
                )
        return playbooks

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
                    "source_label": item.get("source_label"),
                    "data_as_of": item.get("data_as_of"),
                    "market_data": item.get("market_data") or {},
                }
            )
        return option_playbooks[:4]

    def _build_stats(self, trades: List[Dict[str, Any]], starting_capital: float = 0) -> Dict[str, Any]:
        closed = [trade for trade in trades if trade.get("status") == "closed" and trade.get("realized_pnl_pct") is not None]
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        winners = [trade for trade in closed if float(trade.get("realized_pnl_pct") or 0) > 0]
        losers = [trade for trade in closed if float(trade.get("realized_pnl_pct") or 0) < 0]
        performance = build_trade_performance(closed)
        realized_value = round(sum(float(trade.get("realized_pnl_value") or 0) for trade in closed), 2)
        account_realized_pct = round((realized_value / starting_capital) * 100, 2) if starting_capital > 0 else 0
        average_trade_pct = round(
            sum(float(trade.get("realized_pnl_pct") or 0) for trade in closed) / len(closed), 2
        ) if closed else 0
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
            "realized_pnl_pct": account_realized_pct,
            "realized_pnl_value": realized_value,
            "average_trade_pnl_pct": average_trade_pct,
            "best_trade_pct": round(max((float(trade.get("realized_pnl_pct") or 0) for trade in closed), default=0), 2),
            "worst_trade_pct": round(min((float(trade.get("realized_pnl_pct") or 0) for trade in closed), default=0), 2),
            "long_short_split": {
                "long": sum(1 for trade in trades if trade.get("direction") == "long"),
                "short": sum(1 for trade in trades if trade.get("direction") == "short"),
            },
            "loss_count": len(losers),
            "performance": performance,
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
            "max_gross_exposure_pct": env_float("PAPER_TRADING_MAX_GROSS_EXPOSURE_PCT", 60.0, minimum=1.0),
            "max_ticker_exposure_pct": env_float("PAPER_TRADING_MAX_TICKER_EXPOSURE_PCT", 12.0, minimum=0.1),
            "max_option_premium_pct": env_float("PAPER_TRADING_MAX_OPTION_PREMIUM_PCT", 0.75, minimum=0.01),
            "max_open_option_premium_pct": env_float("PAPER_TRADING_MAX_OPEN_OPTION_PREMIUM_PCT", 2.0, minimum=0.01),
            "risk_per_option_trade_pct": env_float("PAPER_TRADING_RISK_PER_OPTION_TRADE_PCT", 0.25, minimum=0.01),
            "max_open_trades": env_int("PAPER_TRADING_MAX_OPEN_TRADES", 12, minimum=1),
            "daily_loss_limit_pct": env_float("PAPER_TRADING_DAILY_LOSS_LIMIT_PCT", 1.0, minimum=0.1),
            "max_drawdown_pct": env_float("PAPER_TRADING_MAX_DRAWDOWN_PCT", 8.0, minimum=0.5),
            "max_consecutive_losses": env_int("PAPER_TRADING_MAX_CONSECUTIVE_LOSSES", 3, minimum=1),
            "loss_streak_cooldown_hours": env_float("PAPER_TRADING_LOSS_STREAK_COOLDOWN_HOURS", 24.0, minimum=1.0),
            "mode": "paper_learning_only",
        }

    def _build_paper_risk_circuit(
        self,
        closed_trades: List[Dict[str, Any]],
        current_equity: float,
        starting_capital: float,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        def closed_sort_value(trade: Dict[str, Any]) -> float:
            value = self._parse_datetime(trade.get("closed_at"))
            return value.timestamp() if value else 0.0

        ordered = sorted(
            closed_trades,
            key=closed_sort_value,
        )
        running_equity = float(starting_capital)
        peak_equity = float(starting_capital)
        max_drawdown_pct = 0.0
        for trade in ordered:
            running_equity += float(trade.get("realized_pnl_value") or 0)
            peak_equity = max(peak_equity, running_equity)
            drawdown_pct = ((peak_equity - running_equity) / peak_equity) * 100 if peak_equity > 0 else 0.0
            max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        peak_equity = max(peak_equity, running_equity)
        current_drawdown_pct = (
            ((peak_equity - float(current_equity)) / peak_equity) * 100
            if peak_equity > 0
            else 0.0
        )
        max_drawdown_pct = max(max_drawdown_pct, current_drawdown_pct)

        now = datetime.now()
        daily_realized_pnl = 0.0
        recent_closed = sorted(
            closed_trades,
            key=closed_sort_value,
            reverse=True,
        )
        for trade in recent_closed:
            closed_at = self._parse_datetime(trade.get("closed_at"))
            closed_day = closed_at.astimezone().date() if closed_at and closed_at.tzinfo else closed_at.date() if closed_at else None
            if closed_day == now.date():
                daily_realized_pnl += float(trade.get("realized_pnl_value") or 0)

        consecutive_losses = 0
        for trade in recent_closed:
            pnl = float(trade.get("realized_pnl_value") or 0)
            if pnl < 0:
                consecutive_losses += 1
            else:
                break
        latest_closed_at = self._parse_datetime(recent_closed[0].get("closed_at")) if recent_closed else None
        cooldown_until = (
            latest_closed_at + timedelta(hours=float(config["loss_streak_cooldown_hours"]))
            if latest_closed_at
            else None
        )
        compare_now = datetime.now(cooldown_until.tzinfo) if cooldown_until and cooldown_until.tzinfo else now
        streak_cooldown_active = bool(
            consecutive_losses >= int(config["max_consecutive_losses"])
            and cooldown_until
            and cooldown_until > compare_now
        )
        daily_loss_limit_value = float(starting_capital) * (float(config["daily_loss_limit_pct"]) / 100)
        daily_loss_blocked = daily_realized_pnl <= -daily_loss_limit_value
        reasons: List[str] = []
        if daily_loss_blocked:
            reasons.append("Daily paper loss limit reached.")
        if streak_cooldown_active:
            reasons.append("Paper loss streak cooldown is active.")
        drawdown_reduced = current_drawdown_pct >= float(config["max_drawdown_pct"])
        display_reasons = [
            "Tagesverlust-Limit erreicht; heute keine neuen Paper-Entries."
            if reason == "Daily paper loss limit reached."
            else "Drei Verluste in Folge; der Paper-Cooldown ist aktiv."
            if reason == "Paper loss streak cooldown is active."
            else reason
            for reason in reasons
        ]
        return {
            "active": bool(reasons),
            "status": "paused" if reasons else "reduced_risk" if drawdown_reduced else "ready",
            "reasons": reasons,
            "display_reasons": display_reasons,
            "daily_realized_pnl_value": round(daily_realized_pnl, 2),
            "daily_loss_limit_value": round(daily_loss_limit_value, 2),
            "current_drawdown_pct": round(max(0.0, current_drawdown_pct), 2),
            "max_drawdown_pct_seen": round(max(0.0, max_drawdown_pct), 2),
            "drawdown_limit_pct": float(config["max_drawdown_pct"]),
            "consecutive_losses": consecutive_losses,
            "max_consecutive_losses": int(config["max_consecutive_losses"]),
            "cooldown_until": cooldown_until.isoformat() if streak_cooldown_active and cooldown_until else None,
            "risk_multiplier": 0.25 if drawdown_reduced else 1.0,
        }

    def _build_demo_account(self, trades: List[Dict[str, Any]], playbooks: List[Dict[str, Any]]) -> Dict[str, Any]:
        config = self._demo_account_config()
        starting_capital = float(config["starting_capital"])
        realized_value = sum(float(trade.get("realized_pnl_value") or 0) for trade in trades if trade.get("status") == "closed")
        unrealized_value = sum(float(trade.get("unrealized_pnl_value") or 0) for trade in trades if trade.get("status") == "open")
        equity = round(starting_capital + realized_value + unrealized_value, 2)
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        closed_trades = [trade for trade in trades if trade.get("status") == "closed"]
        open_risk_value = round(sum(self._trade_open_risk_value(trade) for trade in open_trades), 2)
        open_exposure_value = round(
            sum(float(trade.get("invested_value") or 0) for trade in open_trades),
            2,
        )
        exposure_by_ticker: Dict[str, float] = {}
        for trade in open_trades:
            ticker = str(trade.get("ticker") or "UNKNOWN").upper()
            exposure_by_ticker[ticker] = round(
                exposure_by_ticker.get(ticker, 0.0) + float(trade.get("invested_value") or 0),
                2,
            )
        exposure_profile = self._build_demo_exposure_profile(open_trades, equity)
        option_premium_exposure_value = round(
            sum(float(trade.get("invested_value") or 0) for trade in open_trades if trade.get("asset_class") == "option"),
            2,
        )
        net_pnl_value = round(realized_value + unrealized_value, 2)
        net_pnl_pct = round((net_pnl_value / starting_capital) * 100, 2) if starting_capital > 0 else 0
        cash_available_value = round(max(0.0, equity - open_exposure_value), 2)
        capital_status = "ahead" if net_pnl_value > 0 else "behind" if net_pnl_value < 0 else "flat"
        realized_status = "ahead" if realized_value > 0 else "behind" if realized_value < 0 else "flat"
        capital_flow = {
            "starting_capital_value": round(starting_capital, 2),
            "equity_value": equity,
            "cash_available_value": cash_available_value,
            "open_exposure_value": open_exposure_value,
            "realized_pnl_value": round(realized_value, 2),
            "unrealized_pnl_value": round(unrealized_value, 2),
            "net_pnl_value": net_pnl_value,
            "net_pnl_pct": net_pnl_pct,
            "capital_status": capital_status,
            "realized_status": realized_status,
            "open_trade_count": len(open_trades),
            "closed_trade_count": len(closed_trades),
        }
        performance = build_trade_performance(closed_trades)
        risk_circuit = self._build_paper_risk_circuit(
            closed_trades,
            equity,
            starting_capital,
            config,
        )
        management_counts: Dict[str, int] = {}
        for trade in open_trades:
            grade = str((trade.get("management_plan") or {}).get("decision_grade") or "hold")
            management_counts[grade] = management_counts.get(grade, 0) + 1
        if risk_circuit.get("active"):
            day_status = "risk_halt"
            day_action = "Keine neuen Paper-Entries: Verlustlimit oder Verlustserien-Cooldown zuerst auslaufen lassen."
        elif management_counts.get("exit"):
            day_status = "action_required"
            day_action = "Exits prüfen, bevor ein neuer Paper-Trade geöffnet wird."
        elif management_counts.get("review"):
            day_status = "risk_review"
            day_action = "Schwache oder stop-nahe Trades prüfen, bevor neue Exposure hinzukommt."
        elif management_counts.get("protect"):
            day_status = "protect_profit"
            day_action = "Gewinnschutz bei Gewinnern nahe am Ziel prüfen."
        elif open_trades:
            day_status = "monitor"
            day_action = "Aktuellen Paper-Plan halten; keine Änderung ohne Trigger oder Invalidierung."
        else:
            day_status = "no_open_trades"
            day_action = "Auf ein sauberes Setup mit Trigger, Invalidierung und freiem Risikobudget warten."
        risk_budget = round(equity * (float(config["risk_per_trade_pct"]) / 100), 2)
        max_open_risk_value = round(equity * (float(config["max_open_risk_pct"]) / 100), 2)
        max_position_value = round(equity * (float(config["max_position_pct"]) / 100), 2)
        max_gross_exposure_value = round(equity * (float(config["max_gross_exposure_pct"]) / 100), 2)
        max_ticker_exposure_value = round(equity * (float(config["max_ticker_exposure_pct"]) / 100), 2)
        max_option_premium_value = round(equity * (float(config["max_option_premium_pct"]) / 100), 2)
        max_open_option_premium_value = round(equity * (float(config["max_open_option_premium_pct"]) / 100), 2)
        option_risk_budget = round(equity * (float(config["risk_per_option_trade_pct"]) / 100), 2)
        remaining_risk = round(max(0.0, max_open_risk_value - open_risk_value), 2)
        remaining_gross_exposure = round(max(0.0, max_gross_exposure_value - open_exposure_value), 2)
        remaining_option_premium = round(max(0.0, max_open_option_premium_value - option_premium_exposure_value), 2)
        top_ticker = max(exposure_by_ticker, key=exposure_by_ticker.get) if exposure_by_ticker else None
        return {
            **config,
            "equity": equity,
            "realized_pnl_value": round(realized_value, 2),
            "unrealized_pnl_value": round(unrealized_value, 2),
            "net_pnl_value": net_pnl_value,
            "net_pnl_pct": net_pnl_pct,
            "cash_available_value": cash_available_value,
            "capital_status": capital_status,
            "capital_flow": capital_flow,
            "performance": performance,
            "risk_circuit": risk_circuit,
            "open_risk_value": open_risk_value,
            "open_risk_pct": round((open_risk_value / equity) * 100, 2) if equity > 0 else 0,
            "open_exposure_value": open_exposure_value,
            "open_exposure_pct": round((open_exposure_value / equity) * 100, 2) if equity > 0 else 0,
            "exposure_profile": exposure_profile,
            "exposure_by_ticker": exposure_by_ticker,
            "top_ticker_exposure": {
                "ticker": top_ticker,
                "value": exposure_by_ticker.get(top_ticker, 0.0) if top_ticker else 0.0,
                "pct": round((exposure_by_ticker.get(top_ticker, 0.0) / equity) * 100, 2) if top_ticker and equity > 0 else 0.0,
            },
            "option_premium_exposure_value": option_premium_exposure_value,
            "open_trade_count": len(open_trades),
            "closed_trade_count": len(closed_trades),
            "management_counts": management_counts,
            "day_status": day_status,
            "day_action": day_action,
            "risk_budget_per_trade_value": risk_budget,
            "risk_budget_per_option_trade_value": option_risk_budget,
            "max_open_risk_value": max_open_risk_value,
            "remaining_risk_value": remaining_risk,
            "max_position_value": max_position_value,
            "max_gross_exposure_value": max_gross_exposure_value,
            "remaining_gross_exposure_value": remaining_gross_exposure,
            "max_ticker_exposure_value": max_ticker_exposure_value,
            "max_option_premium_value": max_option_premium_value,
            "max_open_option_premium_value": max_open_option_premium_value,
            "remaining_option_premium_value": remaining_option_premium,
            "open_trade_slots": max(0, int(config["max_open_trades"]) - len(open_trades)),
            "candidate_count": len(playbooks),
            "guardrails": [
                "Nur Demo-Lernkonto; keine automatische Echtgeld-Ausführung.",
                "Jede Idee braucht These, Trigger, Stop, Ziel und Nachtrade-Journal.",
                "Gesamt-, Ticker- und Options-Exposure werden vor jedem Auto-Entry neu berechnet.",
                "Calls und Puts bleiben Paper-only, bis Optionskette, IV, Strike, Laufzeit und Spread geprüft sind.",
                "Echtgeld-Nutzung erfordert manuelle Prüfung, Suitability-Check und aktuelle Marktvalidierung.",
            ],
            "learning_feedback": self._build_learning_feedback(trades),
        }

    def _build_demo_exposure_profile(self, open_trades: List[Dict[str, Any]], equity: float) -> Dict[str, Any]:
        buckets = {
            "long": {"label": "Long", "count": 0, "notional_value": 0.0, "pnl_value": 0.0},
            "short": {"label": "Short", "count": 0, "notional_value": 0.0, "pnl_value": 0.0},
            "call": {"label": "Calls", "count": 0, "notional_value": 0.0, "pnl_value": 0.0},
            "put": {"label": "Puts", "count": 0, "notional_value": 0.0, "pnl_value": 0.0},
            "other": {"label": "Andere", "count": 0, "notional_value": 0.0, "pnl_value": 0.0},
        }
        leveraged_value = 0.0
        biggest_open_risk: Dict[str, Any] | None = None
        total_notional = 0.0
        open_pnl = 0.0

        for trade in open_trades:
            direction = str(trade.get("direction") or "").lower()
            bucket_key = direction if direction in {"long", "short", "call", "put"} else "other"
            notional = float(trade.get("invested_value") or 0)
            pnl = float(trade.get("unrealized_pnl_value") or trade.get("result_value_delta") or 0)
            risk = self._trade_open_risk_value(trade)
            leverage = float(trade.get("leverage") or 1)
            buckets[bucket_key]["count"] += 1
            buckets[bucket_key]["notional_value"] += notional
            buckets[bucket_key]["pnl_value"] += pnl
            total_notional += notional
            open_pnl += pnl
            if leverage > 1 or trade.get("asset_class") == "option":
                leveraged_value += notional
            if not biggest_open_risk or risk > float(biggest_open_risk.get("risk_value") or 0):
                biggest_open_risk = {
                    "ticker": str(trade.get("ticker") or "UNKNOWN").upper(),
                    "direction": direction or "unknown",
                    "risk_value": round(risk, 2),
                    "notional_value": round(notional, 2),
                }

        rows = []
        for key, bucket in buckets.items():
            value = round(float(bucket["notional_value"]), 2)
            pnl_value = round(float(bucket["pnl_value"]), 2)
            rows.append(
                {
                    "key": key,
                    "label": bucket["label"],
                    "count": int(bucket["count"]),
                    "notional_value": value,
                    "notional_pct": round((value / equity) * 100, 2) if equity > 0 else 0.0,
                    "pnl_value": pnl_value,
                    "pnl_pct_of_notional": round((pnl_value / value) * 100, 2) if value > 0 else 0.0,
                }
            )

        net_direction = "balanced"
        if buckets["long"]["notional_value"] + buckets["call"]["notional_value"] > buckets["short"]["notional_value"] + buckets["put"]["notional_value"]:
            net_direction = "net_long"
        elif buckets["short"]["notional_value"] + buckets["put"]["notional_value"] > buckets["long"]["notional_value"] + buckets["call"]["notional_value"]:
            net_direction = "net_short"

        return {
            "net_direction": net_direction,
            "open_trade_count": len(open_trades),
            "total_notional_value": round(total_notional, 2),
            "open_pnl_value": round(open_pnl, 2),
            "leveraged_notional_value": round(leveraged_value, 2),
            "leveraged_notional_pct": round((leveraged_value / equity) * 100, 2) if equity > 0 else 0.0,
            "buckets": rows,
            "biggest_open_risk": biggest_open_risk
            or {"ticker": None, "direction": None, "risk_value": 0.0, "notional_value": 0.0},
        }

    def _attach_demo_sizing(self, playbooks: List[Dict[str, Any]], demo_account: Dict[str, Any]) -> List[Dict[str, Any]]:
        sized: List[Dict[str, Any]] = []
        for item in playbooks:
            row = dict(item)
            sizing = self._suggest_demo_sizing(row, demo_account)
            row.update(sizing)
            row["trade_ticket"] = self._build_trade_ticket(row, demo_account)
            sized.append(row)
        return sized

    def _build_trade_ticket(self, playbook: Dict[str, Any], demo_account: Dict[str, Any]) -> Dict[str, Any]:
        framework = playbook.get("decision_framework") or {}
        strategy = playbook.get("strategy") or {}
        ticker = str(playbook.get("ticker") or "").upper()
        asset_class = str(playbook.get("asset_class") or "equity").lower()
        direction = str(playbook.get("direction") or "long").lower()
        entry = float(playbook.get("reference_price") or 0)
        risk_buffer_pct = float(playbook.get("risk_buffer_pct") or 3.5)
        reward_buffer_pct = float(playbook.get("reward_buffer_pct") or 7.0)
        is_short = direction in {"short", "put"}
        is_option = asset_class == "option"

        if is_option:
            stop = round(entry * 0.5, 2) if entry > 0 else None
            target_1 = round(entry * 1.5, 2) if entry > 0 else None
            target_2 = round(entry * 2.0, 2) if entry > 0 else None
        else:
            risk_distance = entry * (risk_buffer_pct / 100)
            reward_distance = entry * (reward_buffer_pct / 100)
            stop = round(entry + risk_distance if is_short else entry - risk_distance, 4) if entry > 0 else None
            target_2 = round(entry - reward_distance if is_short else entry + reward_distance, 4) if entry > 0 else None
            target_1 = round(entry - (reward_distance / 2) if is_short else entry + (reward_distance / 2), 4) if entry > 0 else None

        risk_reward = None
        if entry > 0 and stop not in (None, entry) and target_2 not in (None, entry):
            risk_reward = round(abs(float(target_2) - entry) / abs(entry - float(stop)), 2)

        source_label = str(
            playbook.get("source_label")
            or playbook.get("publisher")
            or playbook.get("source")
            or ""
        ).strip()
        data_as_of = str(
            playbook.get("data_as_of")
            or playbook.get("updated_at")
            or playbook.get("generated_at")
            or ""
        ).strip()
        market_data = playbook.get("market_data") if isinstance(playbook.get("market_data"), dict) else {}
        execution_model = playbook.get("execution_model") if isinstance(playbook.get("execution_model"), dict) else {}
        blocked_reasons = self._dedupe_reason_list(
            [
                *[str(item) for item in playbook.get("do_not_trade_reasons", [])],
                *[str(item) for item in playbook.get("demo_block_reasons", [])],
            ]
        )
        errors: List[str] = []
        warnings: List[str] = []
        required_text = {
            "instrument": ticker,
            "thesis": str(playbook.get("thesis") or "").strip(),
            "trigger": str(framework.get("entry_trigger") or "").strip(),
            "invalidation": str(framework.get("invalidation") or "").strip(),
        }
        for field, value in required_text.items():
            if not value:
                errors.append(f"missing_{field}")
        if entry <= 0:
            errors.append("missing_entry_price")
        if stop is None:
            errors.append("missing_stop")
        if target_2 is None:
            errors.append("missing_target")
        if float(playbook.get("suggested_quantity") or 0) <= 0:
            errors.append("missing_position_size")
        if not source_label:
            warnings.append("source_label_missing")
        if not data_as_of:
            errors.append("market_data_timestamp_missing")
        errors.extend(self._market_snapshot_blockers(market_data))
        if market_data.get("liquidity_status") == "unknown":
            warnings.append("liquidity_unverified")
        if is_option:
            warnings.append("option_chain_not_validated")
        if playbook.get("leverage_product_type"):
            warnings.append("leverage_product_data_required")
        if playbook.get("product_data_required"):
            warnings.append("issuer_strike_expiry_spread_required")
        if playbook.get("leveraged_product"):
            warnings = [item for item in warnings if item not in {"leverage_product_data_required", "issuer_strike_expiry_spread_required"}]
            warnings.extend(str(item) for item in playbook.get("product_data_warnings") or [])
        warnings.extend(str(item) for item in framework.get("warnings") or [])

        paper_ready = not errors and not blocked_reasons and bool(playbook.get("demo_tradeable"))
        if blocked_reasons:
            status = "blocked"
        elif errors:
            status = "incomplete"
        elif is_option:
            status = "paper_only"
        elif paper_ready:
            status = "paper_ready"
        else:
            status = "watch"
        return {
            "schema_version": "1.0",
            "ticket_id": str(playbook.get("id") or f"{ticker}-{direction}"),
            "instrument": ticker,
            "asset_class": asset_class,
            "direction": direction,
            "status": status,
            "paper_ready": paper_ready,
            "real_money_ready": False,
            "entry_condition": required_text["trigger"],
            "entry_price": round(entry, 4) if entry > 0 else None,
            "stop_price": stop,
            "target_1": target_1,
            "target_2": target_2,
            "horizon": framework.get("strategy_horizon") or strategy.get("horizon") or "not classified",
            "quantity": playbook.get("suggested_quantity"),
            "notional_value": playbook.get("suggested_notional_value"),
            "max_loss_value": playbook.get("suggested_max_loss_value"),
            "account_risk_pct": playbook.get("suggested_risk_pct"),
            "risk_reward": risk_reward,
            "thesis": required_text["thesis"],
            "catalyst": playbook.get("headline") or playbook.get("title") or "",
            "counterargument": required_text["invalidation"],
            "invalidation": required_text["invalidation"],
            "strategy_id": framework.get("strategy_id") or strategy.get("id"),
            "strategy_label": framework.get("strategy_label") or strategy.get("label"),
            "confidence_score": playbook.get("score"),
            "evidence_level": framework.get("evidence_level") or "watch",
            "source_label": source_label or None,
            "entry_source_label": playbook.get("entry_source_label") or "Paper-Autopilot",
            "data_as_of": data_as_of or None,
            "market_data": market_data or None,
            "execution_model": execution_model or None,
            "leverage_product_type": playbook.get("leverage_product_type") or None,
            "underlying_asset": playbook.get("underlying_asset") or None,
            "underlying_proxy": playbook.get("underlying_proxy") or None,
            "product_data_required": playbook.get("product_data_required") or [],
            "leveraged_product": playbook.get("leveraged_product") or None,
            "generated_at": datetime.utcnow().isoformat(),
            "validation": {
                "valid": not errors,
                "errors": errors,
                "warnings": self._dedupe_reason_list(warnings),
                "blocked_reasons": blocked_reasons,
            },
            "policy": "Paper-only decision framework. Manual review and independent real-world validation required.",
        }

    def _suggest_demo_sizing(
        self,
        playbook: Dict[str, Any],
        demo_account: Dict[str, Any],
        risk_multiplier_override: Any = None,
    ) -> Dict[str, Any]:
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
        equity = max(1.0, float(demo_account.get("equity") or 1))
        cash_available = float(
            demo_account.get("cash_available_value")
            if demo_account.get("cash_available_value") is not None
            else equity
        )
        remaining_gross = float(
            demo_account.get("remaining_gross_exposure_value")
            if demo_account.get("remaining_gross_exposure_value") is not None
            else cash_available
        )
        ticker = str(playbook.get("ticker") or "").upper()
        exposure_by_ticker = (
            demo_account.get("exposure_by_ticker")
            if isinstance(demo_account.get("exposure_by_ticker"), dict)
            else {}
        )
        current_ticker_exposure = float(exposure_by_ticker.get(ticker) or 0)
        ticker_limit = float(demo_account.get("max_ticker_exposure_value") or max_position_value)
        remaining_ticker_exposure = max(0.0, ticker_limit - current_ticker_exposure)
        capacity_limits = [max_position_value, remaining_gross, cash_available, remaining_ticker_exposure]
        remaining_option_premium = max_position_value
        if is_option:
            remaining_option_premium = float(
                demo_account.get("remaining_option_premium_value")
                if demo_account.get("remaining_option_premium_value") is not None
                else max_position_value
            )
            capacity_limits.append(remaining_option_premium)
        max_position_value = max(0.0, min(capacity_limits))
        risk_circuit = demo_account.get("risk_circuit") if isinstance(demo_account.get("risk_circuit"), dict) else {}
        risk_multiplier = min(1.0, max(0.0, float(risk_circuit.get("risk_multiplier") or 1.0)))
        if risk_multiplier_override is not None:
            try:
                risk_multiplier *= min(1.0, max(0.01, float(risk_multiplier_override)))
            except (TypeError, ValueError):
                pass
        risk_budget *= risk_multiplier
        block_reasons: List[str] = []
        day_status = str(demo_account.get("day_status") or "")
        learning_feedback = demo_account.get("learning_feedback")
        if not isinstance(learning_feedback, dict):
            learning_feedback = {}
        missing_journal_count = int(learning_feedback.get("missing_journal_count") or 0)

        if price <= 0:
            block_reasons.append("Keine Preisreferenz für Demo-Größe.")
        if risk_circuit.get("active"):
            for reason in risk_circuit.get("reasons") or ["Paper risk circuit is active."]:
                block_reasons.append(f"Paper risk circuit: {reason}")
        elif day_status == "action_required":
            block_reasons.append("Paper-Konto hat offene Exit-Aktionen; bestehende Trades vor neuer Exposure prüfen.")
        elif day_status == "risk_review":
            block_reasons.append("Paper-Konto ist im Risiko-Review; schwache oder stop-nahe Trades zuerst prüfen.")
        if missing_journal_count > 0:
            block_reasons.append(
                f"{missing_journal_count} fehlende Paper-Journale abschließen, bevor neue Exposure hinzukommt."
            )
        if risk_budget <= 0:
            block_reasons.append("Offenes Risikobudget ist ausgeschöpft.")
        if demo_account.get("remaining_gross_exposure_value") is not None and remaining_gross <= 0:
            block_reasons.append("Gross exposure budget is exhausted.")
        if demo_account.get("cash_available_value") is not None and cash_available <= 0:
            block_reasons.append("Demo cash capacity is exhausted.")
        if demo_account.get("max_ticker_exposure_value") is not None and remaining_ticker_exposure <= 0:
            block_reasons.append("Ticker exposure budget is exhausted.")
        if is_option and demo_account.get("remaining_option_premium_value") is not None and remaining_option_premium <= 0:
            block_reasons.append("Option premium budget is exhausted.")
        if int(demo_account.get("open_trade_slots") or 0) <= 0:
            block_reasons.append("Maximale Anzahl offener Demo-Trades erreicht.")
        if playbook.get("tradeable") is False:
            signal_reasons = [str(reason) for reason in playbook.get("do_not_trade_reasons", []) if str(reason).strip()]
            hard_signal_reasons = [
                reason for reason in signal_reasons if not reason.lower().startswith("score below minimum trade score")
            ]
            if hard_signal_reasons:
                block_reasons.extend([f"Signalregel: {reason}" for reason in hard_signal_reasons[:2]])
            elif signal_reasons:
                block_reasons.extend([f"Strict-Signalregel: {reason}" for reason in signal_reasons[:2]])
            else:
                block_reasons.append("Signalregel: Playbook hat kein freigegebenes Signal.")

        quantity_by_risk = risk_budget / risk_per_unit if risk_per_unit > 0 else 0
        quantity_by_position = max_position_value / (price * contract_multiplier) if price > 0 else 0
        quantity = max(0.0, min(quantity_by_risk, quantity_by_position))
        if is_option:
            quantity = float(int(quantity))
        if quantity < 0.0001:
            block_reasons.append("Vorgeschlagene Menge ist zu klein für das konfigurierte Risikobudget.")

        notional = quantity * price * contract_multiplier
        max_loss = quantity * risk_per_unit
        return {
            "suggested_quantity": round(quantity, 6),
            "suggested_notional_value": round(notional, 2),
            "suggested_max_loss_value": round(max_loss, 2),
            "suggested_account_pct": round((notional / float(demo_account.get("equity") or 1)) * 100, 2),
            "suggested_risk_pct": round((max_loss / float(demo_account.get("equity") or 1)) * 100, 2),
            "remaining_gross_capacity_value": round(remaining_gross, 2),
            "remaining_ticker_capacity_value": round(remaining_ticker_exposure, 2),
            "risk_multiplier": risk_multiplier,
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
        missing_journal = [
            trade
            for trade in closed
            if not str(trade.get("exit_reason") or "").strip()
            or not str(trade.get("lessons_learned") or "").strip()
        ]
        mistakes: Dict[str, int] = {}
        for trade in closed:
            if float(trade.get("realized_pnl_pct") or 0) >= 0:
                continue
            key = (trade.get("exit_reason") or trade.get("setup_type") or "unclassified").strip() or "unclassified"
            mistakes[key] = mistakes.get(key, 0) + 1
        option_wins = [trade for trade in option_closed if float(trade.get("realized_pnl_pct") or 0) > 0]
        journal_complete = len(missing_journal) == 0
        return {
            "closed_trades": len(closed),
            "option_closed_trades": len(option_closed),
            "option_win_rate": round((len(option_wins) / len(option_closed)) * 100, 1) if option_closed else 0,
            "journal_complete": journal_complete,
            "journal_completion_rate": round(((len(closed) - len(missing_journal)) / len(closed)) * 100, 1) if closed else 100.0,
            "missing_journal_count": len(missing_journal),
            "missing_journal_trades": [
                {
                    "id": trade.get("id"),
                    "ticker": trade.get("ticker"),
                    "setup_type": trade.get("setup_type"),
                    "result_value_delta": trade.get("result_value_delta"),
                    "realized_pnl_pct": trade.get("realized_pnl_pct"),
                }
                for trade in missing_journal[:5]
            ],
            "top_mistakes": [
                {"reason": reason, "count": count}
                for reason, count in sorted(mistakes.items(), key=lambda item: item[1], reverse=True)[:5]
            ],
            "next_rule": (
                f"{len(missing_journal)} fehlende Paper-Journale abschließen, bevor der Lernschleife vertraut wird."
                if missing_journal
                else
                "Keine Echtgeld-Calls oder -Puts, bis mindestens 20 Paper-Optionstrades wiederholbar positive Erwartung zeigen."
                if len(option_closed) < 20
                else "Options-Erwartung je Setup prüfen, bevor Demo-Risiko erhöht wird."
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
                    "missing_journal": 0,
                    "closed_trades": [],
                },
            )
            pnl = float(trade.get("realized_pnl_pct") or 0)
            bucket["trades"] += 1
            bucket["wins"] += 1 if pnl > 0 else 0
            bucket["avg_pnl_pct"] += pnl
            bucket["best_pnl_pct"] = pnl if bucket["best_pnl_pct"] is None else max(bucket["best_pnl_pct"], pnl)
            bucket["worst_pnl_pct"] = pnl if bucket["worst_pnl_pct"] is None else min(bucket["worst_pnl_pct"], pnl)
            bucket["closed_trades"].append(trade)
            if not str(trade.get("exit_reason") or "").strip() or not str(trade.get("lessons_learned") or "").strip():
                bucket["missing_journal"] += 1

        rows = []
        for bucket in buckets.values():
            performance = build_trade_performance(bucket.pop("closed_trades"))
            trades = max(1, int(bucket["trades"]))
            avg_pnl = round(float(bucket["avg_pnl_pct"]) / trades, 2)
            win_rate = round((int(bucket["wins"]) / trades) * 100, 1)
            missing_journal = int(bucket.get("missing_journal") or 0)
            journal_completion_rate = round(((trades - missing_journal) / trades) * 100, 1)
            if missing_journal:
                quality_status = "needs_journal"
                next_action = "Exit-Grund und Lektion vervollständigen, bevor diesem Setup vertraut wird."
            elif trades < 10:
                quality_status = "building_evidence"
                next_action = "Mindestens 10 geschlossene Paper-Trades sammeln; ab 30 wird die Stichprobe belastbarer."
            elif performance["expectancy_value"] > 0 and (performance["profit_factor"] or 0) >= 1.2:
                quality_status = "promising"
                next_action = "Positive Erwartung weiter per Paper testen; manuelle Prüfung frühestens ab belastbarer Stichprobe."
            elif performance["expectancy_value"] < 0 or (performance["profit_factor"] is not None and performance["profit_factor"] < 1):
                quality_status = "downgrade"
                next_action = "Score-Gewichtung senken und vor dem nächsten Einstieg stärkere Bestätigung verlangen."
            else:
                quality_status = "neutral"
                next_action = "Risiko unverändert lassen und auf klarere Beweise warten."
            rows.append(
                {
                    **bucket,
                    "avg_pnl_pct": avg_pnl,
                    "win_rate": win_rate,
                    "journal_completion_rate": journal_completion_rate,
                    "performance": performance,
                    "quality_status": quality_status,
                    "next_action": next_action,
                }
            )
        status_rank = {"promising": 0, "neutral": 1, "building_evidence": 2, "needs_journal": 3, "downgrade": 4}
        rows.sort(key=lambda item: (status_rank.get(item.get("quality_status"), 5), -item.get("win_rate", 0), -item.get("avg_pnl_pct", 0)))
        return rows

    def _build_entry_source_performance(self, closed_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for trade in closed_trades:
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            source = str(ticket.get("entry_source_label") or "Paper-Autopilot").strip() or "Paper-Autopilot"
            buckets.setdefault(source, []).append(trade)

        rows = []
        for source, trades in buckets.items():
            performance = build_trade_performance(trades)
            rows.append(
                {
                    "entry_source_label": source,
                    "trades": len(trades),
                    "performance": performance,
                    "summary": (
                        f"{source}: {performance.get('sample_size', 0)} geschlossene Paper-Trades, "
                        f"Treffer {performance.get('win_rate', 0)}%, "
                        f"Erwartung {performance.get('expectancy_value', 0)} pro Trade."
                    ),
                }
            )
        rows.sort(
            key=lambda item: (
                -float((item.get("performance") or {}).get("expectancy_value") or 0),
                -int(item.get("trades") or 0),
                str(item.get("entry_source_label") or ""),
            )
        )
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
                    "invested_value": trade.get("invested_value"),
                    "current_value": trade.get("current_value"),
                    "final_value": trade.get("final_value"),
                    "result_value_delta": trade.get("result_value_delta"),
                    "result_label": trade.get("result_label"),
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
        ticket = row.get("trade_ticket") if isinstance(row.get("trade_ticket"), dict) else {}
        execution_model = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        current_market = {} if is_option else self._get_market_snapshot(row.get("ticker"))
        current_reference = None if is_option else current_market.get("price")
        current_price = current_reference
        if current_reference not in (None, 0) and isinstance(execution_model.get("entry"), dict):
            current_execution = self._simulate_execution_fill(
                reference_price=float(current_reference),
                direction=str(row.get("direction") or "long"),
                phase="exit",
                asset_class=str(row.get("asset_class") or "equity"),
                market_data=current_market,
                quantity=quantity,
                contract_multiplier=float(row.get("contract_multiplier") or (100 if is_option else 1)),
            )
            current_price = current_execution["fill_price"]
            row["estimated_exit_execution"] = current_execution
        row["current_reference_price"] = current_reference
        row["current_price"] = current_price
        direction_multiplier = -1 if row.get("direction") == "short" else 1
        contract_multiplier = 100 if is_option else 1
        invested_value = round(entry * quantity * leverage * contract_multiplier, 2)
        row["invested_value"] = invested_value
        row["position_notional_value"] = invested_value

        if row.get("status") == "closed":
            exit_price = float(row.get("closed_price") or 0)
            pnl_pct = self._calc_return_pct(entry, exit_price, direction_multiplier, leverage)
            pnl_value = round(((exit_price - entry) * quantity * direction_multiplier * leverage * contract_multiplier), 2)
            row["realized_pnl_pct"] = pnl_pct
            row["realized_pnl_value"] = pnl_value
            row["unrealized_pnl_pct"] = None
            row["unrealized_pnl_value"] = None
            row["current_value"] = None
            row["final_value"] = round(invested_value + pnl_value, 2)
            row["result_value_delta"] = pnl_value
            row["result_label"] = "more" if pnl_value > 0 else "less" if pnl_value < 0 else "flat"
        else:
            pnl_pct = self._calc_return_pct(entry, current_price, direction_multiplier, leverage) if current_price else None
            pnl_value = (
                round(((current_price - entry) * quantity * direction_multiplier * leverage * contract_multiplier), 2)
                if current_price is not None
                else None
            )
            row["unrealized_pnl_pct"] = pnl_pct
            row["unrealized_pnl_value"] = pnl_value
            row["realized_pnl_pct"] = None
            row["realized_pnl_value"] = None
            row["current_value"] = round(invested_value + pnl_value, 2) if pnl_value is not None else None
            row["final_value"] = None
            row["result_value_delta"] = pnl_value
            row["result_label"] = "more" if (pnl_value or 0) > 0 else "less" if (pnl_value or 0) < 0 else "flat"

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
                "decision_grade": "wait",
                "next_check": "Auf verlässlichen aktuellen Kurs warten, bevor die Paper-Position geändert wird.",
                "summary": "Aktueller Kurs fehlt; Paper-Trade weiter prüfen.",
            }

        current_price = float(current)
        stop_price = float(stop) if stop not in (None, 0) else None
        target_price = float(target) if target not in (None, 0) else None
        favorable_pct = float(trade.get("unrealized_pnl_pct") or 0)
        risk_distance = None
        target_progress = None
        action = "hold"
        status = "monitor"
        summary = "Paper-Position halten, solange der Trigger gültig bleibt."

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
                    "decision_grade": "exit",
                    "next_check": "Schließen oder dokumentieren, warum der Stop nicht respektiert wird; nicht verbilligen.",
                    "summary": "Stop-Zone wurde erreicht oder gebrochen. Paper-Trade-Schließung prüfen und Lektion loggen.",
                    "risk_distance_pct": round(risk_distance, 2),
                    "target_progress_pct": None,
                }
            if risk_distance is not None and risk_distance <= 0.6:
                status = "near_stop"
                action = "reduce_or_close_review"
                summary = "Kurs ist nahe am Stop. Nicht aufstocken; Exit-Prüfung vorbereiten, falls Schwäche anhält."

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
                    "decision_grade": "exit",
                    "next_check": "Zieltreffer dokumentieren, schließen oder engeren Trailing-Plan festhalten.",
                    "summary": "Zielzone erreicht. Gewinnmitnahme oder Paper-Trade-Schließung prüfen.",
                    "risk_distance_pct": round(risk_distance, 2) if risk_distance is not None else None,
                    "target_progress_pct": round(target_progress, 1),
                }
            if target_progress >= 75 and favorable_pct > 0 and status == "monitor":
                status = "near_target"
                action = "protect_profit_review"
                summary = "Trade ist nahe am Ziel. Prüfen, ob Gewinn geschützt oder Paper-Plan enger geführt wird."

        if favorable_pct <= -1.5 and status == "monitor":
            status = "weak_follow_through"
            action = "thesis_check"
            summary = "Negative Anschlussbewegung. Prüfen, ob der ursprüngliche Trigger versagt."
        elif favorable_pct >= 1.5 and status == "monitor":
            status = "working"
            action = "hold_with_plan"
            summary = "Trade funktioniert. Nur halten, solange die Invalidierung nicht ausgelöst ist."

        decision_grade = "hold"
        next_check = "Geplanten Stop und Ziel halten; nach dem nächsten relevanten Kursupdate erneut prüfen."
        if status in {"near_stop", "weak_follow_through"}:
            decision_grade = "review"
            next_check = "Trigger-Qualität und Invalidierung erneut prüfen, bevor aufgestockt oder länger gehalten wird."
        elif status == "near_target":
            decision_grade = "protect"
            next_check = "Gewinnschutz prüfen; Gewinner nahe am Ziel nicht ungeprüft zum Verlierer werden lassen."
        elif status == "working":
            decision_grade = "hold"
            next_check = "Halten, solange der ursprüngliche Trigger gültig bleibt; keine Vergrößerung ohne neues Setup."

        return {
            "status": status,
            "action": action,
            "decision_grade": decision_grade,
            "next_check": next_check,
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
                blocked.append(f"Politisches Delay-Setup braucht stärkere Bestätigung über {min_trade_score + 2:.0f}.")
        if playbook.get("asset_class") == "crypto" and playbook.get("direction") == "short":
            blocked.append("Crypto-Short-Playbooks sind im aktuellen Modell deaktiviert.")
        if playbook.get("asset_class") == "crypto" and bool(rules.get("block_crypto_leverage", True)):
            leverage_rules.append("Crypto-Hebel ist im aktuellen Regelwerk geblockt.")
        if score < min_leverage_score:
            leverage_rules.append(f"Kein Hebel unter Score {min_leverage_score:.0f} erlaubt.")
        if playbook.get("learning_blocked"):
            blocked.append("Paper-Ergebnisse blockieren dieses Setup, bis die Resultate besser werden.")
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

    def _market_reference_fields(self, ticker: Optional[str]) -> Dict[str, Any]:
        snapshot = self._get_market_snapshot(ticker)
        return {
            "reference_price": snapshot.get("price"),
            "data_as_of": snapshot.get("data_as_of"),
            "market_data": snapshot,
        }

    def _execution_cost_bps(self, asset_class: str, market_data: Dict[str, Any] | None = None) -> float:
        asset = str(asset_class or "equity").lower()
        market_data = market_data if isinstance(market_data, dict) else {}
        defaults = {
            "equity": 8.0,
            "etf": 6.0,
            "crypto": 18.0,
            "option": 125.0,
        }
        env_names = {
            "equity": "PAPER_EXECUTION_EQUITY_BPS",
            "etf": "PAPER_EXECUTION_ETF_BPS",
            "crypto": "PAPER_EXECUTION_CRYPTO_BPS",
            "option": "PAPER_EXECUTION_OPTION_BPS",
        }
        try:
            base_bps = float(os.getenv(env_names.get(asset, "PAPER_EXECUTION_EQUITY_BPS"), str(defaults.get(asset, 12.0))))
        except (TypeError, ValueError):
            base_bps = defaults.get(asset, 12.0)
        liquidity_multiplier = {
            "strong": 1.0,
            "adequate": 1.75,
            "unknown": 2.5,
            "thin": 4.0,
        }.get(str(market_data.get("liquidity_status") or "unknown").lower(), 2.5)
        age_hours = float(market_data.get("age_hours") or 0)
        stale_surcharge = 5.0 if age_hours > 24 else 0.0
        return round(min(500.0, max(0.0, base_bps * liquidity_multiplier + stale_surcharge)), 2)

    def _simulate_execution_fill(
        self,
        reference_price: float,
        direction: str,
        phase: str,
        asset_class: str,
        market_data: Dict[str, Any] | None = None,
        quantity: float = 0,
        contract_multiplier: float = 1,
    ) -> Dict[str, Any]:
        reference = float(reference_price or 0)
        if reference <= 0:
            raise ValueError("Execution model requires a positive reference price.")
        normalized_direction = str(direction or "long").lower()
        normalized_phase = "exit" if str(phase or "entry").lower() == "exit" else "entry"
        # Calls and puts in this paper model are long-premium positions.
        opens_with_buy = normalized_direction in {"long", "call", "put"}
        is_buy = opens_with_buy if normalized_phase == "entry" else not opens_with_buy
        cost_bps = self._execution_cost_bps(asset_class, market_data)
        adjustment = cost_bps / 10_000
        fill_price = reference * (1 + adjustment if is_buy else 1 - adjustment)
        fill_price = round(max(0.0001, fill_price), 4)
        cost_per_unit = abs(fill_price - reference)
        estimated_cost_value = cost_per_unit * max(0.0, float(quantity or 0)) * max(1.0, float(contract_multiplier or 1))
        return {
            "phase": normalized_phase,
            "side": "buy" if is_buy else "sell",
            "pricing_mode": "conservative_reference_plus_cost",
            "reference_price": round(reference, 4),
            "fill_price": fill_price,
            "cost_bps": cost_bps,
            "cost_per_unit": round(cost_per_unit, 6),
            "estimated_cost_value": round(estimated_cost_value, 2),
            "liquidity_status": (market_data or {}).get("liquidity_status") or "unknown",
            "data_as_of": (market_data or {}).get("data_as_of"),
            "policy": "Paper estimate only; no broker fill or live order-book guarantee.",
        }

    def _market_snapshot_blockers(self, snapshot: Dict[str, Any] | None) -> List[str]:
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        if not snapshot:
            return ["market_snapshot_missing"]
        blockers: List[str] = []
        if float(snapshot.get("price") or 0) <= 0:
            blockers.append("market_price_missing")
        if not snapshot.get("data_as_of"):
            blockers.append("market_data_timestamp_missing")
        if snapshot.get("freshness") == "stale":
            blockers.append("market_data_stale")
        if snapshot.get("liquidity_status") == "thin":
            blockers.append("market_liquidity_too_thin")
        return self._dedupe_reason_list(blockers)

    def _get_market_snapshot(self, ticker: Optional[str]) -> Dict[str, Any]:
        if not ticker:
            return {}
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d")
            if hist.empty:
                return {}
            close = hist["Close"].dropna()
            if close.empty:
                return {}
            price = round(float(close.iloc[-1]), 4)
            timestamp = close.index[-1]
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if not isinstance(timestamp, datetime):
                return {}
            now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
            age_hours = max(0.0, (now - timestamp).total_seconds() / 3600)
            max_age_hours = max(24.0, float(os.getenv("PAPER_MARKET_DATA_MAX_AGE_HOURS", "96")))

            volume_values = hist["Volume"].dropna() if "Volume" in hist else []
            average_volume = float(volume_values.tail(5).mean()) if len(volume_values) else None
            is_crypto_pair = str(ticker).upper().endswith("-USD")
            dollar_volume = (
                average_volume
                if is_crypto_pair and average_volume is not None
                else average_volume * price
                if average_volume is not None
                else None
            )
            min_dollar_volume = max(
                100_000.0,
                float(os.getenv("PAPER_MIN_AVG_DOLLAR_VOLUME", "2000000")),
            )
            liquidity_status = (
                "unknown"
                if dollar_volume is None or dollar_volume <= 0
                else "thin"
                if dollar_volume < min_dollar_volume
                else "strong"
                if dollar_volume >= min_dollar_volume * 5
                else "adequate"
            )
            return {
                "price": price,
                "data_as_of": timestamp.isoformat(),
                "source": "yfinance_daily",
                "interval": "1d",
                "age_hours": round(age_hours, 2),
                "freshness": "fresh" if age_hours <= max_age_hours else "stale",
                "average_volume_5d": round(average_volume, 2) if average_volume is not None else None,
                "average_dollar_volume_5d": round(dollar_volume, 2) if dollar_volume is not None else None,
                "volume_basis": "reported_quote_volume" if is_crypto_pair else "shares_times_price",
                "liquidity_status": liquidity_status,
                "minimum_dollar_volume": min_dollar_volume,
            }
        except Exception:
            return {}

    def _get_last_price(self, ticker: Optional[str]) -> Optional[float]:
        return self._get_market_snapshot(ticker).get("price")

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
