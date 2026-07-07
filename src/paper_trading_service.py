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
        blocker_summary = selection.get("blocker_summary") if isinstance(selection.get("blocker_summary"), dict) else {}
        no_trade_message = self._auto_selection_no_trade_message(mode, blocker_summary)
        preview_message = (
            no_trade_message
            if not selected
            else f"{len(selected)} Learning-Kandidaten erfüllen die Exploration-Gates."
            if mode == "learn"
            else f"{len(selected)} Demo-Kandidaten erfüllen die Auto-Selection-Gates."
        )
        if not execute:
            return {
                "status": "preview",
                "execute": False,
                "mode": mode,
                "selected": selected,
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
        execution_message = (
            no_trade_message
            if not selected and not opened
            else f"{len(opened)} Paper-Learning-Trades eröffnet; {len(errors)} im finalen Gate geblockt."
            if mode == "learn"
            else f"{len(opened)} Paper-Trades eröffnet; {len(errors)} im finalen Gate geblockt."
        )
        return {
            "status": "ok" if not errors else "partial",
            "execute": True,
            "mode": mode,
            "selected": selected,
            "opened": opened,
            "errors": errors,
            "rejected_count": selection.get("rejected_count"),
            "blocker_summary": blocker_summary,
            "message": execution_message,
        }

    def _auto_selection_no_trade_message(self, mode: str, blocker_summary: Dict[str, Any]) -> str:
        label = "Learning" if mode == "learn" else "Strict"
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
        if "open risk budget is exhausted" in lower:
            return "offenes Risikobudget ausgeschöpft"
        if "open-trade slots exhausted" in lower or "maximum demo open trades reached" in lower:
            return "maximale Anzahl offener Demo-Trades erreicht"
        if "missing ticker or reference price" in lower:
            return "Ticker oder Referenzkurs fehlt"
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
        return text

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
        auto_outcome = self._classify_closed_trade_outcome(existing, exit_price)
        if not exit_reason and auto_outcome.get("exit_reason"):
            exit_reason = auto_outcome["exit_reason"]
        if not lessons_learned and auto_outcome.get("lesson"):
            lessons_learned = auto_outcome["lesson"]
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
            "Entscheidungs-Snapshot beim Paper-Einstieg:",
            f"Headline: {playbook.get('headline') or 'n/a'}",
            f"Setup: {playbook.get('setup_type') or 'signal_playbook'} / {playbook.get('asset_class') or 'equity'} / {playbook.get('direction') or 'long'}",
            f"Score: {playbook.get('score')}; Beweisniveau: {framework.get('evidence_level') or 'watch'}",
            f"Demo-Größe: vorgeschlagene Menge {playbook.get('suggested_quantity')}; max. Verlust {playbook.get('suggested_max_loss_value')} {demo_account.get('currency')}.",
            f"Trigger: {framework.get('entry_trigger') or 'Manuelle Trigger-Prüfung erforderlich.'}",
            f"Invalidierung: {framework.get('invalidation') or 'Manuelle Invalidierungsprüfung erforderlich.'}",
            f"Risikoplan: {framework.get('risk_plan') or 'Nur Paper-Risiko.'}",
        ]
        if playbook.get("learning_mode"):
            lines.append("Lernmodus: reduzierte Demo-Position, kein strenges Top-Setup und nicht Echtgeld-bereit.")
        if is_option:
            lines.append("Options-Gate: nur Paper-Premienmodell; Strike, Laufzeit, Spread, IV und maximalen Prämienverlust manuell prüfen.")
        for question in checklist[:3]:
            lines.append(f"Prüffrage: {question}")
        lines.append(framework.get("real_money_policy") or "Nur Entscheidungsrahmen; keine automatische Echtgeld-Ausführung.")
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
            rule_reasons = [str(item) for item in playbook.get("do_not_trade_reasons", [])]
            if score < min_score:
                reasons.append(f"score below auto minimum {min_score:.0f}")
            if score < exploration_min_score:
                exploration_reasons.append(f"score below learning minimum {exploration_min_score:.0f}")
            if playbook.get("tradeable") is False:
                reasons.extend(rule_reasons[:3] or ["trade signal rules blocked this playbook"])
            if playbook.get("demo_tradeable") is False and not playbook.get("demo_block_reasons"):
                reasons.append("demo risk gate blocked")
            if hard_rule_reasons:
                exploration_reasons.extend(hard_rule_reasons[:3])
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
                    reasons.append("Option bleibt Paper-only und braucht manuelle Optionskettenprüfung")
                    exploration_reasons.append("Optionskette muss vor Exploration manuell geprüft werden")
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
                "reasons": self._dedupe_reason_list(reasons),
            }
            row["display_reasons"] = [self._auto_rejection_display_reason(reason) for reason in row["reasons"]]
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
            "rejected_count": len(rejected),
            "blocker_summary": self._summarize_auto_rejections(rejected),
            "policy": "Paper-only Auto-Auswahl. Strict-Modus priorisiert Qualität; Lernmodus nutzt kleineres Demo-Risiko zum Sammeln von Beweisen.",
        }

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
                "reasons": next_best_reasons,
                "display_reasons": (
                    next_best.get("display_reasons")
                    or [self._auto_rejection_display_reason(reason) for reason in (next_best.get("reasons") or [])]
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
        if "risk review" in lower or "exit actions open" in lower:
            return "risk_review"
        if "open risk budget is exhausted" in lower or "open-trade slots exhausted" in lower or "maximum demo open trades" in lower:
            return "capacity"
        if "same ticker/setup/direction already open" in lower:
            return "duplicate"
        if "score below" in lower:
            return "score"
        if "missing ticker or reference price" in lower:
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
            "capacity": "Risiko/Slots voll",
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
        if "risk review" in text or "exit actions open" in text:
            return "Offene Trades pruefen und Risk-Review beenden"
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
        if "risk review" in text or "exit actions open" in text:
            return "Erst offene Paper-Trades prüfen, Stop/Target bestätigen und Risk-Review abschließen."
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
        closed_trades = [trade for trade in trades if trade.get("status") == "closed"]
        open_risk_value = round(sum(self._trade_open_risk_value(trade) for trade in open_trades), 2)
        open_exposure_value = round(
            sum(float(trade.get("invested_value") or 0) for trade in open_trades),
            2,
        )
        net_pnl_value = round(realized_value + unrealized_value, 2)
        net_pnl_pct = round((net_pnl_value / starting_capital) * 100, 2) if starting_capital > 0 else 0
        cash_available_value = round(max(0.0, equity - open_exposure_value), 2)
        capital_status = "ahead" if net_pnl_value > 0 else "behind" if net_pnl_value < 0 else "flat"
        management_counts: Dict[str, int] = {}
        for trade in open_trades:
            grade = str((trade.get("management_plan") or {}).get("decision_grade") or "hold")
            management_counts[grade] = management_counts.get(grade, 0) + 1
        if management_counts.get("exit"):
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
        max_option_premium_value = round(equity * (float(config["max_option_premium_pct"]) / 100), 2)
        option_risk_budget = round(equity * (float(config["risk_per_option_trade_pct"]) / 100), 2)
        remaining_risk = round(max(0.0, max_open_risk_value - open_risk_value), 2)
        return {
            **config,
            "equity": equity,
            "realized_pnl_value": round(realized_value, 2),
            "unrealized_pnl_value": round(unrealized_value, 2),
            "net_pnl_value": net_pnl_value,
            "net_pnl_pct": net_pnl_pct,
            "cash_available_value": cash_available_value,
            "capital_status": capital_status,
            "open_risk_value": open_risk_value,
            "open_risk_pct": round((open_risk_value / equity) * 100, 2) if equity > 0 else 0,
            "open_exposure_value": open_exposure_value,
            "open_exposure_pct": round((open_exposure_value / equity) * 100, 2) if equity > 0 else 0,
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
            "max_option_premium_value": max_option_premium_value,
            "open_trade_slots": max(0, int(config["max_open_trades"]) - len(open_trades)),
            "candidate_count": len(playbooks),
            "guardrails": [
                "Nur Demo-Lernkonto; keine automatische Echtgeld-Ausführung.",
                "Jede Idee braucht These, Trigger, Stop, Ziel und Nachtrade-Journal.",
                "Calls und Puts bleiben Paper-only, bis Optionskette, IV, Strike, Laufzeit und Spread geprüft sind.",
                "Echtgeld-Nutzung erfordert manuelle Prüfung, Suitability-Check und aktuelle Marktvalidierung.",
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
        day_status = str(demo_account.get("day_status") or "")
        learning_feedback = demo_account.get("learning_feedback")
        if not isinstance(learning_feedback, dict):
            learning_feedback = {}
        missing_journal_count = int(learning_feedback.get("missing_journal_count") or 0)

        if price <= 0:
            block_reasons.append("Keine Preisreferenz für Demo-Größe.")
        if day_status == "action_required":
            block_reasons.append("Paper-Konto hat offene Exit-Aktionen; bestehende Trades vor neuer Exposure prüfen.")
        elif day_status == "risk_review":
            block_reasons.append("Paper-Konto ist im Risiko-Review; schwache oder stop-nahe Trades zuerst prüfen.")
        if missing_journal_count > 0:
            block_reasons.append(
                f"{missing_journal_count} fehlende Paper-Journale abschließen, bevor neue Exposure hinzukommt."
            )
        if risk_budget <= 0:
            block_reasons.append("Offenes Risikobudget ist ausgeschöpft.")
        if int(demo_account.get("open_trade_slots") or 0) <= 0:
            block_reasons.append("Maximale Anzahl offener Demo-Trades erreicht.")
        if playbook.get("tradeable") is False:
            block_reasons.append("Playbook ist durch Signalregeln geblockt.")

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
                },
            )
            pnl = float(trade.get("realized_pnl_pct") or 0)
            bucket["trades"] += 1
            bucket["wins"] += 1 if pnl > 0 else 0
            bucket["avg_pnl_pct"] += pnl
            bucket["best_pnl_pct"] = pnl if bucket["best_pnl_pct"] is None else max(bucket["best_pnl_pct"], pnl)
            bucket["worst_pnl_pct"] = pnl if bucket["worst_pnl_pct"] is None else min(bucket["worst_pnl_pct"], pnl)
            if not str(trade.get("exit_reason") or "").strip() or not str(trade.get("lessons_learned") or "").strip():
                bucket["missing_journal"] += 1

        rows = []
        for bucket in buckets.values():
            trades = max(1, int(bucket["trades"]))
            avg_pnl = round(float(bucket["avg_pnl_pct"]) / trades, 2)
            win_rate = round((int(bucket["wins"]) / trades) * 100, 1)
            missing_journal = int(bucket.get("missing_journal") or 0)
            journal_completion_rate = round(((trades - missing_journal) / trades) * 100, 1)
            if missing_journal:
                quality_status = "needs_journal"
                next_action = "Exit-Grund und Lektion vervollständigen, bevor diesem Setup vertraut wird."
            elif trades < 5:
                quality_status = "building_evidence"
                next_action = "Mindestens 5 geschlossene Paper-Trades sammeln, bevor Risiko verändert wird."
            elif win_rate >= 55 and avg_pnl > 0:
                quality_status = "promising"
                next_action = "Weiter per Paper testen; höhere Demo-Priorität erst nach wiederholt sauberen Journalen prüfen."
            elif win_rate < 45 or avg_pnl < 0:
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
                    "quality_status": quality_status,
                    "next_action": next_action,
                }
            )
        status_rank = {"promising": 0, "neutral": 1, "building_evidence": 2, "needs_journal": 3, "downgrade": 4}
        rows.sort(key=lambda item: (status_rank.get(item.get("quality_status"), 5), -item.get("win_rate", 0), -item.get("avg_pnl_pct", 0)))
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
        current_price = None if is_option else self._get_last_price(row.get("ticker"))
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
