from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import yfinance as yf

from src.storage import PortfolioManager

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
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "playbooks": self._attach_demo_sizing(playbooks, demo_account),
            "open_trades": open_trades[:12],
            "closed_trades": closed_trades[:12],
            "stats": self._build_stats(trades),
            "setup_performance": self._build_setup_performance(closed_trades),
            "journal": self._build_journal(trades),
            "outcomes": self._build_outcome_dashboard(),
            "outcome_learning": outcome_learning,
            "rules": rules,
            "demo_account": demo_account,
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
        if playbook.get("do_not_trade_reasons"):
            raise ValueError("Playbook is blocked by do-not-trade rules.")
        if playbook.get("demo_block_reasons"):
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
                "notes": (
                    f"Demo account idea. Suggested qty {playbook.get('suggested_quantity')}; "
                    f"risk {playbook.get('suggested_max_loss_value')} {demo_account.get('currency')}. "
                    f"{'Paper option premium model. ' if is_option else ''}"
                    f"{playbook.get('headline') or ''}"
                ).strip(),
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
            rule_state = self._get_do_not_trade_state(item, rules)
            item["do_not_trade_reasons"] = rule_state["blocked"]
            item["leverage_warnings"] = rule_state["leverage"]
            item["tradeable"] = len(rule_state["blocked"]) == 0

        return sorted(playbooks, key=lambda item: float(item.get("score") or 0), reverse=True)[:10]

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

        return {
            "setup_adjustments": setup_adjustments,
            "option_readiness": {
                "decisive": option_decisive,
                "hit_rate": option_hit_rate,
                "real_money_ready": option_decisive >= 20 and option_hit_rate >= 55,
                "reason": (
                    "Options remain paper-only until 20 decisive checks and >=55% hit rate."
                    if option_decisive < 20 or option_hit_rate < 55
                    else "Options have enough paper evidence for manual review, not automatic execution."
                ),
            },
            "top_error_tags": [
                {"error_tag": key, "count": count}
                for key, count in sorted(by_error.items(), key=lambda item: item[1], reverse=True)[:6]
            ],
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
        return {
            "starting_capital": 50_000.0,
            "currency": "EUR",
            "risk_per_trade_pct": 0.5,
            "max_open_risk_pct": 4.0,
            "max_position_pct": 12.0,
            "max_option_premium_pct": 1.0,
            "risk_per_option_trade_pct": 0.5,
            "max_open_trades": 10,
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
        return row

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
