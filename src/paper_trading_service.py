from __future__ import annotations

import os
import json
import ipaddress
import re
import socket
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
import yfinance as yf

from src.storage import PortfolioManager
from src.strategy_library import StrategyLibrary
from src.performance_metrics import build_trade_performance

DEFAULT_PAPER_OUTCOME_HORIZONS_HOURS = (1, 24, 72, 168)


class PaperTradeAlreadyClosedError(ValueError):
    pass


COMMODITY_LEVERAGE_PROXIES = [
    {
        "ticker": "GLD",
        "label": "Gold",
        "theme": "gold_safe_haven",
        "call_headline": "Gold CALL: falling real yields, a softer dollar or risk-off demand must confirm",
        "put_headline": "Gold PUT: rising real yields, a firmer dollar and failed safe-haven demand must confirm",
        "call_thesis": "Gold should benefit only if real yields fall, the US dollar weakens or verified risk-off demand persists.",
        "put_thesis": "Gold should weaken only if real yields rise, the US dollar strengthens and safe-haven demand fails.",
        "call_confirmation": "GLD must hold above the reaction high while gold spot/futures and volume confirm the upside move.",
        "put_confirmation": "GLD must remain below the reaction low while gold spot/futures and volume confirm the downside move.",
        "call_invalidation": "The CALL case fails if real yields or the dollar reverse higher and GLD loses the confirmed breakout zone.",
        "put_invalidation": "The PUT case fails if real yields or the dollar reverse lower and GLD reclaims the confirmed breakdown zone.",
        "event_drivers": ["US real yields", "US dollar", "inflation data", "central-bank guidance", "risk-off flows"],
        "score": 84,
    },
    {
        "ticker": "USO",
        "label": "Oil",
        "theme": "oil_supply_demand",
        "call_headline": "Oil CALL: verified supply tightening must beat demand concerns",
        "put_headline": "Oil PUT: demand weakness or verified supply growth must break support",
        "call_thesis": "Oil should rise only if a verified supply disruption, inventory draw or OPEC restraint is confirmed by the futures curve.",
        "put_thesis": "Oil should fall only if demand weakens, inventories build or verified supply growth is confirmed by the futures curve.",
        "call_confirmation": "USO and front-month crude must hold the reaction high with supportive volume and no immediate headline reversal.",
        "put_confirmation": "USO and front-month crude must remain below the reaction low with supportive volume and no immediate headline reversal.",
        "call_invalidation": "The CALL case fails if the supply headline is reversed, inventories contradict it or crude loses the reaction low.",
        "put_invalidation": "The PUT case fails if the demand/supply evidence improves or crude reclaims the reaction high.",
        "event_drivers": ["OPEC decisions", "inventory data", "supply disruptions", "futures curve", "global demand"],
        "score": 82,
    },
    {
        "ticker": "XLE",
        "label": "Energy equities",
        "theme": "energy_equity_beta",
        "call_headline": "Energy CALL: oil strength, margins and sector breadth must align",
        "put_headline": "Energy PUT: oil weakness and deteriorating sector breadth must align",
        "call_thesis": "Energy equities should outperform only if oil strength, refining/upstream margins and broad participation across XLE holdings align.",
        "put_thesis": "Energy equities should underperform only if oil weakens and sector breadth, margins or earnings expectations deteriorate.",
        "call_confirmation": "XLE must outperform the broad market and hold the reaction high with participation beyond one large constituent.",
        "put_confirmation": "XLE must underperform the broad market and remain below the reaction low with broad constituent weakness.",
        "call_invalidation": "The CALL case fails if crude reverses, sector breadth narrows or XLE loses relative strength versus the broad market.",
        "put_invalidation": "The PUT case fails if crude and margins recover or XLE regains relative strength versus the broad market.",
        "event_drivers": ["crude prices", "refining margins", "earnings revisions", "sector breadth", "relative strength"],
        "score": 80,
    },
]


class PaperTradingService:
    def __init__(self, portfolio_manager: PortfolioManager) -> None:
        self.portfolio_manager = portfolio_manager
        self._correlation_cache: Dict[str, Any] = {}

    @staticmethod
    def _is_safe_public_news_url(url: str) -> bool:
        try:
            parsed = urlparse(str(url or "").strip())
            hostname = (parsed.hostname or "").strip().lower()
            if parsed.scheme not in {"http", "https"} or not hostname:
                return False
            if hostname == "localhost" or hostname.endswith((".local", ".internal")):
                return False
            addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])
                if not ip.is_global:
                    return False
            return bool(addresses)
        except (OSError, ValueError):
            return False

    def _fetch_news_source_status(self, url: str) -> Dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        current_url = str(url or "").strip()
        if not self._is_safe_public_news_url(current_url):
            return {
                "url": current_url,
                "status": "unsafe_or_unresolvable_url",
                "checked_at": checked_at,
                "actionable": False,
            }
        try:
            for _ in range(4):
                response = requests.get(
                    current_url,
                    headers={"User-Agent": "BrokerFreund-NewsEvidenceMonitor/1.0"},
                    timeout=12,
                    stream=True,
                    allow_redirects=False,
                )
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = urljoin(current_url, response.headers.get("Location") or "")
                    response.close()
                    if not self._is_safe_public_news_url(target):
                        return {
                            "url": str(url),
                            "final_url": target,
                            "status": "unsafe_redirect",
                            "checked_at": checked_at,
                            "actionable": False,
                        }
                    current_url = target
                    continue
                status_code = int(response.status_code)
                if status_code in {404, 410}:
                    response.close()
                    return {
                        "url": str(url),
                        "final_url": current_url,
                        "http_status": status_code,
                        "status": "source_unavailable",
                        "checked_at": checked_at,
                        "actionable": True,
                    }
                if status_code >= 400:
                    response.close()
                    return {
                        "url": str(url),
                        "final_url": current_url,
                        "http_status": status_code,
                        "status": "access_blocked" if status_code in {401, 403, 429} else "check_failed",
                        "checked_at": checked_at,
                        "actionable": False,
                    }
                body = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    body.extend(chunk)
                    if len(body) >= 262144:
                        break
                encoding = response.encoding or "utf-8"
                response.close()
                text = bytes(body[:262144]).decode(encoding, errors="replace")
                visible = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
                visible = re.sub(r"<[^>]+>", " ", visible)
                visible = re.sub(r"\s+", " ", visible).strip().lower()[:50000]
                withdrawn = re.search(
                    r"\b(retracted|retraction|story withdrawn|report withdrawn|withdrawn report|zur(?:ue|ü)ckgezogen|widerrufen)\b",
                    visible,
                )
                corrected = re.search(
                    r"\b(correction|corrected version|corrects?\b|korrigiert|korrektur|berichtigt)\b",
                    visible,
                )
                status = "retracted_or_withdrawn" if withdrawn else "correction_detected" if corrected else "unchanged"
                signal = withdrawn.group(0) if withdrawn else corrected.group(0) if corrected else None
                return {
                    "url": str(url),
                    "final_url": current_url,
                    "http_status": status_code,
                    "status": status,
                    "signal": signal,
                    "checked_at": checked_at,
                    "actionable": status in {"retracted_or_withdrawn", "correction_detected"},
                }
            return {
                "url": str(url),
                "final_url": current_url,
                "status": "redirect_limit",
                "checked_at": checked_at,
                "actionable": False,
            }
        except requests.RequestException as exc:
            return {
                "url": str(url),
                "final_url": current_url,
                "status": "check_failed",
                "error_type": type(exc).__name__,
                "checked_at": checked_at,
                "actionable": False,
            }

    def revalidate_open_news_sources(self, limit: int = 50) -> Dict[str, Any]:
        trades = self.portfolio_manager.list_paper_trades(status="open", limit=limit)
        checked: List[Dict[str, Any]] = []
        skipped = 0
        priority = {
            "retracted_or_withdrawn": 5,
            "correction_detected": 4,
            "source_unavailable": 3,
            "unchanged": 1,
        }
        for trade in trades:
            if str(trade.get("setup_type") or "") != "confirmed_news_event":
                skipped += 1
                continue
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            evidence = ticket.get("news_evidence") if isinstance(ticket.get("news_evidence"), dict) else {}
            sources: List[Dict[str, str]] = []
            reporting = evidence.get("reporting_source") if isinstance(evidence.get("reporting_source"), dict) else {}
            primary = evidence.get("primary_source") if isinstance(evidence.get("primary_source"), dict) else {}
            for source_type, source_url in (
                ("reporting_source", reporting.get("url") or evidence.get("source_url")),
                ("primary_source", primary.get("url")),
            ):
                normalized = str(source_url or "").strip()
                if normalized and normalized not in {item["url"] for item in sources}:
                    sources.append({"source_type": source_type, "url": normalized})
            if not sources:
                skipped += 1
                continue
            checks = []
            for source in sources:
                result = self._fetch_news_source_status(source["url"])
                checks.append({**result, "source_type": source["source_type"]})
            actionable = [item for item in checks if item.get("actionable")]
            if actionable:
                selected = max(actionable, key=lambda item: priority.get(str(item.get("status")), 0))
            elif checks and all(item.get("status") == "unchanged" for item in checks):
                selected = {"status": "unchanged", "actionable": False}
            else:
                selected = {"status": "check_failed", "actionable": False}
            prior = evidence.get("correction_status") if isinstance(evidence.get("correction_status"), dict) else {}
            prior_status = str(prior.get("status") or "")
            if (
                not selected.get("actionable")
                and prior_status in {"retracted_or_withdrawn", "correction_detected", "source_unavailable"}
            ):
                selected = {"status": prior_status, "actionable": True, "latched": True}
            checked_at = datetime.now(timezone.utc).isoformat()
            history = list(prior.get("history") or [])
            if prior_status and prior_status != selected["status"]:
                history.append({"status": prior_status, "checked_at": prior.get("checked_at")})
            correction_status = {
                **prior,
                "status": selected["status"],
                "checked_at": checked_at,
                "checks": checks,
                "signals": [item.get("signal") for item in checks if item.get("signal")],
                "monitoring_scope": "stored_reporting_and_primary_source_urls",
                "ongoing_monitor_verified": all(
                    item.get("status") not in {"check_failed", "access_blocked", "unsafe_redirect", "unsafe_or_unresolvable_url", "redirect_limit"}
                    for item in checks
                ),
                "actionable": bool(selected.get("actionable")),
                "latched_for_manual_review": bool(selected.get("latched")),
                "history": history[-8:],
            }
            updated_ticket = {
                **ticket,
                "news_evidence": {**evidence, "correction_status": correction_status},
                "news_source_revalidation": {
                    "status": selected["status"],
                    "actionable": bool(selected.get("actionable")),
                    "checked_at": checked_at,
                },
            }
            persisted = self.portfolio_manager.update_paper_trade_ticket(str(trade.get("id")), updated_ticket)
            checked.append(
                {
                    "id": trade.get("id"),
                    "ticker": trade.get("ticker"),
                    "status": selected["status"],
                    "actionable": bool(selected.get("actionable")),
                    "persisted": bool(persisted),
                    "checks": checks,
                }
            )
        return {
            "status": "ok",
            "checked": len(checked),
            "actionable": sum(1 for item in checked if item["actionable"]),
            "skipped": skipped,
            "trades": checked,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def build_dashboard(
        self,
        scoreboard: Dict[str, Any],
        settings: Dict[str, Any] | None = None,
        news_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        settings = settings or {}
        rules = settings.get("do_not_trade") or {}
        outcome_learning = self._build_outcome_learning_adjustments()
        trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(limit=150))
        open_trades = [trade for trade in trades if trade.get("status") == "open"]
        closed_trades = [trade for trade in trades if trade.get("status") == "closed"]
        news_evidence_performance = self._build_news_evidence_performance(closed_trades)
        news_shadow_lab = self._build_news_shadow_lab()
        playbooks = self._build_playbooks(scoreboard, rules, outcome_learning, news_context)
        self._apply_news_evidence_learning(playbooks, news_evidence_performance)
        self._apply_news_shadow_learning(playbooks, news_shadow_lab)
        self._refresh_playbook_decision_state(playbooks, rules)
        demo_account = self._build_demo_account(trades, playbooks)
        self._attach_quantitative_correlation(playbooks, open_trades, demo_account)
        sized_playbooks = self._attach_demo_sizing(playbooks, demo_account, rules)
        autopilot_settings = self.portfolio_manager.get_paper_autopilot_settings()
        autopilot_profile = self._build_autopilot_profile_summary(autopilot_settings, demo_account)
        strategy_readiness = StrategyLibrary.build_readiness(
            trades,
            self.portfolio_manager.list_paper_trade_outcomes(limit=800),
        )
        auto_selection = self._build_auto_selection(
            sized_playbooks,
            trades,
            demo_account,
            strategy_readiness,
            autopilot_settings=autopilot_settings,
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
            "news_evidence_performance": news_evidence_performance,
            "news_shadow_lab": news_shadow_lab,
            "learning_context_performance": self._build_learning_context_performance(closed_trades),
            "market_regime_performance": self._build_market_regime_performance(closed_trades),
            "strategy_dimension_performance": self._build_strategy_dimension_performance(closed_trades),
            "current_entry_market_regime": self._build_entry_market_regime(news_context or {}),
            "journal": self._build_journal(trades),
            "outcomes": self._build_outcome_dashboard(),
            "outcome_learning": outcome_learning,
            "rules": rules,
            "demo_account": demo_account,
            "paper_autopilot_settings": autopilot_settings,
            "paper_autopilot_profile": autopilot_profile,
            "news_gate_monitor": self._build_news_gate_monitor(
                news_context or {},
                demo_account,
                sized_playbooks,
                auto_selection,
            ),
            "auto_selection": auto_selection,
            "auto_learn_status": self._build_auto_learn_status(),
        }

    def _build_autopilot_profile_summary(
        self,
        autopilot_settings: Dict[str, Any],
        demo_account: Dict[str, Any],
    ) -> Dict[str, Any]:
        mode = str(autopilot_settings.get("mode") or "aggressive_learning")
        max_trades = max(1, min(8, int(float(autopilot_settings.get("max_trades") or 5))))
        learning_risk = max(0.03, min(0.35, float(autopilot_settings.get("learning_risk_multiplier") or 0.25)))
        aggressive_risk = max(
            learning_risk,
            min(0.65, float(autopilot_settings.get("aggressive_risk_multiplier") or 0.60)),
        )
        risk_budget = float(demo_account.get("risk_budget_per_trade_value") or 0)
        strict_score = float(autopilot_settings.get("strict_min_score") or 88)
        learning_score = float(autopilot_settings.get("learning_min_score") or 60)
        aggressive_score = float(autopilot_settings.get("aggressive_min_score") or 52)
        mode_map = {
            "strict": {
                "label": "Strict",
                "min_score": strict_score,
                "risk_multiplier": 1.0,
                "tone": "quality",
                "description": "Nur sehr starke Paper-Setups. Weniger Trades, hoehere Datenqualität.",
            },
            "learn": {
                "label": "Learn",
                "min_score": learning_score,
                "risk_multiplier": learning_risk,
                "tone": "balanced",
                "description": "Mehr kleine Tests, um schneller belastbare Beweise zu sammeln.",
            },
            "aggressive_learning": {
                "label": "Aggressive Learning",
                "min_score": aggressive_score,
                "risk_multiplier": aggressive_risk,
                "tone": "aggressive",
                "description": "Schneller lernen mit mehr Paper-Ideen, aber weiter ohne Echtgeld-Ausführung.",
            },
        }
        active = mode_map.get(mode, mode_map["aggressive_learning"])
        per_trade_risk = round(risk_budget * float(active["risk_multiplier"]), 2)
        planned_risk = round(per_trade_risk * max_trades, 2)
        protection_active = str(demo_account.get("day_status") or "") in {"protect_profit", "risk_review", "risk_halt"}
        learning_feedback = demo_account.get("learning_feedback") if isinstance(demo_account.get("learning_feedback"), dict) else {}
        journal_rate = float(learning_feedback.get("journal_completion_rate") or 0)
        open_trade_count = int(demo_account.get("open_trade_count") or 0)
        recommendation = "Profil ist für Paper-Lernen freigegeben; vor Ausführung trotzdem Trigger, Stop und Invalidierung prüfen."
        recommended_mode = mode
        recommendation_tone = "ok"
        if str(demo_account.get("day_status") or "") == "risk_halt":
            recommended_mode = "strict"
            recommendation_tone = "block"
            recommendation = "Trading pausieren: Risk-Halt ist aktiv. Erst offene Risiken und Verlustursache prüfen."
        elif str(demo_account.get("day_status") or "") == "risk_review":
            recommended_mode = "strict"
            recommendation_tone = "warning"
            recommendation = "Risiko-Review zuerst abschließen. Neue Paper-Trades nur nach manueller Prüfung."
        elif protection_active and mode == "aggressive_learning":
            recommended_mode = "learn"
            recommendation_tone = "warning"
            recommendation = "Gewinnschutz ist aktiv. Aggressives Lernen zurücknehmen und offene Gewinner zuerst managen."
        elif open_trade_count >= int(demo_account.get("max_open_trades") or 12):
            recommended_mode = "strict"
            recommendation_tone = "warning"
            recommendation = "Zu viele offene Paper-Trades. Erst bestehende Positionen managen, dann neue Setups testen."
        elif journal_rate and journal_rate < 70:
            recommended_mode = "learn"
            recommendation_tone = "warning"
            recommendation = "Lernqualität leidet: Journale zuerst vervollstaendigen, sonst lernt das System aus zu wenig Kontext."
        guardrails = [
            "Paper-only: keine Echtgeld-Ausführung.",
            "Jeder Trade braucht These, Trigger und Invalidierung.",
            "Offene Risiken und Verlustserien können neue Trades blockieren.",
        ]
        if protection_active:
            guardrails.insert(0, "Konto-Schutz ist aktiv: aggressives Lernen wird begrenzt oder geblockt.")
        return {
            "mode": mode,
            "label": active["label"],
            "tone": active["tone"],
            "description": active["description"],
            "max_trades": max_trades,
            "min_score": active["min_score"],
            "risk_multiplier": active["risk_multiplier"],
            "per_trade_risk_value": per_trade_risk,
            "planned_run_risk_value": planned_risk,
            "protection_active": protection_active,
            "recommended_mode": recommended_mode,
            "recommendation": recommendation,
            "recommendation_tone": recommendation_tone,
            "guardrails": guardrails,
            "summary": (
                f"{active['label']}: bis zu {max_trades} Paper-Trades ab Score {float(active['min_score']):.0f}, "
                f"Risiko x{float(active['risk_multiplier']):.2f}, geplant max. {planned_risk:.0f} Demo-Risiko pro Lauf."
            ),
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
        news_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        dashboard = self.build_dashboard(scoreboard, settings, news_context)
        selection = dashboard.get("auto_selection", {})
        raw_mode = str(mode or "").lower()
        mode = raw_mode if raw_mode in {"strict", "learn", "aggressive_learning"} else "strict"
        source_key = "aggressive_exploration" if mode == "aggressive_learning" else "exploration" if mode == "learn" else "selected"
        candidate_pool = selection.get(source_key, [])
        selected: List[Dict[str, Any]] = []
        diversification_skipped: List[Dict[str, Any]] = []
        selected_buckets: set[str] = set()
        for candidate in candidate_pool:
            risk_bucket = str(candidate.get("risk_bucket") or self._paper_risk_bucket(candidate))
            if risk_bucket in selected_buckets:
                diversification_skipped.append(
                    {
                        "ticker": candidate.get("ticker"),
                        "risk_bucket": risk_bucket,
                        "reason": "correlated risk bucket already selected in this run",
                    }
                )
                continue
            selected.append(candidate)
            selected_buckets.add(risk_bucket)
            if len(selected) >= max(1, int(max_trades or 1)):
                break
        selected_capital = self._summarize_candidate_capital(selected)
        blocker_summary = selection.get("blocker_summary") if isinstance(selection.get("blocker_summary"), dict) else {}
        no_trade_message = self._auto_selection_no_trade_message(mode, blocker_summary)
        preview_message = (
            no_trade_message
            if not selected
            else f"{len(selected)} aggressive Learning-Kandidaten erfüllen die erweiterten Paper-Gates: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
            if mode == "aggressive_learning"
            else f"{len(selected)} Learning-Kandidaten erfüllen die Exploration-Gates: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
            if mode == "learn"
            else f"{len(selected)} Demo-Kandidaten erfüllen die Auto-Selection-Gates: {selected_capital['notional_value']:.0f} Demo-Kapital, max. {selected_capital['max_loss_value']:.0f} Risiko."
        )
        if not execute:
            return {
                "status": "preview",
                "execute": False,
                "mode": mode,
                "selected": selected,
                "selected_capital": selected_capital,
                "opened": [],
                "selected_risk_buckets": sorted(selected_buckets),
                "diversification_skipped": diversification_skipped,
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
                            "leverage": (
                                float(candidate.get("recommended_leverage") or 1)
                                if mode == "strict" and candidate.get("leverage_eligible") is True
                                else 1
                            ),
                            "learning_mode": mode in {"learn", "aggressive_learning"} or bool(candidate.get("learning_mode")),
                            "risk_multiplier_override": candidate.get("risk_multiplier"),
                            "learning_context": {
                                "autopilot_mode": mode,
                                "candidate_reason": (candidate.get("reasons") or [None])[0],
                                "candidate_source": source_key,
                                "risk_multiplier": candidate.get("risk_multiplier"),
                                "account_day_status": (dashboard.get("demo_account") or {}).get("day_status"),
                                "account_queue_status": ((dashboard.get("demo_account") or {}).get("trade_action_queue") or {}).get("status"),
                            },
                            "alert_source_label": "Paper-Autopilot",
                        },
                        scoreboard,
                        settings,
                        news_context,
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
            "selected_risk_buckets": sorted(selected_buckets),
            "diversification_skipped": diversification_skipped,
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
        if "paper re-entry cooldown active" in lower:
            return "Re-Entry-Cooldown für denselben Lernfall aktiv"
        if "correlated paper risk bucket already open" in lower:
            return "korrelierte Risikogruppe ist bereits im Portfolio"
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

    def create_trade_from_payload(
        self,
        payload: Dict[str, Any],
        market_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if float(payload.get("leverage") or 1) > 1:
            raise ValueError("Leveraged paper trades must come from a quality-gated playbook.")
        enriched_payload = dict(payload)
        ticket = dict(payload.get("trade_ticket") or {}) if isinstance(payload.get("trade_ticket"), dict) else {}
        ticket.setdefault("schema_version", "1.1")
        ticket["entry_market_regime"] = self._build_entry_market_regime(market_context or {})
        enriched_payload["trade_ticket"] = ticket
        stored_trades = (
            self.portfolio_manager.list_paper_trades(limit=300)
            if hasattr(self.portfolio_manager, "list_paper_trades")
            else []
        )
        trades = self._enrich_trades(stored_trades)
        account = self._build_demo_account(trades, [])
        manual_candidate = {
            "ticker": enriched_payload.get("ticker"),
            "asset_class": enriched_payload.get("asset_class") or "equity",
            "direction": enriched_payload.get("direction") or "long",
        }
        self._attach_quantitative_correlation(
            [manual_candidate],
            [trade for trade in trades if trade.get("status") == "open"],
            account,
        )
        self._validate_requested_trade_capacity(enriched_payload, account, manual_candidate.get("correlation_check") or {})
        trade = self.portfolio_manager.create_paper_trade(enriched_payload)
        self._schedule_trade_outcomes(trade)
        return self._enrich_trade(trade)

    def _validate_requested_trade_capacity(
        self,
        payload: Dict[str, Any],
        account: Dict[str, Any],
        correlation_check: Dict[str, Any] | None = None,
    ) -> None:
        ticker = str(payload.get("ticker") or "").upper()
        asset_class = str(payload.get("asset_class") or "equity").lower()
        quantity = float(payload.get("quantity") or 0)
        entry_price = float(payload.get("entry_price") or 0)
        multiplier = float(payload.get("contract_multiplier") or (100 if asset_class == "option" else 1))
        leverage = float(payload.get("leverage") or 1)
        requested = quantity * entry_price * multiplier * leverage
        if requested <= 0:
            return
        limits = account.get("asset_class_limits") if isinstance(account.get("asset_class_limits"), dict) else {}
        class_limit = limits.get(asset_class) if isinstance(limits.get(asset_class), dict) else {}
        ticker_used = float((account.get("exposure_by_ticker") or {}).get(ticker) or 0)
        capacities = {
            "gross exposure": float(account.get("remaining_gross_exposure_value") or 0),
            "cash": float(account.get("cash_available_value") or 0),
            "ticker exposure": max(0.0, float(account.get("max_ticker_exposure_value") or 0) - ticker_used),
            f"{asset_class} exposure": float(class_limit.get("remaining_value") or 0) if class_limit else requested,
        }
        exceeded = [label for label, capacity in capacities.items() if requested > capacity + 0.01]
        if exceeded:
            raise ValueError(
                f"Requested paper notional {requested:.2f} exceeds " + ", ".join(exceeded) + "."
            )
        check = correlation_check if isinstance(correlation_check, dict) else {}
        if check.get("blocked") is True and check.get("static_bucket_duplicate") is not True:
            raise ValueError("Quantitative correlation gate blocks this paper trade: " + str(check.get("reason") or "extreme overlap"))

    def validate_leverage_product_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._validate_leverage_product_data(payload)

    def create_trade_from_playbook(
        self,
        payload: Dict[str, Any],
        scoreboard: Dict[str, Any],
        settings: Dict[str, Any] | None = None,
        news_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        playbook_id = payload.get("playbook_id")
        direction = (payload.get("direction") or "long").lower()
        requested_quantity = float(payload.get("quantity") or 0)
        leverage = float(payload.get("leverage") or 1)
        if leverage < 1 or leverage > 1000:
            raise ValueError("Paper leverage must be between 1x and the technical limit of 1000x.")
        rules = (settings or {}).get("do_not_trade") or {}
        outcome_learning = self._build_outcome_learning_adjustments()
        trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(limit=150))
        closed_trades = [trade for trade in trades if trade.get("status") == "closed"]
        news_evidence_performance = self._build_news_evidence_performance(closed_trades)
        news_shadow_lab = self._build_news_shadow_lab()
        playbooks = self._build_playbooks(scoreboard, rules, outcome_learning, news_context)
        self._apply_news_evidence_learning(playbooks, news_evidence_performance)
        self._apply_news_shadow_learning(playbooks, news_shadow_lab)
        self._refresh_playbook_decision_state(playbooks, rules)
        demo_account = self._build_demo_account(trades, playbooks)
        self._attach_quantitative_correlation(
            playbooks,
            [trade for trade in trades if trade.get("status") == "open"],
            demo_account,
        )
        playbooks = self._attach_demo_sizing(playbooks, demo_account, rules)
        playbook = next((item for item in playbooks if item.get("id") == playbook_id), None)
        if not playbook:
            raise ValueError("Playbook not found.")
        if str(playbook.get("setup_type") or "") == "confirmed_news_event":
            news_entry_errors = self._confirmed_news_entry_errors(playbook)
            if news_entry_errors:
                raise ValueError(
                    "Confirmed-news entry evidence gate blocks this paper trade: "
                    + ", ".join(news_entry_errors)
                )
        reentry_cooldown = self._build_paper_reentry_cooldown(playbook, trades)
        if reentry_cooldown.get("active") is True:
            raise ValueError(
                "Paper re-entry cooldown blocks the same ticker/setup/direction until "
                f"{reentry_cooldown.get('until')}."
            )
        if (
            playbook.get("setup_type") == "confirmed_news_event"
            and direction != str(playbook.get("direction") or "").lower()
        ):
            raise ValueError("Confirmed-news paper trade direction must match the verified price reaction.")
        if leverage > 1 and direction != str(playbook.get("direction") or "").lower():
            raise ValueError("Leveraged paper trade direction must match the evidence-backed playbook direction.")
        entry_source_label = str(payload.get("alert_source_label") or "Paper-Autopilot")
        playbook = {**playbook, "entry_source_label": entry_source_label}
        learning_mode = bool(payload.get("learning_mode"))
        risk_multiplier_override = payload.get("risk_multiplier_override")
        learning_context_payload = payload.get("learning_context") if isinstance(payload.get("learning_context"), dict) else {}
        if learning_mode:
            playbook = {
                **playbook,
                "learning_context": {
                    "autopilot_mode": learning_context_payload.get("autopilot_mode") or "manual_learning",
                    "candidate_reason": learning_context_payload.get("candidate_reason") or "learning mode",
                    "candidate_source": learning_context_payload.get("candidate_source") or "manual",
                    "risk_multiplier": learning_context_payload.get("risk_multiplier") or risk_multiplier_override,
                    "account_day_status": learning_context_payload.get("account_day_status") or demo_account.get("day_status"),
                    "account_queue_status": learning_context_payload.get("account_queue_status")
                    or (demo_account.get("trade_action_queue") or {}).get("status"),
                },
            }
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
                "contract_multiplier": product_data_validation["data"]["contract_multiplier"],
                "product_data_warnings": product_data_validation["warnings"],
            }
            offered_leverage = float(product_data_validation["data"].get("offered_leverage") or 1)
            if leverage <= 1:
                leverage = offered_leverage
            elif abs(leverage - offered_leverage) > 1e-9:
                raise ValueError("Requested leverage must exactly match the validated provider-offered product leverage.")
            if leverage > 1 and direction != str(playbook.get("direction") or "").lower():
                raise ValueError("Leveraged product direction must match the evidence-backed playbook direction.")
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
            raise ValueError("Demo account risk gate blocks this playbook: " + ", ".join(hard_demo_reasons[:3]))
        risk_bucket = self._paper_risk_bucket(playbook)
        if any(
            trade.get("status") == "open" and self._paper_risk_bucket(trade) == risk_bucket
            for trade in trades
        ):
            raise ValueError(f"Correlated paper risk bucket already has an open trade: {risk_bucket}.")

        is_option = playbook.get("asset_class") == "option"
        if is_option:
            execution_market = self._get_market_snapshot(playbook.get("ticker"))
            execution_blockers = self._market_snapshot_blockers(execution_market)
            if execution_blockers:
                raise ValueError(f"Underlying market data gate blocks this option playbook: {', '.join(execution_blockers)}")
            direction = playbook.get("direction") or direction
            underlying_price = float(execution_market.get("price") or 0)
            option_contract = playbook.get("option_contract") if isinstance(playbook.get("option_contract"), dict) else {}
            last_price = round(
                float(
                    (playbook.get("leveraged_product") or {}).get("ask")
                    or option_contract.get("ask")
                    or max(0.35, underlying_price * 0.025)
                ),
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
        leverage_assessment = self._build_leverage_assessment(playbook, demo_account, rules)
        if leverage > 1:
            if learning_mode:
                raise ValueError("Paper leverage is disabled in learning and aggressive-learning modes.")
            if leverage_assessment.get("eligible") is not True:
                raise ValueError(
                    "Paper leverage gate blocks this playbook: "
                    + ", ".join(leverage_assessment.get("blockers") or ["quality gates not met"])
                )
            if leverage > float(leverage_assessment.get("max_leverage") or 1) + 1e-9:
                raise ValueError("Requested leverage exceeds the evidence-based paper leverage cap.")
        playbook["selected_leverage"] = leverage
        playbook["leverage_assessment"] = leverage_assessment
        final_sizing_playbook = playbook
        if learning_mode and not hard_rule_reasons:
            final_sizing_playbook = {
                **playbook,
                "tradeable": True,
                "do_not_trade_reasons": [],
            }
        final_sizing = self._suggest_demo_sizing(
            final_sizing_playbook,
            demo_account,
            risk_multiplier_override if learning_mode else None,
            leverage=(
                1
                if (playbook.get("leveraged_product") or {}).get("leverage_is_embedded_in_product_price") is True
                else leverage
            ),
        )
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
                "max_holding_days": playbook.get("max_holding_days"),
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
            "leverage": leverage,
            "leverage_assessment": leverage_assessment,
            "trade_ticket": note_playbook.get("trade_ticket") or {},
            "news_evidence": playbook.get("news_evidence") or None,
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
        if str(existing.get("status") or "").lower() != "open":
            raise PaperTradeAlreadyClosedError("Trade is already closed.")
        ticket = existing.get("trade_ticket") if isinstance(existing.get("trade_ticket"), dict) else {}
        entry_execution = (ticket.get("execution_model") or {}).get("entry") if isinstance(ticket.get("execution_model"), dict) else None
        exit_market: Dict[str, Any] = {}
        if existing.get("asset_class") == "option":
            if closed_price not in (None, 0):
                exit_reference = float(closed_price or 0)
                exit_market = {
                    "source": "manual_option_close_price",
                    "data_as_of": datetime.utcnow().isoformat(),
                    "freshness": "manual",
                    "liquidity_status": "unknown",
                }
            else:
                exit_market = self._get_stored_option_contract_quote(ticket)
                exit_reference = float(exit_market.get("price") or 0)
                if exit_market.get("status") != "available" or exit_reference <= 0:
                    raise ValueError(
                        "Stored option contract quote unavailable; an explicit reviewed close price is required."
                    )
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
            raise PaperTradeAlreadyClosedError("Trade was already closed by another process.")
        return self._enrich_trade(closed)

    def close_trades_on_management_exits(self, limit: int = 50) -> Dict[str, Any]:
        open_trades = self._enrich_trades(self.portfolio_manager.list_paper_trades(status="open", limit=limit))
        closed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        exit_statuses = {"stop_hit", "target_hit", "news_reaction_failed"}

        for trade in open_trades:
            management = trade.get("management_plan") or {}
            status = str(management.get("status") or "")
            equity_time_exit = status == "holding_period_expired" and trade.get("asset_class") != "option"
            if status not in exit_statuses and not equity_time_exit:
                skipped.append(
                    {
                        "id": trade.get("id"),
                        "ticker": trade.get("ticker"),
                        "status": status or "monitor",
                    }
                )
                continue
            current_price = trade.get("current_price")
            trigger_reference = management.get("trigger_reference_price")
            exit_reference = trigger_reference or trade.get("current_reference_price") or current_price
            if exit_reference in (None, 0):
                errors.append(
                    {
                        "id": trade.get("id"),
                        "ticker": trade.get("ticker"),
                        "error": "Current reference price unavailable for managed close.",
                    }
                )
                continue
            try:
                exit_reason = f"managed_{status}"
                lesson = (
                    "Paper target reached: record whether the setup should be repeated."
                    if status == "target_hit"
                    else "News reaction failed: review headline direction, timing and relative-price confirmation."
                    if status == "news_reaction_failed"
                    else "Event holding window expired: review whether the catalyst had durable follow-through."
                    if status == "holding_period_expired"
                    else "Paper stop hit: review trigger quality, timing and invalidation."
                )
                notes = (
                    f"Auto-managed paper exit: {status}. "
                    f"{management.get('summary') or 'Management plan triggered.'} "
                    f"Trigger reference: {float(exit_reference):.4f}"
                )
                closed.append(
                    self.close_trade(
                        str(trade.get("id")),
                        closed_price=float(exit_reference),
                        notes=notes,
                        exit_reason=exit_reason,
                        lessons_learned=lesson,
                    )
                )
            except PaperTradeAlreadyClosedError:
                skipped.append(
                    {
                        "id": trade.get("id"),
                        "ticker": trade.get("ticker"),
                        "status": "already_closed",
                    }
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
        news_context: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        playbooks: List[Dict[str, Any]] = []

        for item in scoreboard.get("equities", [])[:4]:
            if not item.get("ticker"):
                continue
            direction = "long" if item.get("action") == "buy" else "short"
            score = float(item.get("total_score") or 0)
            broad_equity = item.get("signal_type") == "broad_equity_quality_momentum"
            market_fields = self._market_reference_fields(item.get("ticker"))
            playbooks.append(
                {
                    "id": f"equity-{item.get('ticker')}-{direction}",
                    "ticker": item.get("ticker"),
                    "asset_class": "equity",
                    "direction": direction,
                    "setup_type": "equity_quality_momentum" if broad_equity else "insider_follow",
                    "title": "Aktien-Qualität und Momentum" if broad_equity else "Insider follow-through",
                    "headline": item.get("headline"),
                    "source_label": item.get("source_label"),
                    "score": score,
                    "risk_buffer_pct": 4.0 if broad_equity else 3.5 if direction == "long" else 4.0,
                    "reward_buffer_pct": 8.5 if broad_equity else 7.5,
                    "max_holding_days": 15 if broad_equity else 10,
                    "thesis": (
                        "Breiter Aktien-Screen bestätigt Qualität, Trend über 20/50 Tage und beobachtbare Marktteilnahme. "
                        "Nur handeln, wenn Kurs und Volumen am Entry weiter bestätigen; Research-Snapshot ist keine Ausführungsquote."
                        if broad_equity
                        else
                        f"{item.get('source_label')} with strong {direction} bias. "
                        f"Use only if price holds after filing delay of {item.get('delay_days') if item.get('delay_days') is not None else 'offen'} days."
                    ),
                    "tags": (
                        ["equity", "quality", "momentum", "diversified scanner"]
                        if broad_equity
                        else ["long" if direction == "long" else "short", "official filing", "equity"]
                    ),
                    "market_evidence": item.get("market_evidence") if broad_equity else None,
                    "data_quality": item.get("data_quality") if broad_equity else None,
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
                    "max_holding_days": 15,
                    "thesis": (
                        f"Official PTR disclosure with {item.get('detail')}. "
                        "Only valid when the tape confirms after the delayed filing."
                    ),
                    "tags": ["delayed signal", "politics", direction],
                    **market_fields,
                }
            )

        for item in scoreboard.get("etfs", [])[:8]:
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
                    "max_holding_days": 14,
                    "thesis": "Liquid ETF with decent quality and momentum profile. Favor clean continuation over narrative chasing.",
                    "tags": ["etf", "momentum", "long"],
                    **market_fields,
                }
            )

        for item in scoreboard.get("crypto", [])[:4]:
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
                    "max_holding_days": 7,
                    "thesis": "Flow-driven crypto setup. Keep leverage conservative and size by volatility, not conviction alone.",
                    "tags": ["crypto", "momentum", "long"],
                    **market_fields,
                }
            )

        playbooks.extend(self._build_confirmed_news_playbooks(news_context or {}))
        playbooks.extend(self._build_commodity_leverage_playbooks())
        playbooks.extend(self._build_option_learning_playbooks(playbooks))
        self._apply_outcome_learning(playbooks, outcome_learning or {})
        entry_market_regime = self._build_entry_market_regime(news_context or {})

        for item in playbooks:
            item["entry_market_regime"] = deepcopy(entry_market_regime)
            item["strategy"] = StrategyLibrary.find_for_playbook(item)
            rule_state = self._get_do_not_trade_state(item, rules)
            item["do_not_trade_reasons"] = rule_state["blocked"]
            item["leverage_warnings"] = rule_state["leverage"]
            item["tradeable"] = len(rule_state["blocked"]) == 0
            item["decision_framework"] = self._build_decision_framework(item)

        return sorted(playbooks, key=lambda item: float(item.get("score") or 0), reverse=True)[:16]

    def _build_entry_market_regime(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Freeze the observable market state used when a Paper trade is opened.

        Volatility and breadth are explicitly labelled proxies because the free
        brief feed does not provide executable VIX or exchange advance/decline data.
        """
        context = context if isinstance(context, dict) else {}
        captured_at = datetime.now(timezone.utc).isoformat()
        regions = context.get("regions") if isinstance(context.get("regions"), dict) else {}
        region_moves: List[float] = []
        for region in regions.values():
            if not isinstance(region, dict):
                continue
            for asset in region.get("assets") or []:
                if not isinstance(asset, dict):
                    continue
                value = asset.get("change_1d")
                if isinstance(value, (int, float)):
                    region_moves.append(float(value))

        avg_move = sum(region_moves) / len(region_moves) if region_moves else None
        avg_abs_move = sum(abs(value) for value in region_moves) / len(region_moves) if region_moves else None
        positive = sum(1 for value in region_moves if value > 0)
        negative = sum(1 for value in region_moves if value < 0)
        breadth_ratio = positive / len(region_moves) if region_moves else None

        trend_label = "unavailable"
        if avg_move is not None:
            trend_label = "uptrend" if avg_move >= 0.35 else "downtrend" if avg_move <= -0.35 else "mixed"
        volatility_label = "unavailable"
        if avg_abs_move is not None:
            volatility_label = "calm" if avg_abs_move < 0.5 else "normal" if avg_abs_move < 1.25 else "elevated"
        breadth_label = "unavailable"
        if breadth_ratio is not None:
            breadth_label = "positive" if breadth_ratio >= 0.65 else "negative" if breadth_ratio <= 0.35 else "mixed"

        macro_assets = {
            str(item.get("ticker") or "").upper(): item
            for item in (context.get("macro_assets") or [])
            if isinstance(item, dict) and item.get("ticker")
        }

        def macro_state(ticker: str, positive_label: str, negative_label: str) -> Dict[str, Any]:
            row = macro_assets.get(ticker) or {}
            change = row.get("change_1d")
            label = "unavailable"
            if isinstance(change, (int, float)):
                label = positive_label if float(change) > 0.1 else negative_label if float(change) < -0.1 else "stable"
            return {
                "label": label,
                "ticker": ticker,
                "value": row.get("price") if isinstance(row.get("price"), (int, float)) else None,
                "change_1d_pct": float(change) if isinstance(change, (int, float)) else None,
                "source": "morning_brief_macro_asset",
            }

        rates = macro_state("^TNX", "rising", "falling")
        dollar = macro_state("DX-Y.NYB", "strengthening", "weakening")
        risk_label = str(context.get("macro_regime") or "unavailable").strip().lower() or "unavailable"
        missing = []
        for dimension, label in (
            ("trend", trend_label),
            ("volatility", volatility_label),
            ("rates", rates["label"]),
            ("dollar", dollar["label"]),
            ("risk_appetite", risk_label),
            ("breadth", breadth_label),
        ):
            if label == "unavailable":
                missing.append(dimension)
        return {
            "schema_version": "1.0",
            "captured_at": captured_at,
            "data_as_of": context.get("generated_at"),
            "immutable_at_entry": True,
            "source": "morning_brief_snapshot",
            "trend": {
                "label": trend_label,
                "average_observed_move_1d_pct": round(avg_move, 4) if avg_move is not None else None,
                "observations": len(region_moves),
                "method": "mean_1d_move_available_region_indices_and_futures",
            },
            "volatility": {
                "label": volatility_label,
                "observed_abs_move_1d_pct": round(avg_abs_move, 4) if avg_abs_move is not None else None,
                "is_proxy": True,
                "method": "mean_absolute_1d_move_region_indices_and_futures_not_vix",
            },
            "rates": rates,
            "dollar": dollar,
            "risk_appetite": {
                "label": risk_label,
                "opening_bias": context.get("opening_bias"),
                "source": "morning_brief_macro_regime",
            },
            "breadth": {
                "label": breadth_label,
                "positive": positive,
                "negative": negative,
                "observations": len(region_moves),
                "positive_ratio": round(breadth_ratio, 4) if breadth_ratio is not None else None,
                "is_proxy": True,
                "method": "cross_market_index_and_futures_participation_not_exchange_advance_decline",
            },
            "quality": {
                "status": "complete" if not missing else "partial" if len(missing) < 6 else "unavailable",
                "missing_dimensions": missing,
                "proxy_dimensions": ["volatility", "breadth"],
            },
        }

    def _news_gate_reasons(self, news: Dict[str, Any]) -> List[str]:
        evidence = news.get("source_evidence") if isinstance(news.get("source_evidence"), dict) else {}
        intelligence = news.get("news_intelligence") if isinstance(news.get("news_intelligence"), dict) else {}
        confirmation = news.get("market_confirmation") if isinstance(news.get("market_confirmation"), dict) else {}
        correction = evidence.get("correction_status") if isinstance(evidence.get("correction_status"), dict) else {}
        ticker = str(news.get("ticker") or confirmation.get("ticker") or "").upper().strip()
        expected = str(confirmation.get("expected_headline_direction") or "").lower()
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        published_at = self._as_utc_naive_datetime(news.get("published_at"))
        baseline_at = self._as_utc_naive_datetime(confirmation.get("baseline_at"))
        observed_at = self._as_utc_naive_datetime(confirmation.get("observed_at"))
        age_hours = ((now_utc - published_at).total_seconds() / 3600) if published_at else None
        reasons: List[str] = []
        if not ticker:
            reasons.append("explicit_ticker_missing")
        if str(news.get("ticker_association_basis") or "") != "explicit_title_entity":
            reasons.append("ticker_not_explicit_in_title")
        if expected not in {"positive", "negative"}:
            reasons.append("directional_stance_missing")
        if str(news.get("source_quality") or evidence.get("quality") or "") != "tier_1":
            reasons.append("tier_1_source_missing")
        if evidence.get("source_agreement") == "mixed_headline_signal":
            reasons.append("source_signal_conflict")
        if str(correction.get("status") or "") in {"correction_detected", "retracted_or_withdrawn"}:
            reasons.append("source_corrected_or_retracted")
        source_url = str(news.get("source_url") or news.get("link") or "").strip()
        parsed_source = urlparse(source_url)
        if (
            evidence.get("link_verified") is not True
            or parsed_source.scheme not in {"http", "https"}
            or not parsed_source.hostname
        ):
            reasons.append("verified_source_link_missing")
        if published_at is None:
            reasons.append("publication_timestamp_missing")
        if intelligence.get("is_important") is not True:
            reasons.append("importance_gate_not_met")
        confirmation_status = str(confirmation.get("status") or "")
        if confirmation_status != "confirmed":
            reasons.append(
                "price_reaction_contradicted"
                if confirmation_status == "contradicted"
                else "price_confirmation_missing"
            )
        if confirmation.get("event_window_aligned") is not True:
            reasons.append("event_window_not_aligned")
        if baseline_at is None or observed_at is None:
            reasons.append("reaction_window_timestamps_missing")
        elif published_at is not None and not (baseline_at <= published_at <= observed_at <= now_utc + timedelta(minutes=5)):
            reasons.append("reaction_window_timestamp_order_invalid")
        if not isinstance(confirmation.get("relative_move_since_publication"), (int, float)):
            reasons.append("relative_market_reaction_missing")
        if str(news.get("event_type") or "") == "earnings" and evidence.get("original_document_verified") is not True:
            reasons.append("earnings_primary_document_missing")
        if not isinstance(age_hours, (int, float)) or float(age_hours) < 0:
            reasons.append("news_age_unavailable")
        elif float(age_hours) > 24:
            reasons.append("news_older_than_24h")
        return self._dedupe_reason_list(reasons)

    def _confirmed_news_entry_errors(self, playbook: Dict[str, Any]) -> List[str]:
        evidence = playbook.get("news_evidence") if isinstance(playbook.get("news_evidence"), dict) else {}
        reporting = evidence.get("reporting_source") if isinstance(evidence.get("reporting_source"), dict) else {}
        primary = evidence.get("primary_source") if isinstance(evidence.get("primary_source"), dict) else {}
        confirmation = evidence.get("market_confirmation") if isinstance(evidence.get("market_confirmation"), dict) else {}
        correction = evidence.get("correction_status") if isinstance(evidence.get("correction_status"), dict) else {}
        errors: List[str] = []

        reporting_url = str(reporting.get("url") or evidence.get("source_url") or "").strip()
        reporting_parsed = urlparse(reporting_url)
        primary_url = str(primary.get("url") or "").strip()
        primary_parsed = urlparse(primary_url)
        reporting_is_tier_1 = str(reporting.get("quality") or evidence.get("source_quality") or "") == "tier_1"
        reporting_verified = (
            reporting.get("link_verified") is True
            and reporting_parsed.scheme in {"http", "https"}
            and bool(reporting_parsed.hostname)
        )
        primary_verified = (
            evidence.get("original_document_verified") is True
            and primary_parsed.scheme in {"http", "https"}
            and bool(primary_parsed.hostname)
        )
        if not primary_verified and not (reporting_is_tier_1 and reporting_verified):
            errors.append("primary_or_verified_tier_1_source_required")

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        published_at = self._as_utc_naive_datetime(evidence.get("published_at") or reporting.get("published_at"))
        baseline_at = self._as_utc_naive_datetime(confirmation.get("baseline_at"))
        observed_at = self._as_utc_naive_datetime(confirmation.get("observed_at"))
        if published_at is None:
            errors.append("publication_timestamp_missing_or_invalid")
        elif published_at > now_utc + timedelta(minutes=5) or (now_utc - published_at).total_seconds() > 24 * 3600:
            errors.append("publication_outside_24h_entry_window")
        if confirmation.get("status") != "confirmed" or confirmation.get("event_window_aligned") is not True:
            errors.append("market_reaction_window_not_confirmed")
        if baseline_at is None or observed_at is None:
            errors.append("market_reaction_timestamps_missing")
        elif published_at is not None and not (baseline_at <= published_at <= observed_at <= now_utc + timedelta(minutes=5)):
            errors.append("market_reaction_timestamp_order_invalid")
        if not isinstance(confirmation.get("relative_move_since_publication"), (int, float)):
            errors.append("relative_market_reaction_missing")
        expected = str(confirmation.get("expected_headline_direction") or "")
        expected_direction = "long" if expected == "positive" else "short" if expected == "negative" else ""
        if not expected_direction or expected_direction != str(playbook.get("direction") or ""):
            errors.append("market_reaction_direction_mismatch")
        if str(correction.get("status") or "") in {"correction_detected", "retracted_or_withdrawn", "source_unavailable"}:
            errors.append("source_corrected_retracted_or_unavailable")
        return self._dedupe_reason_list(errors)

    def _build_news_gate_monitor(
        self,
        news_context: Dict[str, Any],
        demo_account: Dict[str, Any],
        playbooks: List[Dict[str, Any]],
        auto_selection: Dict[str, Any],
    ) -> Dict[str, Any]:
        labels = {
            "explicit_ticker_missing": "kein eindeutig handelbarer Ticker",
            "ticker_not_explicit_in_title": "Ticker nicht ausdrücklich in der Überschrift zugeordnet",
            "directional_stance_missing": "keine belastbare positive oder negative Richtung",
            "tier_1_source_missing": "Quelle ist nicht Tier 1",
            "source_signal_conflict": "vergleichbare Quellen liefern widersprüchliche Richtungssignale",
            "source_corrected_or_retracted": "Quelle wurde korrigiert, zurückgezogen oder als Widerruf erkannt",
            "verified_source_link_missing": "verifizierter Quellenlink fehlt",
            "publication_timestamp_missing": "Veröffentlichungszeit fehlt",
            "importance_gate_not_met": "Meldung unterschreitet das Wichtigkeits-Gate",
            "price_reaction_contradicted": "Kursreaktion widerspricht der Meldungsrichtung",
            "price_confirmation_missing": "richtungskonforme Preisbestätigung fehlt",
            "event_window_not_aligned": "Preisfenster ist nicht an die Veröffentlichung ausgerichtet",
            "reaction_window_timestamps_missing": "Start- oder Beobachtungszeit des Reaktionsfensters fehlt",
            "reaction_window_timestamp_order_invalid": "Zeitfolge von Baseline, Veröffentlichung und Beobachtung ist ungültig",
            "relative_market_reaction_missing": "relative Marktreaktion ist nicht numerisch gespeichert",
            "earnings_primary_document_missing": "Earnings-Originaldokument ist nicht verifiziert",
            "news_age_unavailable": "Meldungsalter ist nicht belastbar",
            "news_older_than_24h": "Meldung ist älter als 24 Stunden",
        }
        checked_items = [item for item in news_context.get("top_news", []) or [] if isinstance(item, dict)]
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        reason_counts: Dict[str, int] = {}
        for news in checked_items:
            reasons = self._news_gate_reasons(news)
            intelligence = news.get("news_intelligence") if isinstance(news.get("news_intelligence"), dict) else {}
            confirmation = news.get("market_confirmation") if isinstance(news.get("market_confirmation"), dict) else {}
            row = {
                "title": news.get("title"),
                "publisher": news.get("publisher"),
                "source_url": news.get("source_url") or news.get("link"),
                "published_at": news.get("published_at"),
                "ticker": news.get("ticker") or confirmation.get("ticker"),
                "importance_score": intelligence.get("importance_score") or news.get("importance_score") or 0,
                "confirmation_status": confirmation.get("status") or "unavailable",
                "relative_move_since_publication": confirmation.get("relative_move_since_publication"),
                "reasons": reasons,
                "display_reasons": [labels.get(reason, reason) for reason in reasons],
            }
            if reasons:
                rejected.append(row)
                for reason in reasons:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
            else:
                accepted.append(row)

        rejected.sort(
            key=lambda item: (
                len(item.get("reasons") or []),
                -float(item.get("importance_score") or 0),
            )
        )
        news_playbooks = [item for item in playbooks if item.get("setup_type") == "confirmed_news_event"]
        paper_ready = [
            item for item in news_playbooks
            if (item.get("trade_ticket") or {}).get("paper_ready") is True
        ]
        auto_pools = [
            *(auto_selection.get("selected") or []),
            *(auto_selection.get("exploration") or []),
            *(auto_selection.get("aggressive_exploration") or []),
        ]
        auto_news_by_id = {
            str(item.get("id") or f"{item.get('ticker')}:{item.get('direction')}"): item
            for item in auto_pools
            if item.get("setup_type") == "confirmed_news_event"
        }
        auto_news = list(auto_news_by_id.values())
        day_status = str(demo_account.get("day_status") or "ready")
        account_blocked = bool(accepted and not auto_news)
        if not checked_items:
            status = "news_unavailable"
            message = "Keine aktuelle News-Stichprobe verfügbar; daraus entsteht kein Paper-Entry."
        elif not accepted:
            status = "no_eligible_news"
            message = "Keine Meldung erfüllt derzeit die vollständige Quellen-, Richtungs- und Preisbestätigung."
        elif account_blocked:
            status = "account_blocked"
            message = f"News-Gate erfüllt, aber Konto- oder Autopilot-Gates blockieren den Entry ({day_status})."
        else:
            status = "ready"
            message = f"{len(auto_news)} bestätigte News-Kandidaten sind für den Paper-Autopiloten qualifiziert."
        top_reasons = [
            {
                "reason": reason,
                "display_reason": labels.get(reason, reason),
                "count": count,
            }
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return {
            "status": status,
            "message": message,
            "brief_generated_at": news_context.get("generated_at"),
            "checked_count": len(checked_items),
            "eligible_count": len(accepted),
            "rejected_count": len(rejected),
            "paper_ready_count": len(paper_ready),
            "autopilot_qualified_count": len(auto_news),
            "account_blocked": account_blocked,
            "account_day_status": day_status,
            "top_reasons": top_reasons[:6],
            "next_best_rejected": rejected[0] if rejected else None,
            "eligible": accepted[:4],
            "policy": "Diagnose-only; der Monitor eröffnet selbst keine Trades und schaltet kein Echtgeld frei.",
        }

    def _build_confirmed_news_playbooks(self, news_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Turn only explicit, fresh and price-confirmed Tier-1 news into paper candidates."""
        candidates: Dict[tuple[str, str], Dict[str, Any]] = {}
        for news in news_context.get("top_news", []) or []:
            if not isinstance(news, dict):
                continue
            if self._news_gate_reasons(news):
                continue
            evidence = news.get("source_evidence") if isinstance(news.get("source_evidence"), dict) else {}
            intelligence = news.get("news_intelligence") if isinstance(news.get("news_intelligence"), dict) else {}
            confirmation = news.get("market_confirmation") if isinstance(news.get("market_confirmation"), dict) else {}
            ticker = str(news.get("ticker") or confirmation.get("ticker") or "").upper().strip()
            expected = str(confirmation.get("expected_headline_direction") or "").lower()
            direction = "long" if expected == "positive" else "short" if expected == "negative" else ""
            importance = float(intelligence.get("importance_score") or news.get("importance_score") or 0)
            original_verified = evidence.get("original_document_verified") is True
            corroborated = str(evidence.get("corroboration") or "") == "corroborated"
            score = min(96.0, 80.0 + max(0.0, importance - 12.0) * 1.2)
            score += 2.0 if original_verified else 0.0
            score += 2.0 if corroborated else 0.0
            score = round(min(96.0, score), 1)
            source_url = str(news.get("source_url") or news.get("link") or "")
            title = str(news.get("title") or "Confirmed Tier-1 news event")
            relative_move = confirmation.get("relative_move_since_publication")
            market_fields = self._market_reference_fields(ticker)
            primary_sources = list(news.get("primary_sources") or [])
            primary_source = primary_sources[0] if primary_sources else None
            correction_status = (
                evidence.get("correction_status")
                if isinstance(evidence.get("correction_status"), dict)
                else {
                    "status": "not_checked_legacy_context",
                    "checked_at": news_context.get("generated_at"),
                    "signals": [],
                    "monitoring_scope": "legacy_context_without_correction_scan",
                    "ongoing_monitor_verified": False,
                }
            )
            news_evidence = {
                "schema_version": "2.0",
                "title": title,
                "publisher": news.get("publisher"),
                "source_url": source_url,
                "published_at": news.get("published_at"),
                "source_quality": "tier_1",
                "fact_basis": intelligence.get("fact_basis"),
                "fact_summary": intelligence.get("fact_summary"),
                "event_type": news.get("event_type") or "unknown",
                "impact": news.get("impact") or intelligence.get("impact") or "unknown",
                "importance_score": importance,
                "original_document_verified": original_verified,
                "primary_sources": primary_sources,
                "corroboration": evidence.get("corroboration") or "single_source",
                "source_agreement": evidence.get("source_agreement") or "single_headline_signal",
                "reporting_source": {
                    "publisher": news.get("publisher"),
                    "domain": news.get("source_domain") or evidence.get("domain"),
                    "url": source_url,
                    "published_at": news.get("published_at"),
                    "quality": news.get("source_quality") or evidence.get("quality"),
                    "link_verified": evidence.get("link_verified") is True,
                    "reporting_basis": evidence.get("reporting_basis") or intelligence.get("fact_basis"),
                },
                "primary_source": primary_source,
                "facts": {
                    "summary": intelligence.get("fact_summary") or title,
                    "basis": intelligence.get("fact_basis") or evidence.get("reporting_basis"),
                    "verified_against_primary": bool(original_verified and primary_source),
                    "source_layer": "primary_document" if original_verified else "reporting_source",
                },
                "interpretation": {
                    "meaning": intelligence.get("meaning"),
                    "assessment": intelligence.get("assessment"),
                    "directional_bias": intelligence.get("directional_bias"),
                    "bull_case": intelligence.get("bull_case"),
                    "bear_case": intelligence.get("bear_case"),
                    "confirmation": intelligence.get("confirmation") or [],
                    "invalidation": intelligence.get("invalidation"),
                    "execution_horizon": intelligence.get("execution_horizon"),
                    "generated_by": "Broker Freund rule-based news intelligence",
                    "is_reported_fact": False,
                },
                "source_comparison": {
                    "corroboration": evidence.get("corroboration") or "single_source",
                    "publisher_count": int(evidence.get("publisher_count") or 1),
                    "source_agreement": evidence.get("source_agreement") or "single_headline_signal",
                    "independence_verified": False,
                },
                "correction_status": correction_status,
                "market_confirmation": {
                    "status": "confirmed",
                    "expected_headline_direction": expected,
                    "ticker": ticker,
                    "benchmark": confirmation.get("benchmark"),
                    "asset_move_since_publication": confirmation.get("asset_move_since_publication"),
                    "benchmark_move_since_publication": confirmation.get("benchmark_move_since_publication"),
                    "relative_move_since_publication": relative_move,
                    "baseline_at": confirmation.get("baseline_at"),
                    "observed_at": confirmation.get("observed_at"),
                    "event_window_aligned": True,
                    "causality_proven": False,
                },
                "precision_note": (
                    "Die Preisreaktion ist zeitlich am Veröffentlichungsfenster ausgerichtet, beweist aber keine Kausalität."
                ),
            }
            playbook = {
                "id": f"news-{ticker}-{direction}",
                "ticker": ticker,
                "asset_class": "equity",
                "direction": direction,
                "setup_type": "confirmed_news_event",
                "title": "Bestätigtes Tier-1-Newsereignis",
                "headline": title,
                "source_label": news.get("publisher") or evidence.get("publisher"),
                "source_url": source_url,
                "score": score,
                "risk_buffer_pct": 3.0,
                "reward_buffer_pct": 6.5,
                "max_holding_days": 3,
                "thesis": (
                    f"Explizite Tier-1-Meldung zu {ticker} mit bestätigter relativer Preisreaktion "
                    f"seit Veröffentlichung ({relative_move if relative_move is not None else 'gemessen'}%)."
                ),
                "tags": ["tier-1 news", "event-window confirmed", direction, "paper-only"],
                "news_evidence": news_evidence,
                **market_fields,
            }
            key = (ticker, direction)
            if key not in candidates or score > float(candidates[key].get("score") or 0):
                candidates[key] = playbook
        return list(candidates.values())[:4]

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
            (
                f"Paper-Hebel: {float(playbook.get('selected_leverage') or 1):.1f}x; "
                + (
                    "Anbieterhebel ist bereits im Produktkurs enthalten, Echtgeld gesperrt."
                    if (playbook.get("leveraged_product") or {}).get("leverage_is_embedded_in_product_price") is True
                    else "hebelbereinigte Stückzahl, Echtgeld gesperrt."
                )
            ),
            f"Trigger: {framework.get('entry_trigger') or 'Manuelle Trigger-Prüfung erforderlich.'}",
            f"Invalidierung: {framework.get('invalidation') or 'Manuelle Invalidierungsprüfung erforderlich.'}",
            f"Risikoplan: {framework.get('risk_plan') or 'Nur Paper-Risiko.'}",
            f"Ticket: Schema {ticket.get('schema_version') or 'n/a'} / Status {ticket.get('status') or 'n/a'} / Paper-ready {bool(ticket.get('paper_ready'))} / Echtgeld-ready {bool(ticket.get('real_money_ready'))}.",
        ]
        news_evidence = playbook.get("news_evidence") if isinstance(playbook.get("news_evidence"), dict) else {}
        if news_evidence:
            news_market = news_evidence.get("market_confirmation") if isinstance(news_evidence.get("market_confirmation"), dict) else {}
            lines.extend(
                [
                    f"Newsquelle: {news_evidence.get('publisher') or 'n/a'} / {news_evidence.get('source_url') or 'n/a'}",
                    f"News veröffentlicht: {news_evidence.get('published_at') or 'n/a'}; Faktenbasis: {news_evidence.get('fact_basis') or 'n/a'}.",
                    f"Primärdokument verifiziert: {bool(news_evidence.get('original_document_verified'))}; unabhängige Bestätigung: {news_evidence.get('corroboration') or 'single_source'}.",
                    f"Preisbestätigung: {news_market.get('status') or 'n/a'} / relative Bewegung {news_market.get('relative_move_since_publication')}%; Kausalität bewiesen: {bool(news_market.get('causality_proven'))}.",
                ]
            )
        if playbook.get("learning_mode"):
            lines.append("Lernmodus: reduzierte Demo-Position, kein strenges Top-Setup und nicht Echtgeld-bereit.")
            context = playbook.get("learning_context") if isinstance(playbook.get("learning_context"), dict) else {}
            if context:
                lines.append(
                    "Lernkontext: "
                    f"Modus {context.get('autopilot_mode') or 'n/a'} | "
                    f"Konto {context.get('account_day_status') or 'n/a'} | "
                    f"Queue {context.get('account_queue_status') or 'n/a'} | "
                    f"Grund {context.get('candidate_reason') or 'n/a'}."
                )
        if is_option:
            option_contract = playbook.get("option_contract") if isinstance(playbook.get("option_contract"), dict) else {}
            if option_contract.get("status") == "available":
                lines.append(
                    "Options-Snapshot: "
                    f"{option_contract.get('contract_symbol') or 'n/a'} | Strike {option_contract.get('strike')} | "
                    f"Verfall {option_contract.get('expiry')} | Bid/Ask {option_contract.get('bid')}/{option_contract.get('ask')} | "
                    f"Spread {option_contract.get('spread_pct')}% | IV {option_contract.get('implied_volatility_pct')}% | "
                    f"Open Interest {option_contract.get('open_interest')} | Break-even {option_contract.get('break_even')}."
                )
                lines.append("Options-Gate: nur Paper-Premienmodell; Snapshot ist verzögert und kein ausführbarer Brokerkurs; Greeks und Kontrakt vor jeder Echtgeld-Prüfung neu validieren.")
            else:
                lines.append("Options-Gate: nur Paper-Premienmodell; kein brauchbarer Optionsketten-Snapshot; Prämie ist geschätzt und der Kontrakt nicht handelbar freigegeben.")
        if playbook.get("product_data_required"):
            lines.append("Hebelprodukt-Daten vor Echtgeld: " + " | ".join(str(item) for item in playbook.get("product_data_required", [])[:5]))
        if playbook.get("leveraged_product"):
            product = playbook.get("leveraged_product") or {}
            lines.append(
                "Geprüftes Hebelprodukt: "
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
        offered_leverage = number_field("offered_leverage")
        contract_multiplier = number_field("contract_multiplier")
        if offered_leverage is not None:
            if offered_leverage <= 1:
                errors.append("offered_leverage_must_exceed_1")
            elif offered_leverage > 1000:
                errors.append("offered_leverage_over_technical_limit_1000")
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
                "offered_leverage": offered_leverage,
                "contract_multiplier": contract_multiplier,
                "leverage_is_embedded_in_product_price": True,
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
            entry_trigger = str(playbook.get("entry_trigger") or "").strip() or (
                f"{direction.upper()} nur als Paper-Test, nachdem Underlying, Liquidität und Timing bestätigt sind."
            )
            invalidation = str(playbook.get("invalidation") or "").strip() or (
                "Ungültig, wenn Underlying-Momentum nachlässt, Spread breit ist, IV/Laufzeit unattraktiv sind oder maximaler Prämienverlust nicht dokumentiert ist."
            )
            risk_plan = "Nur Paper-Option mit definiertem Risiko; maximaler Verlust ist die Prämie, keine Echtgeld-Ausführung aus diesem Modell."

        if is_commodity_leverage:
            underlying = playbook.get("underlying_asset") or ticker
            proxy = playbook.get("underlying_proxy") or ticker
            entry_trigger = str(playbook.get("entry_trigger") or "").strip() or (
                f"{underlying} Hebel-Proxy {proxy}: Paper-Test nur, wenn Makro-Nachricht, Future/Spot-Reaktion "
                "und ETF-Volumen dieselbe Richtung bestätigen."
            )
            invalidation = str(playbook.get("invalidation") or "").strip() or (
                "Ungültig, wenn die Makro-Nachricht zurückgenommen wird, der Future/Spot-Markt nicht bestätigt, "
                "Spread/IV unattraktiv ist oder das echte Hebelprodukt zu nah am Knockout liegt."
            )
            risk_plan = (
                "Nur Paper-Hebelproxy. Maximaler Verlust ist im Modell die Prämie; echte Optionsscheine/Knockouts "
                "brauchen Strike/Knockout, Laufzeit, Spread, Emittent und Overnight-Risiko vor jeder Real-Money-Prüfung."
            )

        if setup_type == "confirmed_news_event":
            entry_trigger = (
                f"{ticker} hält die im Veröffentlichungsfenster gemessene relative "
                f"{'Stärke' if direction == 'long' else 'Schwäche'}; Quelle und Meldung bleiben unverändert erreichbar."
            )
            invalidation = (
                f"Ungültig, wenn {ticker} die relative Reaktion vollständig zurücknimmt, die Quelle korrigiert wird "
                "oder die geplante Stop-Zone bricht."
            )
            risk_plan = (
                "Nur Paper-Größe. Kein Entry allein aufgrund der Überschrift; Kursfenster, Liquidität, Stop und "
                "gespeicherte News-Evidenz müssen beim Einstieg gültig sein."
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
        if setup_type == "confirmed_news_event":
            review_questions.extend(
                [
                    "Ist die Tier-1-Quelle weiterhin erreichbar und wurde die Meldung nicht korrigiert?",
                    "Hält die relative Preisreaktion nach Kosten an, ohne der Bewegung hinterherzulaufen?",
                ]
            )
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
        if max_holding_days > 0:
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
            ticket = item.get("trade_ticket") if isinstance(item.get("trade_ticket"), dict) else {}
            option_quote = self._get_stored_option_contract_quote(ticket)
            if option_quote.get("status") == "available" and float(option_quote.get("price") or 0) > 0:
                current_price = float(option_quote.get("price") or 0)
                raw_move = ((current_price / entry) - 1) * 100
                result, error_tag, notes = self._score_paper_outcome(raw_move, item)
                return {
                    "status": "evaluated",
                    "result": result,
                    "checked_at": checked_at,
                    "check_price": current_price,
                    "performance_pct": round(raw_move, 2),
                    "notes": (
                        f"Stored option contract premium move for {option_quote.get('contract_symbol')}: {notes} "
                        "Quote uses the delayed bid as a conservative exit reference."
                    ),
                    "error_tag": error_tag,
                }
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
                "notes": (
                    f"Underlying fallback model for paper {direction}: {notes} "
                    f"Stored contract quote unavailable ({option_quote.get('reason') or 'unknown reason'})."
                ),
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

    def _build_paper_reentry_cooldown(
        self,
        playbook: Dict[str, Any],
        trades: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        asset_class = str(playbook.get("asset_class") or "equity").lower()
        default_hours = 24.0 if asset_class in {"crypto", "option"} else 72.0
        env_name = f"PAPER_TRADING_REENTRY_COOLDOWN_HOURS_{asset_class.upper()}"
        try:
            cooldown_hours = min(720.0, max(1.0, float(os.getenv(env_name, str(default_hours)))))
        except (TypeError, ValueError):
            cooldown_hours = default_hours
        key = (
            str(playbook.get("ticker") or "").upper(),
            str(playbook.get("setup_type") or ""),
            str(playbook.get("direction") or "").lower(),
            asset_class,
        )
        latest_closed_at = None
        for trade in trades:
            if trade.get("status") != "closed":
                continue
            trade_key = (
                str(trade.get("ticker") or "").upper(),
                str(trade.get("setup_type") or ""),
                str(trade.get("direction") or "").lower(),
                str(trade.get("asset_class") or "equity").lower(),
            )
            if trade_key != key:
                continue
            closed_at = self._as_utc_naive_datetime(trade.get("closed_at"))
            if closed_at and (latest_closed_at is None or closed_at > latest_closed_at):
                latest_closed_at = closed_at
        if latest_closed_at is None:
            return {"active": False, "cooldown_hours": cooldown_hours}
        until = latest_closed_at + timedelta(hours=cooldown_hours)
        compare_now = datetime.now(timezone.utc).replace(tzinfo=None)
        active = compare_now < until
        return {
            "active": active,
            "cooldown_hours": cooldown_hours,
            "last_closed_at": latest_closed_at.isoformat(),
            "until": until.isoformat(),
            "remaining_hours": round(max(0.0, (until - compare_now).total_seconds() / 3600), 2),
            "policy": "Require a fresh observation window before repeating the same ticker, setup and direction.",
        }

    def _paper_risk_bucket(self, item: Dict[str, Any]) -> str:
        ticker = str(item.get("ticker") or "UNKNOWN").upper()
        asset_class = str(item.get("asset_class") or "equity").lower()
        if asset_class == "crypto":
            return "crypto"
        if asset_class == "etf":
            etf_groups = {
                "etf_growth": {"VUG", "QQQ"},
                "etf_broad_us": {"VTI", "VOO", "SPY"},
                "etf_small_cap": {"IWM"},
                "etf_global": {"VT"},
                "etf_dividend_value": {"VYM", "VTV", "SCHD", "JEPI"},
                "etf_real_estate": {"VNQ"},
                "etf_emerging": {"VWO", "EEM"},
                "etf_bonds": {"TLT", "IEF", "SHY", "BND"},
            }
            for bucket, tickers in etf_groups.items():
                if ticker in tickers:
                    return bucket
            return f"etf_{ticker.lower()}"
        if asset_class == "option":
            underlying = str(item.get("underlying_proxy") or ticker).upper()
            return f"option_{underlying.lower()}"
        return f"{asset_class}_{ticker.lower()}"

    def _attach_quantitative_correlation(
        self,
        playbooks: List[Dict[str, Any]],
        open_trades: List[Dict[str, Any]],
        demo_account: Dict[str, Any],
    ) -> None:
        """Measure daily-return correlations and block only well-observed extreme overlap."""
        open_tickers = sorted(
            {
                str(trade.get("ticker") or "").upper()
                for trade in open_trades
                if trade.get("ticker") and trade.get("asset_class") != "option"
            }
        )
        candidate_tickers = sorted(
            {
                str(playbook.get("ticker") or "").upper()
                for playbook in playbooks
                if playbook.get("ticker") and playbook.get("asset_class") != "option"
            }
        )
        tickers = sorted(set(open_tickers + candidate_tickers))
        analysis = self._build_return_correlation_analysis(tickers, open_tickers, candidate_tickers)
        demo_account["correlation_analysis"] = {
            key: value for key, value in analysis.items() if key != "candidate_checks"
        }
        checks = analysis.get("candidate_checks") if isinstance(analysis.get("candidate_checks"), dict) else {}
        open_risk_buckets = {self._paper_risk_bucket(trade) for trade in open_trades}
        for playbook in playbooks:
            ticker = str(playbook.get("ticker") or "").upper()
            check = checks.get(ticker) if isinstance(checks.get(ticker), dict) else None
            if check:
                playbook["correlation_check"] = {
                    **deepcopy(check),
                    "static_bucket_duplicate": self._paper_risk_bucket(playbook) in open_risk_buckets,
                }
            else:
                playbook["correlation_check"] = {
                    "status": "not_applicable" if playbook.get("asset_class") == "option" else analysis.get("status"),
                    "blocked": False,
                    "reason": "Options use their underlying risk bucket." if playbook.get("asset_class") == "option" else analysis.get("message"),
                }

    def _build_return_correlation_analysis(
        self,
        tickers: List[str],
        open_tickers: List[str],
        candidate_tickers: List[str],
    ) -> Dict[str, Any]:
        threshold = min(0.99, max(0.50, float(os.getenv("PAPER_TRADING_CORRELATION_BLOCK_THRESHOLD", "0.88"))))
        minimum_observations = max(20, int(os.getenv("PAPER_TRADING_CORRELATION_MIN_OBSERVATIONS", "40")))
        if len(tickers) < 2 or not open_tickers:
            return {
                "status": "insufficient_universe",
                "method": "Pearson correlation of daily adjusted returns over six months",
                "threshold": threshold,
                "minimum_observations": minimum_observations,
                "candidate_checks": {},
                "high_correlation_pairs": [],
                "message": "Mindestens eine offene Vergleichsposition und ein weiterer Ticker werden benötigt.",
            }
        cache_key = "|".join(tickers)
        cached = self._correlation_cache.get(cache_key)
        if isinstance(cached, dict) and time.time() - float(cached.get("cached_at") or 0) < 900:
            matrix_payload = cached.get("payload") or {}
        else:
            try:
                raw = yf.download(
                    tickers=tickers,
                    period="6mo",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="column",
                )
                if raw is None or raw.empty:
                    raise ValueError("empty_history")
                if getattr(raw.columns, "nlevels", 1) > 1:
                    closes = raw["Close"]
                else:
                    closes = raw[["Close"]].rename(columns={"Close": tickers[0]})
                returns = closes.pct_change(fill_method=None)
                correlations = returns.corr(min_periods=minimum_observations)
                matrix_payload = {
                    "returns": returns,
                    "correlations": correlations,
                    "data_as_of": (
                        closes.dropna(how="all").index[-1].isoformat()
                        if not closes.dropna(how="all").empty and hasattr(closes.dropna(how="all").index[-1], "isoformat")
                        else None
                    ),
                }
                self._correlation_cache = {cache_key: {"cached_at": time.time(), "payload": matrix_payload}}
            except Exception as exc:
                return {
                    "status": "unavailable",
                    "method": "Pearson correlation of daily adjusted returns over six months",
                    "threshold": threshold,
                    "minimum_observations": minimum_observations,
                    "candidate_checks": {},
                    "high_correlation_pairs": [],
                    "message": f"Renditehistorien nicht verfügbar ({type(exc).__name__}); statische Risikobuckets bleiben aktiv.",
                }

        returns = matrix_payload.get("returns")
        correlations = matrix_payload.get("correlations")
        if returns is None or correlations is None:
            return {
                "status": "unavailable",
                "candidate_checks": {},
                "high_correlation_pairs": [],
                "message": "Korrelationsmatrix ist nicht verfügbar; statische Risikobuckets bleiben aktiv.",
            }
        checks: Dict[str, Dict[str, Any]] = {}
        pairs: List[Dict[str, Any]] = []
        for candidate in candidate_tickers:
            best: Dict[str, Any] | None = None
            if candidate not in correlations.columns:
                continue
            for existing in open_tickers:
                if existing == candidate or existing not in correlations.columns:
                    continue
                value = correlations.at[candidate, existing]
                if value != value:
                    continue
                observations = int(returns[[candidate, existing]].dropna().shape[0])
                row = {
                    "candidate": candidate,
                    "existing_ticker": existing,
                    "correlation": round(float(value), 3),
                    "absolute_correlation": round(abs(float(value)), 3),
                    "observations": observations,
                }
                if best is None or row["absolute_correlation"] > best["absolute_correlation"]:
                    best = row
            if best:
                blocked = best["absolute_correlation"] >= threshold and best["observations"] >= minimum_observations
                checks[candidate] = {
                    **best,
                    "status": "blocked" if blocked else "clear",
                    "blocked": blocked,
                    "threshold": threshold,
                    "minimum_observations": minimum_observations,
                    "reason": (
                        f"{candidate} korreliert mit {best['existing_ticker']} zu {best['correlation']:.2f} über {best['observations']} Handelstage."
                    ),
                }
                if best["absolute_correlation"] >= 0.75:
                    pairs.append(best)
        pairs.sort(key=lambda item: float(item["absolute_correlation"]), reverse=True)
        return {
            "status": "ready",
            "method": "Pearson correlation of daily adjusted returns over six months",
            "threshold": threshold,
            "minimum_observations": minimum_observations,
            "data_as_of": matrix_payload.get("data_as_of"),
            "open_tickers": open_tickers,
            "candidate_checks": checks,
            "high_correlation_pairs": pairs[:12],
            "message": "Extreme, ausreichend beobachtete Renditekorrelation blockiert neue Doppelwetten; statische Buckets bleiben zusätzlicher Sicherheitsgurt.",
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
            "learning_risk_multiplier": 0.25,
            "aggressive_risk_multiplier": 0.60,
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
        open_risk_buckets = {
            self._paper_risk_bucket(trade)
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
                    or os.getenv("PAPER_TRADING_EXPLORATION_RISK_MULTIPLIER", "0.25")
                ),
            ),
        )
        aggressive_risk_multiplier = min(
            0.65,
            max(
                exploration_risk_multiplier,
                float(
                    autopilot_settings.get("aggressive_risk_multiplier")
                    or os.getenv("PAPER_TRADING_AGGRESSIVE_LEARNING_RISK_MULTIPLIER", "0.60")
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
            reentry_cooldown = self._build_paper_reentry_cooldown(playbook, trades)
            if reentry_cooldown.get("active") is True:
                cooldown_reason = f"paper re-entry cooldown active until {reentry_cooldown.get('until')}"
                reasons.append(cooldown_reason)
                exploration_reasons.append(cooldown_reason)
                aggressive_reasons.append(cooldown_reason)
            risk_bucket = self._paper_risk_bucket(playbook)
            if risk_bucket in open_risk_buckets:
                bucket_reason = f"correlated paper risk bucket already open: {risk_bucket}"
                reasons.append(bucket_reason)
                exploration_reasons.append(bucket_reason)
                aggressive_reasons.append(bucket_reason)
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
            if str(demo_account.get("day_status") or "") == "protect_profit":
                reasons.append("Paper account has profit-protection priority; new strict entries wait.")
                aggressive_reasons.append("Paper account has profit-protection priority; aggressive learning waits.")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected):
                reasons.append("demo account open-trade slots exhausted")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected) + len(exploration):
                exploration_reasons.append("demo account open-trade slots exhausted")
            if int(demo_account.get("open_trade_slots") or 0) <= len(selected) + len(exploration) + len(aggressive_exploration):
                aggressive_reasons.append("demo account open-trade slots exhausted")
            if playbook.get("asset_class") == "option" and not aggressive_reasons:
                aggressive_reasons.append("Optionskette muss vor aggressive Learning manuell geprüft werden")

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
                "leverage_eligible": (playbook.get("leverage_assessment") or {}).get("eligible") is True,
                "recommended_leverage": (playbook.get("leverage_assessment") or {}).get("recommended_leverage") or 1,
                "leverage_assessment": playbook.get("leverage_assessment") or {},
                "learning_mode": False,
                "trigger": framework.get("entry_trigger"),
                "invalidation": framework.get("invalidation"),
                "trade_ticket": playbook.get("trade_ticket") or {},
                "reentry_cooldown": reentry_cooldown,
                "risk_bucket": risk_bucket,
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
            if not exploration_reasons and playbook.get("asset_class") != "option":
                learning_row = dict(row)
                learning_row["learning_mode"] = True
                learning_sizing = self._suggest_demo_sizing(
                    {**playbook, "tradeable": True, "do_not_trade_reasons": []},
                    demo_account,
                    risk_multiplier_override=exploration_risk_multiplier,
                )
                learning_row.update(
                    {
                        key: learning_sizing.get(key)
                        for key in (
                            "suggested_quantity",
                            "suggested_notional_value",
                            "suggested_max_loss_value",
                            "suggested_account_pct",
                            "suggested_risk_pct",
                        )
                    }
                )
                learning_row["risk_multiplier"] = learning_sizing.get("risk_multiplier")
                learning_row["reasons"] = [f"learning mode: reduced risk x{exploration_risk_multiplier:g}"]
                exploration.append(learning_row)
            if not aggressive_reasons and playbook.get("asset_class") != "option":
                aggressive_row = dict(row)
                aggressive_row["learning_mode"] = True
                aggressive_row["aggressive_learning_mode"] = True
                aggressive_sizing = self._suggest_demo_sizing(
                    {**playbook, "tradeable": True, "do_not_trade_reasons": []},
                    demo_account,
                    risk_multiplier_override=aggressive_risk_multiplier,
                )
                aggressive_row.update(
                    {
                        key: aggressive_sizing.get(key)
                        for key in (
                            "suggested_quantity",
                            "suggested_notional_value",
                            "suggested_max_loss_value",
                            "suggested_account_pct",
                            "suggested_risk_pct",
                        )
                    }
                )
                aggressive_row["risk_multiplier"] = aggressive_sizing.get("risk_multiplier")
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
                and not any("paper re-entry cooldown active" in str(reason) for reason in item.get("reasons") or [])
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
            "reentry_cooldown_count": sum(
                1
                for item in rejected
                if any("paper re-entry cooldown active" in str(reason) for reason in item.get("reasons") or [])
            ),
        }

    def _auto_rejection_category(self, reason: str) -> str:
        lower = str(reason or "").lower()
        if "missing paper journal" in lower:
            return "journal"
        if "risk review" in lower or "exit actions open" in lower or "paper risk circuit" in lower:
            return "risk_review"
        if "profit-protection priority" in lower:
            return "profit_protection"
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
        if "paper re-entry cooldown active" in lower:
            return "reentry_cooldown"
        if "correlated paper risk bucket already open" in lower:
            return "correlation"
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
            "risk_review": "Risiko prüfen",
            "capacity": "Kapazitaet voll",
            "duplicate": "Duplikat offen",
            "reentry_cooldown": "Neues Beobachtungsfenster abwarten",
            "correlation": "Korrelationsrisiko",
            "score": "Score zu niedrig",
            "data": "Daten fehlen",
            "setup_quality": "Setup unvollstaendig",
            "options_review": "Optionscheck fehlt",
            "learning_block": "Lernen blockiert",
            "profit_protection": "Gewinnschutz zuerst",
            "quality_gate": "Quality-Gate",
        }
        return labels.get(str(category or ""), "Quality-Gate")

    def _auto_rejection_missing_to_trade(self, reasons: List[str]) -> str:
        text = " | ".join(str(reason or "").lower() for reason in reasons)
        if "score below auto minimum" in text:
            return "Score 88+ oder stärkere Preis-/Volumenbestätigung"
        if "score below minimum trade score" in text:
            return "Score 78+ und bessere Signalqualität"
        if "missing thesis, trigger or invalidation" in text:
            return "These, Trigger und Invalidierung voll dokumentieren"
        if "missing ticker or reference price" in text:
            return "Kursdaten oder Ticker-Zuordnung reparieren"
        if "same ticker/setup/direction already open" in text:
            return "Bestehenden Paper-Trade managen statt doppeln"
        if "paper re-entry cooldown active" in text:
            return "Re-Entry-Cooldown abwarten; danach beginnt ein unabhängigeres Beobachtungsfenster"
        if "correlated paper risk bucket already open" in text:
            return "Erst einen unabhängigen Risikobucket wählen oder die bestehende Gruppenposition schließen"
        if "paper risk circuit" in text:
            return "Cooldown abwarten und Verlustserie prüfen, bevor ein neuer Entry startet"
        if "risk review" in text or "exit actions open" in text:
            return "Offene Trades prüfen und Risk-Review beenden"
        if "profit-protection priority" in text:
            return "Gewinnschutz bei offenen Gewinnern prüfen"
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
            return "Fehlende Journale abschließen"
        if "option" in text or "optionskette" in text:
            return "Strike, Laufzeit, Spread und IV manuell prüfen"
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
        if "profit-protection priority" in text:
            return "Erst Gewinnschutz oder Trailing-Plan für laufende Gewinner festhalten; danach wieder Strict/Aggro öffnen."
        if "gross exposure budget is exhausted" in text:
            return "Kein neuer Entry: Gesamt-Exposure am Limit; erst Kapital freigeben."
        if "demo cash capacity is exhausted" in text:
            return "Kein neuer Entry: es ist kein freies Demo-Cash verfuegbar."
        if "ticker exposure budget is exhausted" in text:
            return "Kein neuer Entry in diesem Ticker: bestehende Konzentration zuerst reduzieren."
        if "option premium budget is exhausted" in text:
            return "Keine weitere Option: das aggregierte Prämienbudget ist ausgeschoepft."
        if "open risk budget is exhausted" in text or "open-trade slots exhausted" in text:
            return "Kein neuer Entry: Risiko oder Slots freimachen, bevor neue Exposure aufgebaut wird."
        if "same ticker/setup/direction already open" in text:
            return "Kein Duplikat eröffnen; bestehenden Paper-Trade managen oder schließen."
        if "paper re-entry cooldown active" in text:
            return "Keinen identischen Lernfall sofort wiederholen; Cooldown bis zum nächsten Beobachtungsfenster abwarten."
        if "correlated paper risk bucket already open" in text:
            return "Keine zweite stark korrelierte Position eröffnen; einen anderen Markt- oder Faktor-Bucket verwenden."
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
            for option_type, bias, score_penalty in (("call", "long", 0), ("put", "short", 3)):
                score = max(0, float(proxy["score"]) - score_penalty)
                option_contract = self._get_option_contract_snapshot(ticker, option_type, underlying_price)
                estimated_premium = round(max(0.45, underlying_price * 0.022), 2)
                premium = float(option_contract.get("ask") or option_contract.get("mid") or estimated_premium)
                contract_verified = option_contract.get("status") == "available"
                headline = str(proxy.get(f"{option_type}_headline") or f"{proxy['label']} {option_type.upper()} paper setup")
                thesis = str(proxy.get(f"{option_type}_thesis") or "")
                confirmation = str(proxy.get(f"{option_type}_confirmation") or "")
                invalidation = str(proxy.get(f"{option_type}_invalidation") or "")
                playbooks.append(
                    {
                        "id": f"commodity-option-{ticker}-{option_type}",
                        "ticker": ticker,
                        "asset_class": "option",
                        "direction": option_type,
                        "setup_type": f"commodity_{option_type}_leverage_learning",
                        "title": f"{proxy['label']} {option_type.upper()} leverage paper setup",
                        "headline": headline,
                        "source_label": "Yahoo Finance options chain snapshot" if contract_verified else "commodity proxy paper model fallback",
                        "score": score,
                        "risk_buffer_pct": 100.0,
                        "reward_buffer_pct": 120.0,
                        "thesis": thesis,
                        "entry_trigger": confirmation,
                        "invalidation": invalidation,
                        "option_decision": {
                            "underlying": proxy["label"],
                            "bias": bias,
                            "thesis": thesis,
                            "confirmation": confirmation,
                            "invalidation": invalidation,
                            "event_drivers": list(proxy.get("event_drivers") or []),
                            "data_limit": (
                                "Delayed options-chain snapshot; Greeks and executable broker quote are not verified."
                                if contract_verified
                                else "No usable options-chain snapshot; premium is an estimate and the setup cannot be treated as contract-specific."
                            ),
                        },
                        "tags": ["commodity", "leverage", proxy["theme"], option_type, "paper only"],
                        "reference_price": round(premium, 4),
                        "underlying_reference_price": underlying_price,
                        "option_contract": option_contract,
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
                            "Provider contract multiplier / product ratio",
                            "Implied volatility or product pricing premium",
                            "Overnight gap and issuer risk",
                        ],
                        "market_data": market_fields.get("market_data") or {},
                        "data_as_of": option_contract.get("data_as_of") or market_fields.get("data_as_of"),
                    }
                )
        return playbooks

    def _get_option_contract_snapshot(
        self,
        ticker: str,
        option_type: str,
        underlying_price: float,
    ) -> Dict[str, Any]:
        cache = getattr(self, "_option_chain_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._option_chain_cache = cache
        cache_key = f"{str(ticker).upper()}:{str(option_type).lower()}"
        try:
            ttl_seconds = max(30.0, float(os.getenv("PAPER_OPTION_CHAIN_CACHE_SECONDS", "900")))
        except (TypeError, ValueError):
            ttl_seconds = 900.0
        now_monotonic = time.monotonic()
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and now_monotonic - float(cached.get("stored_at") or 0) <= ttl_seconds:
            return dict(cached.get("snapshot") or {})

        fallback = {
            "status": "unavailable",
            "ticker": str(ticker).upper(),
            "option_type": str(option_type).lower(),
            "source": "yfinance_option_chain",
            "data_as_of": datetime.utcnow().isoformat(),
            "reason": "option_chain_unavailable",
        }
        try:
            raw_cache = getattr(self, "_option_chain_raw_cache", None)
            if not isinstance(raw_cache, dict):
                raw_cache = {}
                self._option_chain_raw_cache = raw_cache
            raw_key = str(ticker).upper()
            raw_cached = raw_cache.get(raw_key)
            expiry_chains: List[tuple[int, str, Any]] = []
            if (
                isinstance(raw_cached, dict)
                and now_monotonic - float(raw_cached.get("stored_at") or 0) <= ttl_seconds
            ):
                expiry_chains = list(raw_cached.get("expiry_chains") or [])
            else:
                client = yf.Ticker(ticker)
                today = datetime.utcnow().date()
                expiries: List[tuple[int, str]] = []
                for raw_expiry in list(client.options or []):
                    try:
                        expiry_date = datetime.fromisoformat(str(raw_expiry)).date()
                    except (TypeError, ValueError):
                        continue
                    days = (expiry_date - today).days
                    if days > 0:
                        expiries.append((days, str(raw_expiry)))
                preferred = [item for item in expiries if 14 <= item[0] <= 45]
                expiry_candidates = sorted(preferred or expiries, key=lambda item: abs(item[0] - 30))[:3]
                for expiry_days, expiry in expiry_candidates:
                    try:
                        expiry_chains.append((expiry_days, expiry, client.option_chain(expiry)))
                    except Exception:
                        continue
                raw_cache[raw_key] = {
                    "stored_at": now_monotonic,
                    "expiry_chains": expiry_chains,
                }
            rows: List[Dict[str, Any]] = []
            if not expiry_chains:
                raise ValueError("no_future_option_expiry")
            for expiry_days, expiry, chain in expiry_chains:
                frame = chain.calls if str(option_type).lower() == "call" else chain.puts
                if frame is None or frame.empty:
                    continue
                for record in frame.to_dict("records"):
                    try:
                        strike = float(record.get("strike") or 0)
                        bid = max(0.0, float(record.get("bid") or 0))
                        ask = max(0.0, float(record.get("ask") or 0))
                        last_price = max(0.0, float(record.get("lastPrice") or 0))
                        open_interest = max(0, int(record.get("openInterest") or 0))
                        volume = max(0, int(record.get("volume") or 0))
                        iv = max(0.0, float(record.get("impliedVolatility") or 0))
                    except (TypeError, ValueError):
                        continue
                    last_trade_dt = self._as_utc_naive_datetime(record.get("lastTradeDate"))
                    quote_is_stale = (
                        last_trade_dt is None
                        or datetime.utcnow() - last_trade_dt > timedelta(days=7)
                    )
                    if strike <= 0 or bid <= 0 or ask <= bid or iv < 0.01 or quote_is_stale:
                        continue
                    mid = (bid + ask) / 2
                    spread_pct = ((ask - bid) / mid) * 100 if mid > 0 else None
                    moneyness_pct = ((strike / underlying_price) - 1) * 100 if underlying_price > 0 else None
                    if (
                        spread_pct is None
                        or spread_pct > 25
                        or abs(moneyness_pct or 0) > 10
                        or (underlying_price > 0 and ask > underlying_price * 0.35)
                    ):
                        continue
                    if open_interest <= 0 and volume <= 0:
                        continue
                    distance = abs(moneyness_pct or 0)
                    liquidity_penalty = 0 if open_interest >= 100 else 1.5 if open_interest > 0 else 4.0
                    spread_penalty = min(8.0, spread_pct / 5)
                    rows.append(
                        {
                            "record": record,
                            "last_trade_dt": last_trade_dt,
                            "expiry": expiry,
                            "expiry_days": expiry_days,
                            "strike": strike,
                            "bid": bid,
                            "ask": ask,
                            "last_price": last_price,
                            "mid": mid,
                            "spread_pct": spread_pct,
                            "open_interest": open_interest,
                            "volume": volume,
                            "iv": iv,
                            "moneyness_pct": moneyness_pct,
                            "selection_score": distance + liquidity_penalty + spread_penalty + abs(expiry_days - 30) / 30,
                        }
                    )
            if not rows:
                raise ValueError("no_liquid_two_sided_near_money_contract")
            selected = min(rows, key=lambda item: float(item["selection_score"]))
            expiry = str(selected["expiry"])
            expiry_days = int(selected["expiry_days"])
            strike = float(selected["strike"])
            ask = float(selected["ask"])
            break_even = strike + ask if str(option_type).lower() == "call" else strike - ask
            distance_to_break_even_pct = ((break_even / underlying_price) - 1) * 100 if underlying_price > 0 else None
            last_trade = selected.get("last_trade_dt")
            if hasattr(last_trade, "isoformat"):
                last_trade = last_trade.isoformat()
            snapshot = {
                "status": "available",
                "ticker": str(ticker).upper(),
                "option_type": str(option_type).lower(),
                "contract_symbol": selected["record"].get("contractSymbol"),
                "expiry": expiry,
                "days_to_expiry": expiry_days,
                "strike": round(strike, 4),
                "underlying_price": round(float(underlying_price), 4),
                "bid": round(float(selected["bid"]), 4),
                "ask": round(ask, 4),
                "mid": round(float(selected["mid"]), 4),
                "spread_pct": round(float(selected["spread_pct"]), 2) if selected["spread_pct"] is not None else None,
                "last_price": round(float(selected["last_price"]), 4),
                "implied_volatility_pct": round(float(selected["iv"]) * 100, 2),
                "volume": int(selected["volume"]),
                "open_interest": int(selected["open_interest"]),
                "moneyness_pct": round(float(selected["moneyness_pct"]), 2) if selected["moneyness_pct"] is not None else None,
                "break_even": round(break_even, 4),
                "distance_to_break_even_pct": round(float(distance_to_break_even_pct), 2) if distance_to_break_even_pct is not None else None,
                "max_loss_per_contract": round(ask * 100, 2),
                "last_trade_at": str(last_trade) if last_trade is not None else None,
                "source": "yfinance_option_chain",
                "data_as_of": datetime.utcnow().isoformat(),
                "quote_quality": "delayed_snapshot_not_executable",
                "selection_basis": "near-the-money contract around 30 days, penalizing weak open interest and wide spreads",
            }
        except Exception as exc:
            fallback["reason"] = str(exc) or fallback["reason"]
            snapshot = fallback
        cache[cache_key] = {"stored_at": now_monotonic, "snapshot": snapshot}
        return dict(snapshot)

    def _build_option_contract_identity(self, playbook: Dict[str, Any]) -> Dict[str, Any]:
        ticker = str(playbook.get("ticker") or playbook.get("underlying_proxy") or "").upper()
        option_contract = playbook.get("option_contract") if isinstance(playbook.get("option_contract"), dict) else {}
        leveraged_product = playbook.get("leveraged_product") if isinstance(playbook.get("leveraged_product"), dict) else {}
        if not leveraged_product and option_contract.get("status") == "available" and option_contract.get("contract_symbol"):
            contract_symbol = str(option_contract.get("contract_symbol") or "").upper()
            expiry = str(option_contract.get("expiry") or "")
            strike = option_contract.get("strike")
            option_type = str(option_contract.get("option_type") or playbook.get("direction") or "").lower()
            return {
                "status": "locked",
                "identity_source": "option_chain_contract_symbol",
                "identity_key": f"option:{ticker}:{contract_symbol}:{expiry}:{strike}:{option_type}",
                "underlying_ticker": ticker,
                "contract_symbol": contract_symbol,
                "option_type": option_type,
                "strike": strike,
                "expiry": expiry,
                "locked_at": datetime.utcnow().isoformat(),
                "immutable": True,
            }
        if leveraged_product:
            product_type = str(leveraged_product.get("product_type") or "option_certificate").lower()
            issuer = str(leveraged_product.get("issuer") or "").strip()
            expiry = str(leveraged_product.get("expiry") or "")
            strike = leveraged_product.get("strike_or_knockout_level")
            return {
                "status": "locked",
                "identity_source": "manually_validated_provider_product",
                "identity_key": f"provider:{ticker}:{product_type}:{issuer}:{expiry}:{strike}",
                "underlying_ticker": ticker,
                "product_type": product_type,
                "issuer": issuer,
                "strike_or_knockout_level": strike,
                "expiry": expiry,
                "locked_at": datetime.utcnow().isoformat(),
                "immutable": True,
            }
        return {
            "status": "unverified",
            "identity_source": "estimated_premium_only",
            "identity_key": None,
            "underlying_ticker": ticker,
            "option_type": str(playbook.get("direction") or "").lower(),
            "locked_at": datetime.utcnow().isoformat(),
            "immutable": True,
        }

    def _get_stored_option_contract_quote(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        ticket = ticket if isinstance(ticket, dict) else {}
        contract = ticket.get("option_contract") if isinstance(ticket.get("option_contract"), dict) else {}
        identity = (
            ticket.get("option_contract_identity")
            if isinstance(ticket.get("option_contract_identity"), dict)
            else {}
        )
        symbol = str(contract.get("contract_symbol") or identity.get("contract_symbol") or "").upper()
        underlying = str(identity.get("underlying_ticker") or contract.get("ticker") or ticket.get("underlying_proxy") or ticket.get("instrument") or "").upper()
        expiry = str(identity.get("expiry") or contract.get("expiry") or "")
        option_type = str(identity.get("option_type") or contract.get("option_type") or ticket.get("direction") or "").lower()
        if not symbol or not underlying or not expiry or option_type not in {"call", "put"}:
            return {
                "status": "unavailable",
                "reason": "stored_contract_identity_incomplete",
                "contract_symbol": symbol or None,
            }
        if identity.get("status") == "locked":
            locked_symbol = str(identity.get("contract_symbol") or "").upper()
            if locked_symbol and locked_symbol != symbol:
                return {
                    "status": "blocked",
                    "reason": "stored_contract_identity_mismatch",
                    "contract_symbol": symbol,
                }

        cache = getattr(self, "_stored_option_quote_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._stored_option_quote_cache = cache
        try:
            ttl_seconds = max(15.0, float(os.getenv("PAPER_OPTION_QUOTE_CACHE_SECONDS", "120")))
        except (TypeError, ValueError):
            ttl_seconds = 120.0
        now_monotonic = time.monotonic()
        cached = cache.get(symbol)
        if isinstance(cached, dict) and now_monotonic - float(cached.get("stored_at") or 0) <= ttl_seconds:
            return dict(cached.get("quote") or {})

        quote: Dict[str, Any] = {
            "status": "unavailable",
            "reason": "stored_contract_quote_unavailable",
            "contract_symbol": symbol,
            "underlying_ticker": underlying,
            "expiry": expiry,
            "option_type": option_type,
        }
        try:
            chain = yf.Ticker(underlying).option_chain(expiry)
            frame = chain.calls if option_type == "call" else chain.puts
            if frame is None or frame.empty or "contractSymbol" not in frame:
                raise ValueError("stored_contract_not_in_chain")
            matched = frame[frame["contractSymbol"].astype(str).str.upper() == symbol]
            if matched.empty:
                raise ValueError("stored_contract_symbol_not_found")
            record = matched.iloc[0].to_dict()
            bid = max(0.0, float(record.get("bid") or 0))
            ask = max(0.0, float(record.get("ask") or 0))
            last_price = max(0.0, float(record.get("lastPrice") or 0))
            open_interest = max(0, int(record.get("openInterest") or 0))
            volume = max(0, int(record.get("volume") or 0))
            iv = max(0.0, float(record.get("impliedVolatility") or 0))
            last_trade_dt = self._as_utc_naive_datetime(record.get("lastTradeDate"))
            if last_trade_dt is None:
                raise ValueError("stored_contract_last_trade_missing")
            age_hours = max(0.0, (datetime.utcnow() - last_trade_dt).total_seconds() / 3600)
            if age_hours > 168:
                raise ValueError("stored_contract_quote_stale_over_7d")
            if bid <= 0 or ask < bid:
                raise ValueError("stored_contract_two_sided_quote_missing")
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100 if mid > 0 else None
            if spread_pct is None or spread_pct > 25:
                raise ValueError("stored_contract_spread_over_25_pct")
            liquidity_status = (
                "strong"
                if spread_pct <= 10 and open_interest >= 100
                else "adequate"
                if (open_interest > 0 or volume > 0)
                else "thin"
            )
            quote = {
                "status": "available",
                "price": round(bid, 4),
                "bid": round(bid, 4),
                "ask": round(ask, 4),
                "mid": round(mid, 4),
                "last_price": round(last_price, 4),
                "spread_pct": round(spread_pct, 2),
                "implied_volatility_pct": round(iv * 100, 2),
                "volume": volume,
                "open_interest": open_interest,
                "contract_symbol": symbol,
                "underlying_ticker": underlying,
                "expiry": expiry,
                "option_type": option_type,
                "source": "yfinance_stored_option_contract",
                "quote_side": "bid_for_conservative_exit",
                "data_as_of": last_trade_dt.isoformat(),
                "age_hours": round(age_hours, 2),
                "freshness": "fresh",
                "liquidity_status": liquidity_status,
                "quote_quality": "delayed_snapshot_not_executable",
            }
        except Exception as exc:
            quote["reason"] = str(exc) or quote["reason"]
        cache[symbol] = {"stored_at": now_monotonic, "quote": quote}
        return dict(quote)

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
            ticker = str(item.get("ticker") or "").upper()
            option_contract = self._get_option_contract_snapshot(ticker, option_type, price)
            estimated_premium = round(max(0.35, price * 0.025), 2)
            premium = float(option_contract.get("ask") or option_contract.get("mid") or estimated_premium)
            contract_verified = option_contract.get("status") == "available"
            base_headline = str(item.get("headline") or item.get("title") or f"{ticker} underlying setup")
            confirmation = (
                f"{ticker} must sustain the bullish trigger from '{base_headline}' with confirming relative volume before the CALL is valid."
                if option_type == "call"
                else f"{ticker} must sustain the bearish trigger from '{base_headline}' with confirming relative volume before the PUT is valid."
            )
            invalidation = (
                f"The CALL case fails if {ticker} loses the underlying stop zone, relative volume fades or the source catalyst is contradicted."
                if option_type == "call"
                else f"The PUT case fails if {ticker} reclaims the underlying stop zone, downside volume fades or the source catalyst is contradicted."
            )
            thesis = (
                f"Options-Demo on {ticker}: {base_headline}. The contract is useful only if the underlying thesis, timing and volume remain aligned."
            )
            option_playbooks.append(
                {
                    "id": f"option-{item.get('ticker')}-{option_type}",
                    "ticker": item.get("ticker"),
                    "asset_class": "option",
                    "direction": option_type,
                    "setup_type": f"option_{option_type}_learning",
                    "title": f"{ticker} {option_type.upper()} contract-specific paper setup",
                    "headline": f"{ticker} {option_type.upper()}: {base_headline}",
                    "score": max(0, score - 3),
                    "risk_buffer_pct": 100.0,
                    "reward_buffer_pct": 100.0,
                    "thesis": thesis,
                    "entry_trigger": confirmation,
                    "invalidation": invalidation,
                    "option_decision": {
                        "underlying": ticker,
                        "bias": direction,
                        "thesis": thesis,
                        "confirmation": confirmation,
                        "invalidation": invalidation,
                        "event_drivers": [base_headline, "underlying price trend", "relative volume", "source catalyst"],
                        "data_limit": (
                            "Delayed options-chain snapshot; Greeks and executable broker quote are not verified."
                            if contract_verified
                            else "No usable options-chain snapshot; premium is an estimate and the setup cannot be treated as contract-specific."
                        ),
                    },
                    "tags": ["option", option_type, "paper only", "defined risk"],
                    "reference_price": round(premium, 4),
                    "underlying_reference_price": price,
                    "option_contract": option_contract,
                    "option_type": option_type,
                    "contract_multiplier": 100,
                    "max_holding_days": 10,
                    "quality_gate": [
                        "Underlying signal score >= 88",
                        "Price reference exists",
                        "Use only as demo option idea until IV, strike and expiry are verified",
                    ],
                    "source_label": "Yahoo Finance options chain snapshot" if contract_verified else item.get("source_label"),
                    "data_as_of": option_contract.get("data_as_of") or item.get("data_as_of"),
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
            "risk_per_trade_pct": env_float("PAPER_TRADING_RISK_PER_TRADE_PCT", 0.75, minimum=0.01),
            "max_open_risk_pct": env_float("PAPER_TRADING_MAX_OPEN_RISK_PCT", 6.0, minimum=0.1),
            "max_position_pct": env_float("PAPER_TRADING_MAX_POSITION_PCT", 20.0, minimum=0.1),
            "max_gross_exposure_pct": env_float("PAPER_TRADING_MAX_GROSS_EXPOSURE_PCT", 100.0, minimum=1.0),
            "min_cash_reserve_pct": min(40.0, env_float("PAPER_TRADING_MIN_CASH_RESERVE_PCT", 10.0, minimum=0.0)),
            "max_ticker_exposure_pct": env_float("PAPER_TRADING_MAX_TICKER_EXPOSURE_PCT", 25.0, minimum=0.1),
            "max_equity_exposure_pct": min(100.0, env_float("PAPER_TRADING_MAX_EQUITY_EXPOSURE_PCT", 45.0, minimum=0.1)),
            "max_etf_exposure_pct": min(100.0, env_float("PAPER_TRADING_MAX_ETF_EXPOSURE_PCT", 45.0, minimum=0.1)),
            "max_crypto_exposure_pct": min(100.0, env_float("PAPER_TRADING_MAX_CRYPTO_EXPOSURE_PCT", 12.0, minimum=0.1)),
            "max_option_exposure_pct": min(100.0, env_float("PAPER_TRADING_MAX_OPTION_EXPOSURE_PCT", 8.0, minimum=0.1)),
            "max_option_premium_pct": env_float("PAPER_TRADING_MAX_OPTION_PREMIUM_PCT", 2.0, minimum=0.01),
            "max_open_option_premium_pct": env_float("PAPER_TRADING_MAX_OPEN_OPTION_PREMIUM_PCT", 8.0, minimum=0.01),
            "risk_per_option_trade_pct": env_float("PAPER_TRADING_RISK_PER_OPTION_TRADE_PCT", 0.50, minimum=0.01),
            "risk_review_new_trade_multiplier": min(
                1.0,
                env_float("PAPER_TRADING_RISK_REVIEW_NEW_TRADE_MULTIPLIER", 0.50, minimum=0.01),
            ),
            "max_open_trades": env_int("PAPER_TRADING_MAX_OPEN_TRADES", 12, minimum=1),
            "daily_loss_limit_pct": env_float("PAPER_TRADING_DAILY_LOSS_LIMIT_PCT", 1.5, minimum=0.1),
            "max_drawdown_pct": env_float("PAPER_TRADING_MAX_DRAWDOWN_PCT", 12.0, minimum=0.5),
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
        exposure_by_asset_class: Dict[str, float] = {}
        for trade in open_trades:
            ticker = str(trade.get("ticker") or "UNKNOWN").upper()
            asset_class = str(trade.get("asset_class") or "equity").lower()
            invested_value = float(trade.get("invested_value") or 0)
            exposure_by_ticker[ticker] = round(
                exposure_by_ticker.get(ticker, 0.0) + invested_value,
                2,
            )
            exposure_by_asset_class[asset_class] = round(
                exposure_by_asset_class.get(asset_class, 0.0) + invested_value,
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
        trade_action_queue = self._build_trade_action_queue(open_trades)
        review_trades = [
            trade
            for trade in open_trades
            if str((trade.get("management_plan") or {}).get("decision_grade") or "") == "review"
        ]
        review_tickers = sorted({str(trade.get("ticker") or "").upper() for trade in review_trades if trade.get("ticker")})
        review_asset_classes = sorted(
            {str(trade.get("asset_class") or "").lower() for trade in review_trades if trade.get("asset_class")}
        )
        if risk_circuit.get("active"):
            day_status = "risk_halt"
            day_action = "Keine neuen Paper-Entries: Verlustlimit oder Verlustserien-Cooldown zuerst auslaufen lassen."
        elif management_counts.get("exit"):
            day_status = "action_required"
            day_action = "Exits prüfen, bevor ein neuer Paper-Trade geöffnet wird."
        elif management_counts.get("review"):
            day_status = "risk_review"
            day_action = "Review-Ticker und korreliertes Krypto-Risiko nicht erhöhen; unabhängige Setups nur mit halbiertem Risiko."
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
        effective_max_gross_exposure_pct = min(
            float(config["max_gross_exposure_pct"]),
            max(0.0, 100.0 - float(config["min_cash_reserve_pct"])),
        )
        max_gross_exposure_value = round(equity * (effective_max_gross_exposure_pct / 100), 2)
        max_ticker_exposure_value = round(equity * (float(config["max_ticker_exposure_pct"]) / 100), 2)
        max_option_premium_value = round(equity * (float(config["max_option_premium_pct"]) / 100), 2)
        max_open_option_premium_value = round(equity * (float(config["max_open_option_premium_pct"]) / 100), 2)
        option_risk_budget = round(equity * (float(config["risk_per_option_trade_pct"]) / 100), 2)
        remaining_risk = round(max(0.0, max_open_risk_value - open_risk_value), 2)
        remaining_gross_exposure = round(max(0.0, max_gross_exposure_value - open_exposure_value), 2)
        remaining_option_premium = round(max(0.0, max_open_option_premium_value - option_premium_exposure_value), 2)
        asset_class_limit_pcts = {
            "equity": float(config["max_equity_exposure_pct"]),
            "etf": float(config["max_etf_exposure_pct"]),
            "crypto": float(config["max_crypto_exposure_pct"]),
            "option": float(config["max_option_exposure_pct"]),
        }
        asset_class_limits: Dict[str, Dict[str, Any]] = {}
        for asset_class, limit_pct in asset_class_limit_pcts.items():
            limit_value = round(equity * (limit_pct / 100), 2)
            used_value = round(float(exposure_by_asset_class.get(asset_class) or 0), 2)
            asset_class_limits[asset_class] = {
                "limit_pct": limit_pct,
                "limit_value": limit_value,
                "used_value": used_value,
                "used_pct": round((used_value / equity) * 100, 2) if equity > 0 else 0.0,
                "remaining_value": round(max(0.0, limit_value - used_value), 2),
                "over_limit": used_value > limit_value + 0.01,
            }
        cash_reserve_target_value = round(equity * (float(config["min_cash_reserve_pct"]) / 100), 2)
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
            "exposure_by_asset_class": exposure_by_asset_class,
            "asset_class_limits": asset_class_limits,
            "effective_max_gross_exposure_pct": effective_max_gross_exposure_pct,
            "cash_reserve_target_value": cash_reserve_target_value,
            "cash_reserve_gap_value": round(max(0.0, cash_reserve_target_value - cash_available_value), 2),
            "top_ticker_exposure": {
                "ticker": top_ticker,
                "value": exposure_by_ticker.get(top_ticker, 0.0) if top_ticker else 0.0,
                "pct": round((exposure_by_ticker.get(top_ticker, 0.0) / equity) * 100, 2) if top_ticker and equity > 0 else 0.0,
            },
            "option_premium_exposure_value": option_premium_exposure_value,
            "open_trade_count": len(open_trades),
            "closed_trade_count": len(closed_trades),
            "management_counts": management_counts,
            "trade_action_queue": trade_action_queue,
            "review_tickers": review_tickers,
            "review_asset_classes": review_asset_classes,
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
                f"Mindestens {float(config['min_cash_reserve_pct']):g}% Cashreserve und Assetklassen-Limits verhindern einseitige Vollinvestition.",
                "Im Risiko-Review bleiben betroffene Ticker und neues Krypto-Risiko gesperrt; unabhängige Setups laufen höchstens mit halbem Risiko.",
                "Calls und Puts bleiben Paper-only, bis Optionskette, IV, Strike, Laufzeit und Spread geprüft sind.",
                "Echtgeld-Nutzung erfordert manuelle Prüfung, Suitability-Check und aktuelle Marktvalidierung.",
            ],
            "learning_feedback": self._build_learning_feedback(trades),
        }

    def _build_trade_action_queue(self, open_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        priority_map = {
            "exit": (1, "jetzt prüfen", "critical"),
            "review": (2, "Risiko prüfen", "warning"),
            "protect": (3, "Gewinn schuetzen", "positive"),
            "wait": (4, "Daten abwarten", "neutral"),
            "hold": (5, "Plan halten", "neutral"),
        }
        rows: List[Dict[str, Any]] = []
        for trade in open_trades:
            management = trade.get("management_plan") if isinstance(trade.get("management_plan"), dict) else {}
            grade = str(management.get("decision_grade") or "hold")
            priority, label, severity = priority_map.get(grade, priority_map["hold"])
            rows.append(
                {
                    "id": trade.get("id"),
                    "ticker": str(trade.get("ticker") or "UNKNOWN").upper(),
                    "direction": str(trade.get("direction") or "").lower(),
                    "asset_class": trade.get("asset_class") or "equity",
                    "setup_type": trade.get("setup_type"),
                    "priority": priority,
                    "priority_label": label,
                    "severity": severity,
                    "management_status": management.get("status") or "monitor",
                    "decision_grade": grade,
                    "action": management.get("action") or "hold",
                    "summary": management.get("summary") or "Paper-Plan halten, solange Trigger und Invalidierung gueltig bleiben.",
                    "next_check": management.get("next_check") or "Trigger, Stop und Ziel erneut prüfen.",
                    "invested_value": round(float(trade.get("invested_value") or 0), 2),
                    "unrealized_pnl_value": round(float(trade.get("unrealized_pnl_value") or 0), 2),
                    "unrealized_pnl_pct": trade.get("unrealized_pnl_pct"),
                    "risk_distance_pct": management.get("risk_distance_pct"),
                    "target_progress_pct": management.get("target_progress_pct"),
                }
            )
        rows.sort(key=lambda item: (int(item["priority"]), -abs(float(item.get("unrealized_pnl_value") or 0))))
        first = rows[0] if rows else None
        return {
            "status": first.get("decision_grade") if first else "no_open_trades",
            "top_priority": first,
            "items": rows[:8],
            "counts": {
                "exit": sum(1 for item in rows if item.get("decision_grade") == "exit"),
                "review": sum(1 for item in rows if item.get("decision_grade") == "review"),
                "protect": sum(1 for item in rows if item.get("decision_grade") == "protect"),
                "hold": sum(1 for item in rows if item.get("decision_grade") == "hold"),
                "wait": sum(1 for item in rows if item.get("decision_grade") == "wait"),
            },
            "message": (
                f"Zuerst {first.get('ticker')} {str(first.get('direction') or '').upper()} prüfen: {first.get('priority_label')}."
                if first
                else "Keine offenen Paper-Trades. Nächsten Entry nur mit Trigger, Stop, Ziel und Risiko öffnen."
            ),
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

    def _attach_demo_sizing(
        self,
        playbooks: List[Dict[str, Any]],
        demo_account: Dict[str, Any],
        rules: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        sized: List[Dict[str, Any]] = []
        for item in playbooks:
            row = dict(item)
            row["risk_bucket"] = self._paper_risk_bucket(row)
            sizing = self._suggest_demo_sizing(row, demo_account)
            row.update(sizing)
            assessment = self._build_leverage_assessment(row, demo_account, rules or {})
            if assessment.get("eligible") is True:
                leveraged_sizing = self._suggest_demo_sizing(
                    row,
                    demo_account,
                    leverage=float(assessment.get("recommended_leverage") or 1),
                )
                assessment["recommended_sizing"] = {
                    key: leveraged_sizing.get(key)
                    for key in (
                        "suggested_quantity",
                        "suggested_notional_value",
                        "suggested_max_loss_value",
                        "suggested_account_pct",
                        "suggested_risk_pct",
                    )
                }
            row["leverage_assessment"] = assessment
            row["recommended_leverage"] = assessment.get("recommended_leverage") or 1
            row["trade_ticket"] = self._build_trade_ticket(row, demo_account)
            sized.append(row)
        return sized

    def _build_leverage_assessment(
        self,
        playbook: Dict[str, Any],
        demo_account: Dict[str, Any],
        rules: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Conservative paper-only leverage gate with an auditable verdict."""
        rules = rules or {}
        blockers: List[str] = []
        checks: List[str] = []
        score = float(playbook.get("score") or 0)
        leveraged_product = (
            playbook.get("leveraged_product")
            if isinstance(playbook.get("leveraged_product"), dict)
            else {}
        )
        provider_offered_leverage = float(leveraged_product.get("offered_leverage") or 0)
        provider_product = bool(
            playbook.get("leverage_product_type")
            and provider_offered_leverage > 1
            and leveraged_product.get("leverage_is_embedded_in_product_price") is True
        )
        min_score = (
            max(80.0, float(rules.get("min_score_for_new_trade") or 78))
            if provider_product
            else max(88.0, float(rules.get("min_score_for_leverage") or 88))
        )
        asset_class = str(playbook.get("asset_class") or "equity").lower()
        direction = str(playbook.get("direction") or "").lower()
        market = playbook.get("market_data") if isinstance(playbook.get("market_data"), dict) else {}
        risk_pct = float(playbook.get("risk_buffer_pct") or 0)
        reward_pct = float(playbook.get("reward_buffer_pct") or 0)
        risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0
        day_status = str(demo_account.get("day_status") or "")

        if not provider_product and asset_class not in {"equity", "etf"}:
            blockers.append("Hebel-Multiplikator ist nur für Aktien- und ETF-Paper-Setups erlaubt; Optionen und Krypto haben eigene Risikomodelle.")
        if direction not in ({"long", "short", "call", "put"} if provider_product else {"long", "short"}):
            blockers.append("Keine eindeutig handelbare Long- oder Short-Richtung.")
        if score < min_score:
            blockers.append(f"Score {score:.0f} liegt unter dem Hebel-Mindestscore {min_score:.0f}.")
        else:
            checks.append(f"Score-Gate erfüllt ({score:.0f}/{min_score:.0f}).")
        if playbook.get("leverage_warnings"):
            leverage_warnings = [str(item) for item in playbook.get("leverage_warnings") or []]
            if provider_product:
                leverage_warnings = [item for item in leverage_warnings if not item.startswith("Kein Hebel unter Score")]
            blockers.extend(leverage_warnings)
        if playbook.get("tradeable") is False or playbook.get("do_not_trade_reasons"):
            blockers.append("Signalregeln geben das Setup nicht uneingeschränkt frei.")
        if playbook.get("demo_tradeable") is False or playbook.get("demo_block_reasons"):
            blockers.append("Demo-Konto- oder Risikogate blockiert neue Exposure.")
        if day_status not in {"no_open_trades", "monitor"}:
            blockers.append(f"Kontostatus {day_status or 'unbekannt'} erlaubt keinen neuen Hebel.")
        else:
            checks.append(f"Kontostatus {day_status} erlaubt eine Hebelprüfung.")
        if str(market.get("freshness") or "") != "fresh":
            blockers.append("Marktdaten sind nicht frisch.")
        else:
            checks.append("Marktdaten sind frisch.")
        if str(market.get("liquidity_status") or "") != "strong":
            blockers.append("Liquidität ist nicht stark genug für Hebel.")
        else:
            checks.append("Liquiditäts-Gate erfüllt.")
        minimum_risk_reward = 1.2 if provider_product else 2.0
        if risk_reward < minimum_risk_reward:
            blockers.append(f"Geplantes Chance/Risiko {risk_reward:.2f} liegt unter {minimum_risk_reward:.2f}.")
        else:
            checks.append(f"Chance/Risiko-Gate erfüllt ({risk_reward:.2f}).")

        news_evidence = playbook.get("news_evidence") if isinstance(playbook.get("news_evidence"), dict) else {}
        if str(playbook.get("setup_type") or "") == "confirmed_news_event":
            confirmation = news_evidence.get("market_confirmation") if isinstance(news_evidence.get("market_confirmation"), dict) else {}
            if confirmation.get("status") != "confirmed" or confirmation.get("event_window_aligned") is not True:
                blockers.append("News-Preisreaktion ist nicht sauber bestätigt und zeitlich ausgerichtet.")
            if str(news_evidence.get("event_type") or "") == "earnings" and news_evidence.get("original_document_verified") is not True:
                blockers.append("Earnings-Originaldokument ist nicht verifiziert.")
            if news_evidence.get("source_agreement") == "mixed_headline_signal":
                blockers.append("Quellen liefern widersprüchliche Richtungssignale.")

        blockers = self._dedupe_reason_list(blockers)
        eligible = not blockers
        max_leverage = 1.0
        if eligible:
            max_leverage = provider_offered_leverage if provider_product else (2.0 if score >= 95 and risk_reward >= 2.0 else 1.5)
        return {
            "status": "eligible" if eligible else "blocked",
            "eligible": eligible,
            "recommended_leverage": max_leverage,
            "max_leverage": max_leverage,
            "score": score,
            "minimum_score": min_score,
            "risk_reward": round(risk_reward, 2),
            "provider_offered_leverage": provider_offered_leverage if provider_product else None,
            "leverage_embedded_in_product_price": provider_product,
            "checks": checks,
            "blockers": blockers,
            "risk_policy": (
                "Anbieterhebel wird vollständig ausgewiesen, ist aber bereits im Produktkurs enthalten; Einsatz, Stückzahl und P&L werden nicht erneut multipliziert."
                if provider_product
                else "Hebel erhöht nie das konfigurierte maximale Kontorisiko; die Stückzahl wird invers reduziert."
            ),
            "paper_only": True,
            "real_money_ready": False,
        }

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
        option_contract = playbook.get("option_contract") if isinstance(playbook.get("option_contract"), dict) else {}
        option_contract_identity = self._build_option_contract_identity(playbook) if is_option else None
        if is_option and option_contract.get("status") != "available":
            warnings.append("option_chain_not_validated")
        elif is_option:
            warnings.append("option_chain_snapshot_not_executable_quote")
        if playbook.get("leverage_product_type"):
            warnings.append("leverage_product_data_required")
        if playbook.get("product_data_required"):
            warnings.append("issuer_strike_expiry_spread_required")
        if playbook.get("leveraged_product"):
            warnings = [item for item in warnings if item not in {"leverage_product_data_required", "issuer_strike_expiry_spread_required"}]
            warnings.extend(str(item) for item in playbook.get("product_data_warnings") or [])
        warnings.extend(str(item) for item in framework.get("warnings") or [])

        paper_ready = not errors and not blocked_reasons and bool(playbook.get("demo_tradeable"))
        selected_leverage = float(playbook.get("selected_leverage") or 1)
        contract_multiplier = float(playbook.get("contract_multiplier") or (100 if is_option else 1))
        leveraged_product = playbook.get("leveraged_product") if isinstance(playbook.get("leveraged_product"), dict) else {}
        leverage_embedded = leveraged_product.get("leverage_is_embedded_in_product_price") is True
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
            "schema_version": "1.1",
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
            "max_holding_days": playbook.get("max_holding_days") or None,
            "quantity": playbook.get("suggested_quantity"),
            "notional_value": playbook.get("suggested_notional_value"),
            "max_loss_value": playbook.get("suggested_max_loss_value"),
            "leverage": selected_leverage,
            "contract_multiplier": contract_multiplier,
            "leverage_calculation": {
                "selected_or_offered_leverage": selected_leverage,
                "leverage_embedded_in_product_price": leverage_embedded,
                "pnl_leverage_multiplier": 1.0 if leverage_embedded else selected_leverage,
                "contract_multiplier": contract_multiplier,
                "formula": "price_move * quantity * direction * pnl_leverage_multiplier * contract_multiplier",
                "double_application_blocked": True,
            },
            "leverage_assessment": playbook.get("leverage_assessment") or None,
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
            "learning_context": playbook.get("learning_context") or None,
            "entry_market_regime": deepcopy(playbook.get("entry_market_regime") or self._build_entry_market_regime({})),
            "news_evidence": playbook.get("news_evidence") or None,
            "data_as_of": data_as_of or None,
            "market_data": market_data or None,
            "execution_model": execution_model or None,
            "leverage_product_type": playbook.get("leverage_product_type") or None,
            "underlying_asset": playbook.get("underlying_asset") or None,
            "underlying_proxy": playbook.get("underlying_proxy") or None,
            "option_contract": option_contract or None,
            "option_contract_identity": option_contract_identity,
            "option_decision": playbook.get("option_decision") or None,
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
        leverage: float = 1.0,
    ) -> Dict[str, Any]:
        leverage = max(1.0, min(1000.0, float(leverage or 1)))
        price = float(playbook.get("reference_price") or 0)
        risk_buffer_pct = float(playbook.get("risk_buffer_pct") or 3.5)
        contract_multiplier = float(playbook.get("contract_multiplier") or 1)
        is_option = playbook.get("asset_class") == "option"
        risk_per_unit = price * (risk_buffer_pct / 100) * contract_multiplier * leverage
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
        asset_class = str(playbook.get("asset_class") or "equity").lower()
        exposure_by_ticker = (
            demo_account.get("exposure_by_ticker")
            if isinstance(demo_account.get("exposure_by_ticker"), dict)
            else {}
        )
        current_ticker_exposure = float(exposure_by_ticker.get(ticker) or 0)
        ticker_limit = float(demo_account.get("max_ticker_exposure_value") or max_position_value)
        remaining_ticker_exposure = max(0.0, ticker_limit - current_ticker_exposure)
        asset_class_limits = (
            demo_account.get("asset_class_limits")
            if isinstance(demo_account.get("asset_class_limits"), dict)
            else {}
        )
        asset_class_limit = (
            asset_class_limits.get(asset_class)
            if isinstance(asset_class_limits.get(asset_class), dict)
            else {}
        )
        remaining_asset_class_exposure = float(
            asset_class_limit.get("remaining_value")
            if asset_class_limit.get("remaining_value") is not None
            else max_position_value
        )
        capacity_limits = [
            max_position_value,
            remaining_gross,
            cash_available,
            remaining_ticker_exposure,
            remaining_asset_class_exposure,
        ]
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
        day_status = str(demo_account.get("day_status") or "")
        review_tickers = {str(item).upper() for item in demo_account.get("review_tickers") or []}
        review_asset_classes = {str(item).lower() for item in demo_account.get("review_asset_classes") or []}
        candidate_is_under_review = ticker in review_tickers or (
            asset_class == "crypto" and "crypto" in review_asset_classes
        )
        if day_status == "risk_review" and not candidate_is_under_review:
            risk_multiplier *= min(
                1.0,
                max(0.01, float(demo_account.get("risk_review_new_trade_multiplier") or 0.50)),
            )
        if risk_multiplier_override is not None:
            try:
                risk_multiplier *= min(1.0, max(0.01, float(risk_multiplier_override)))
            except (TypeError, ValueError):
                pass
        risk_budget *= risk_multiplier
        block_reasons: List[str] = []
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
        elif day_status == "risk_review" and candidate_is_under_review:
            block_reasons.append("Ticker oder korreliertes Krypto-Risiko ist selbst im Risiko-Review und darf nicht erhöht werden.")
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
        if asset_class_limit and remaining_asset_class_exposure <= 0:
            block_reasons.append(f"Asset-class exposure budget is exhausted for {asset_class}.")
        correlation_check = (
            playbook.get("correlation_check")
            if isinstance(playbook.get("correlation_check"), dict)
            else {}
        )
        if correlation_check.get("blocked") is True and correlation_check.get("static_bucket_duplicate") is not True:
            block_reasons.append(
                "Quantitative correlation gate: "
                + str(correlation_check.get("reason") or "candidate duplicates an existing return factor")
            )
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
        quantity_by_position = max_position_value / (price * contract_multiplier * leverage) if price > 0 else 0
        quantity = max(0.0, min(quantity_by_risk, quantity_by_position))
        if is_option:
            quantity = float(int(quantity))
        if quantity < 0.0001:
            block_reasons.append("Vorgeschlagene Menge ist zu klein für das konfigurierte Risikobudget.")

        notional = quantity * price * contract_multiplier * leverage
        max_loss = quantity * risk_per_unit
        return {
            "suggested_quantity": round(quantity, 6),
            "suggested_notional_value": round(notional, 2),
            "suggested_max_loss_value": round(max_loss, 2),
            "suggested_account_pct": round((notional / float(demo_account.get("equity") or 1)) * 100, 2),
            "suggested_risk_pct": round((max_loss / float(demo_account.get("equity") or 1)) * 100, 2),
            "remaining_gross_capacity_value": round(remaining_gross, 2),
            "remaining_ticker_capacity_value": round(remaining_ticker_exposure, 2),
            "remaining_asset_class_capacity_value": round(remaining_asset_class_exposure, 2),
            "asset_class_limit": asset_class_limit,
            "correlation_check": correlation_check,
            "risk_multiplier": risk_multiplier,
            "sizing_leverage": leverage,
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
        ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
        leveraged_product = ticket.get("leveraged_product") if isinstance(ticket.get("leveraged_product"), dict) else {}
        payout_multiplier = 1.0 if leveraged_product.get("leverage_is_embedded_in_product_price") is True else leverage
        contract_multiplier = float(
            trade.get("contract_multiplier")
            or ticket.get("contract_multiplier")
            or (100 if trade.get("asset_class") == "option" else 1)
        )
        if not entry or stop in (None, 0) or quantity <= 0:
            return 0.0
        return abs(entry - float(stop)) * quantity * payout_multiplier * contract_multiplier

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

    def _build_news_evidence_performance(self, closed_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Measure realized news-trade evidence without treating correlation as causation."""
        news_trades: List[Dict[str, Any]] = []
        for trade in closed_trades:
            if str(trade.get("setup_type") or "") != "confirmed_news_event":
                continue
            if trade.get("realized_pnl_pct") is None:
                continue
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            evidence = ticket.get("news_evidence") if isinstance(ticket.get("news_evidence"), dict) else {}
            if not evidence:
                continue
            news_trades.append(trade)

        def build_rows(dimension: str) -> List[Dict[str, Any]]:
            buckets: Dict[str, List[Dict[str, Any]]] = {}
            for trade in news_trades:
                ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
                evidence = ticket.get("news_evidence") if isinstance(ticket.get("news_evidence"), dict) else {}
                if dimension == "source":
                    label = str(evidence.get("publisher") or "Unbekannte Quelle").strip() or "Unbekannte Quelle"
                else:
                    label = str(evidence.get("event_type") or "unknown").strip().lower() or "unknown"
                buckets.setdefault(label, []).append(trade)

            rows: List[Dict[str, Any]] = []
            for label, trades in buckets.items():
                performance = build_trade_performance(trades)
                sample_size = int(performance.get("sample_size") or 0)
                win_rate = float(performance.get("win_rate") or 0)
                expectancy_pct = float(performance.get("expectancy_pct") or 0)
                profit_factor = performance.get("profit_factor")
                reaction_failures = sum(
                    1 for trade in trades if "news_reaction_failed" in str(trade.get("exit_reason") or "")
                )
                reaction_failure_rate = round((reaction_failures / max(1, sample_size)) * 100, 1)
                quality_status = "insufficient_sample"
                score_delta = 0
                next_action = "Mindestens 10 geschlossene News-Paper-Trades sammeln; Quelle noch nicht gewichten."
                if sample_size >= 10:
                    quality_status = "neutral"
                    next_action = "Gewichtung unverändert lassen und weitere Marktregime sammeln."
                    if expectancy_pct < 0 or win_rate < 40:
                        quality_status = "downgrade"
                        score_delta = -6
                        next_action = "Künftige News-Setups vorsichtiger bewerten und stärkeren Follow-through verlangen."
                    elif expectancy_pct > 0 and win_rate >= 55 and profit_factor is not None and float(profit_factor) >= 1.2:
                        quality_status = "promising"
                        score_delta = 3
                        next_action = "Positive Paper-Evidenz weiter testen; keine Echtgeldfreigabe daraus ableiten."
                elif sample_size >= 5:
                    quality_status = "building_evidence"
                    next_action = "Frühes Signal beobachten, aber bis 10 Abschlüssen keine Score-Anpassung vornehmen."
                rows.append(
                    {
                        "dimension": dimension,
                        "label": label,
                        "trades": sample_size,
                        "performance": performance,
                        "reaction_failures": reaction_failures,
                        "reaction_failure_rate": reaction_failure_rate,
                        "quality_status": quality_status,
                        "score_delta": score_delta,
                        "next_action": next_action,
                    }
                )
            status_rank = {"promising": 0, "neutral": 1, "building_evidence": 2, "insufficient_sample": 3, "downgrade": 4}
            rows.sort(
                key=lambda item: (
                    status_rank.get(str(item.get("quality_status") or ""), 5),
                    -int(item.get("trades") or 0),
                    str(item.get("label") or ""),
                )
            )
            return rows

        overall = build_trade_performance(news_trades)
        return {
            "summary": {
                "closed_news_trades": len(news_trades),
                "minimum_adjustment_sample": 10,
                "performance": overall,
                "causality_note": (
                    "Realisierte Ergebnisse messen zeitlichen Follow-through, beweisen aber keine Kausalität der Meldung."
                ),
                "policy": (
                    "Score-Anpassungen beginnen erst ab 10 geschlossenen Trades je Quelle oder Eventtyp; "
                    "eine automatische Echtgeldfreigabe ist ausgeschlossen."
                ),
            },
            "sources": build_rows("source"),
            "event_types": build_rows("event_type"),
        }

    def _build_news_shadow_lab(self) -> Dict[str, Any]:
        """Build a one-signal/one-outcome news study from persisted 24h forecasts."""
        empty = {
            "summary": {
                "forecasts": 0,
                "evaluated_24h": 0,
                "pending_24h": 0,
                "hits": 0,
                "misses": 0,
                "neutral": 0,
                "hit_rate": 0.0,
                "avg_directional_move_pct": None,
                "strict_gate_lift_pct_points": None,
                "sample_unit": "Eine Meldung mit genau einem 24-Stunden-Ergebnis.",
                "policy": "Shadow-Studie ohne Position, PnL oder Echtgeldwirkung.",
            },
            "quality_cohorts": [],
            "sources": [],
            "event_types": [],
        }
        try:
            forecasts = self.portfolio_manager.list_signal_forecasts(limit=500)
            outcomes = self.portfolio_manager.list_signal_forecast_outcomes(limit=2200)
        except Exception:
            return empty

        top_news = [
            forecast
            for forecast in forecasts
            if str(forecast.get("setup_type") or "") == "top_news_forecast"
            or str(forecast.get("source_label") or "") == "trusted_news"
        ]
        forecast_by_id = {str(forecast.get("id") or ""): forecast for forecast in top_news}
        canonical_outcomes = [
            outcome
            for outcome in outcomes
            if str(outcome.get("forecast_id") or "") in forecast_by_id
            and int(outcome.get("horizon_hours") or 0) == 24
        ]
        pending_24h = sum(
            1 for outcome in canonical_outcomes if str(outcome.get("status") or "") in {"pending", "pending_data"}
        )
        rows: List[Dict[str, Any]] = []
        for outcome in canonical_outcomes:
            if str(outcome.get("status") or "") != "evaluated":
                continue
            forecast = forecast_by_id.get(str(outcome.get("forecast_id") or "")) or {}
            metadata_raw = forecast.get("metadata_json")
            if isinstance(metadata_raw, dict):
                metadata = metadata_raw
            else:
                try:
                    metadata = json.loads(str(metadata_raw or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    metadata = {}
            news = metadata.get("news_item") if isinstance(metadata.get("news_item"), dict) else {}
            reasons = set(self._news_gate_reasons(news)) if news else set()
            price_reasons = {
                "price_confirmation_missing",
                "price_reaction_contradicted",
                "event_window_not_aligned",
            }
            if not reasons:
                quality_cohort = "strict_gate_confirmed"
            elif "price_reaction_contradicted" in reasons and not (reasons - price_reasons):
                quality_cohort = "price_contradicted"
            elif reasons and not (reasons - price_reasons):
                quality_cohort = "verified_unconfirmed"
            else:
                quality_cohort = "directional_headline"

            direction = str(forecast.get("direction") or outcome.get("direction") or "").lower()
            try:
                raw_move = float(outcome.get("performance_pct"))
            except (TypeError, ValueError):
                continue
            directional_move = -raw_move if any(token in direction for token in ("short", "hedge", "avoid", "reduce")) else raw_move
            evidence = news.get("source_evidence") if isinstance(news.get("source_evidence"), dict) else {}
            rows.append(
                {
                    "forecast_id": outcome.get("forecast_id"),
                    "symbol": forecast.get("symbol") or outcome.get("symbol"),
                    "result": outcome.get("result"),
                    "directional_move_pct": round(directional_move, 2),
                    "quality_cohort": quality_cohort,
                    "source": str(news.get("publisher") or evidence.get("publisher") or "Unbekannte Quelle"),
                    "event_type": str(news.get("event_type") or "unknown").lower(),
                }
            )

        def group(field: str) -> List[Dict[str, Any]]:
            buckets: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                buckets.setdefault(str(row.get(field) or "unknown"), []).append(row)
            grouped: List[Dict[str, Any]] = []
            for label, items in buckets.items():
                hits = sum(1 for item in items if item.get("result") == "hit")
                misses = sum(1 for item in items if item.get("result") == "miss")
                neutral = sum(1 for item in items if item.get("result") == "neutral")
                decisive = hits + misses
                evaluated = len(items)
                grouped.append(
                    {
                        "label": label,
                        "evaluated": evaluated,
                        "decisive": decisive,
                        "hits": hits,
                        "misses": misses,
                        "neutral": neutral,
                        "hit_rate": round((hits / max(1, decisive)) * 100, 1),
                        "decision_rate": round((decisive / max(1, evaluated)) * 100, 1),
                        "avg_directional_move_pct": round(
                            sum(float(item.get("directional_move_pct") or 0) for item in items) / max(1, evaluated),
                            2,
                        ),
                        "evidence_status": "usable" if evaluated >= 10 else "building" if evaluated >= 5 else "insufficient",
                    }
                )
            grouped.sort(key=lambda item: (-int(item.get("evaluated") or 0), -float(item.get("hit_rate") or 0)))
            return grouped

        quality_cohorts = group("quality_cohort")
        hits = sum(1 for row in rows if row.get("result") == "hit")
        misses = sum(1 for row in rows if row.get("result") == "miss")
        neutral = sum(1 for row in rows if row.get("result") == "neutral")
        decisive = hits + misses
        overall_hit_rate = round((hits / max(1, decisive)) * 100, 1)
        strict = next((item for item in quality_cohorts if item.get("label") == "strict_gate_confirmed"), None)
        strict_lift = None
        if strict and int(strict.get("decisive") or 0) >= 3 and decisive >= 3:
            strict_lift = round(float(strict.get("hit_rate") or 0) - overall_hit_rate, 1)
        summary = {
            "forecasts": len(top_news),
            "evaluated_24h": len(rows),
            "pending_24h": pending_24h,
            "hits": hits,
            "misses": misses,
            "neutral": neutral,
            "hit_rate": overall_hit_rate,
            "avg_directional_move_pct": round(
                sum(float(row.get("directional_move_pct") or 0) for row in rows) / max(1, len(rows)),
                2,
            ) if rows else None,
            "strict_gate_lift_pct_points": strict_lift,
            "sample_unit": "Eine Meldung mit genau einem 24-Stunden-Ergebnis.",
            "policy": "Shadow-Studie ohne Position, PnL oder Echtgeldwirkung.",
        }
        event_types = group("event_type")
        for row in event_types:
            row["paper_prior_score_delta"] = self._news_shadow_event_prior_delta(row)
        return {
            "summary": summary,
            "quality_cohorts": quality_cohorts,
            "sources": group("source"),
            "event_types": event_types,
        }

    def _news_shadow_event_prior_delta(self, row: Dict[str, Any]) -> int:
        """Return a deliberately small prior from one canonical outcome per signal."""
        evaluated = int(row.get("evaluated") or 0)
        decisive = int(row.get("decisive") or 0)
        hit_rate = float(row.get("hit_rate") or 0)
        avg_move = float(row.get("avg_directional_move_pct") or 0)
        if evaluated < 10 or decisive < 8:
            return 0
        if hit_rate <= 35 and avg_move < 0:
            return -4
        if hit_rate >= 60 and avg_move >= 0.25:
            return 2
        return 0

    def _apply_news_shadow_learning(
        self,
        playbooks: List[Dict[str, Any]],
        news_shadow_lab: Dict[str, Any],
    ) -> None:
        event_rows = {
            str(row.get("label") or "").strip().lower(): row
            for row in news_shadow_lab.get("event_types", [])
        }
        for item in playbooks:
            if str(item.get("setup_type") or "") != "confirmed_news_event":
                continue
            evidence = item.get("news_evidence") if isinstance(item.get("news_evidence"), dict) else {}
            event_type = str(evidence.get("event_type") or "unknown").strip().lower()
            row = event_rows.get(event_type)
            if not row:
                continue
            direct_delta = int((item.get("news_learning_adjustment") or {}).get("score_delta") or 0)
            prior_delta = int(row.get("paper_prior_score_delta") or 0)
            applied_delta = 0 if direct_delta else prior_delta
            if applied_delta:
                item.setdefault("raw_score", item.get("score"))
                item["score"] = max(0, min(100, round(float(item.get("score") or 0) + applied_delta, 2)))
            item["news_shadow_prior"] = {
                "event_type": event_type,
                "evaluated_24h": row.get("evaluated"),
                "decisive_24h": row.get("decisive"),
                "hit_rate": row.get("hit_rate"),
                "avg_directional_move_pct": row.get("avg_directional_move_pct"),
                "prior_score_delta": prior_delta,
                "applied_score_delta": applied_delta,
                "direct_trade_evidence_precedence": bool(direct_delta),
                "real_money_ready": False,
                "note": (
                    "Direkte geschlossene News-Trades haben Vorrang; Shadow-Prior wird nicht zusätzlich addiert."
                    if direct_delta
                    else "Sekundärer Eventtyp-Prior aus genau einem 24-Stunden-Ergebnis je Meldung."
                ),
            }

    def _refresh_playbook_decision_state(
        self,
        playbooks: List[Dict[str, Any]],
        rules: Dict[str, Any],
    ) -> None:
        """Recompute every score-sensitive gate after learning changes a playbook."""
        for item in playbooks:
            rule_state = self._get_do_not_trade_state(item, rules)
            item["do_not_trade_reasons"] = rule_state["blocked"]
            item["leverage_warnings"] = rule_state["leverage"]
            item["tradeable"] = len(rule_state["blocked"]) == 0
            item["decision_framework"] = self._build_decision_framework(item)

    def _apply_news_evidence_learning(
        self,
        playbooks: List[Dict[str, Any]],
        news_performance: Dict[str, Any],
    ) -> None:
        source_rows = {
            str(item.get("label") or "").strip().lower(): item
            for item in news_performance.get("sources", [])
        }
        event_rows = {
            str(item.get("label") or "").strip().lower(): item
            for item in news_performance.get("event_types", [])
        }
        for item in playbooks:
            if str(item.get("setup_type") or "") != "confirmed_news_event":
                continue
            evidence = item.get("news_evidence") if isinstance(item.get("news_evidence"), dict) else {}
            source_key = str(evidence.get("publisher") or "").strip().lower()
            event_key = str(evidence.get("event_type") or "unknown").strip().lower()
            matched = [row for row in (source_rows.get(source_key), event_rows.get(event_key)) if row]
            if not matched:
                continue
            # Source and event rows usually contain overlapping trades. Average them
            # so the same realized outcome is not counted twice.
            raw_delta = sum(int(row.get("score_delta") or 0) for row in matched) / max(1, len(matched))
            score_delta = max(-6, min(3, int(round(raw_delta))))
            notes = [
                f"{row.get('dimension')} {row.get('label')}: {row.get('trades')} Abschlüsse, "
                f"Erwartung {row.get('performance', {}).get('expectancy_pct', 0)}%."
                for row in matched
            ]
            if score_delta:
                item.setdefault("raw_score", item.get("score"))
                item["score"] = max(0, min(100, round(float(item.get("score") or 0) + score_delta, 2)))
            item["news_learning_adjustment"] = {
                "score_delta": score_delta,
                "source": source_key or None,
                "event_type": event_key,
                "minimum_sample": 10,
                "notes": notes,
                "real_money_ready": False,
            }

    def _build_learning_context_performance(self, closed_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for trade in closed_trades:
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            context = ticket.get("learning_context") if isinstance(ticket.get("learning_context"), dict) else {}
            if not context:
                continue
            mode = str(context.get("autopilot_mode") or "unknown")
            day_status = str(context.get("account_day_status") or "unknown")
            queue_status = str(context.get("account_queue_status") or "unknown")
            key = f"{day_status}:{queue_status}:{mode}"
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "autopilot_mode": mode,
                    "account_day_status": day_status,
                    "account_queue_status": queue_status,
                    "risk_multiplier_sum": 0.0,
                    "trades": [],
                },
            )
            try:
                bucket["risk_multiplier_sum"] += float(context.get("risk_multiplier") or 0)
            except (TypeError, ValueError):
                pass
            bucket["trades"].append(trade)

        rows: List[Dict[str, Any]] = []
        for bucket in buckets.values():
            trades = bucket.pop("trades")
            performance = build_trade_performance(trades)
            count = max(1, len(trades))
            rows.append(
                {
                    **bucket,
                    "trades": len(trades),
                    "avg_risk_multiplier": round(float(bucket.get("risk_multiplier_sum") or 0) / count, 3),
                    "performance": performance,
                    "summary": (
                        f"{bucket['account_day_status']} / {bucket['account_queue_status']} / {bucket['autopilot_mode']}: "
                        f"{len(trades)} geschlossene Lerntrades, Treffer {performance.get('win_rate', 0)}%, "
                        f"Erwartung {performance.get('expectancy_value', 0)} pro Trade."
                    ),
                }
            )
        rows.sort(
            key=lambda item: (
                -int(item.get("trades") or 0),
                -float((item.get("performance") or {}).get("expectancy_value") or 0),
                str(item.get("key") or ""),
            )
        )
        return rows[:8]

    def _build_market_regime_performance(self, closed_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        dimensions = ("trend", "volatility", "rates", "dollar", "risk_appetite", "breadth")
        buckets: Dict[str, Dict[str, List[Dict[str, Any]]]] = {dimension: {} for dimension in dimensions}
        captured_trades = 0
        for trade in closed_trades:
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            regime = ticket.get("entry_market_regime") if isinstance(ticket.get("entry_market_regime"), dict) else {}
            if not regime:
                continue
            captured_trades += 1
            for dimension in dimensions:
                state = regime.get(dimension) if isinstance(regime.get(dimension), dict) else {}
                label = str(state.get("label") or "unavailable").strip().lower() or "unavailable"
                buckets[dimension].setdefault(label, []).append(trade)

        rows: List[Dict[str, Any]] = []
        for dimension in dimensions:
            for label, trades in buckets[dimension].items():
                performance = build_trade_performance(trades)
                sample_size = int(performance.get("sample_size") or 0)
                rows.append(
                    {
                        "dimension": dimension,
                        "label": label,
                        "trades": sample_size,
                        "performance": performance,
                        "readiness": "usable" if sample_size >= 30 else "building" if sample_size >= 10 else "insufficient_sample",
                        "minimum_usable_sample": 30,
                    }
                )
        rows.sort(key=lambda item: (str(item["dimension"]), -int(item["trades"]), str(item["label"])))
        return {
            "captured_closed_trades": captured_trades,
            "total_closed_trades": len(closed_trades),
            "coverage_pct": round((captured_trades / len(closed_trades)) * 100, 1) if closed_trades else 0.0,
            "rows": rows,
            "policy": "Marktregime wird nur am Entry eingefroren; Auswertung ab 30 geschlossenen Trades je Regime belastbar.",
        }

    def _build_strategy_dimension_performance(self, closed_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        buckets: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for trade in closed_trades:
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            regime = ticket.get("entry_market_regime") if isinstance(ticket.get("entry_market_regime"), dict) else {}
            appetite = regime.get("risk_appetite") if isinstance(regime.get("risk_appetite"), dict) else {}
            score = float(trade.get("confidence_score") or ticket.get("confidence_score") or 0)
            score_band = "90+" if score >= 90 else "78-89" if score >= 78 else "60-77" if score >= 60 else "<60"
            source = str(
                trade.get("entry_source_label")
                or ticket.get("entry_source_label")
                or ticket.get("source_label")
                or "unknown"
            )
            values = {
                "setup": str(trade.get("setup_type") or "unknown"),
                "source": source,
                "score_band": score_band,
                "risk_bucket": self._paper_risk_bucket(trade),
                "market_regime": str(appetite.get("label") or "unavailable"),
            }
            for dimension, label in values.items():
                buckets.setdefault((dimension, label), []).append(trade)

        rows: List[Dict[str, Any]] = []
        for (dimension, label), trades in buckets.items():
            performance = build_trade_performance(trades)
            sample_size = int(performance.get("sample_size") or 0)
            rows.append(
                {
                    "dimension": dimension,
                    "label": label,
                    "trades": sample_size,
                    "performance": performance,
                    "readiness": "usable" if sample_size >= 30 else "building" if sample_size >= 10 else "insufficient_sample",
                    "minimum_usable_sample": 30,
                }
            )
        rows.sort(key=lambda item: (str(item["dimension"]), -int(item["trades"]), str(item["label"])))
        return {
            "rows": rows,
            "closed_trades": len(closed_trades),
            "dimensions": ["setup", "market_regime", "source", "score_band", "risk_bucket"],
            "policy": "Keine Strategie-Freigabe unter 30 geschlossenen Trades je Segment; Trefferquote allein reicht nicht.",
        }

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
        leveraged_product = ticket.get("leveraged_product") if isinstance(ticket.get("leveraged_product"), dict) else {}
        payout_multiplier = 1.0 if leveraged_product.get("leverage_is_embedded_in_product_price") is True else leverage
        execution_model = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        current_market = (
            {}
            if row.get("status") == "closed"
            else self._get_stored_option_contract_quote(ticket)
            if is_option
            else self._get_market_snapshot(
                row.get("ticker"),
                since=row.get("opened_at"),
                stop_price=row.get("stop_price"),
                target_price=row.get("target_price"),
                direction=row.get("direction"),
            )
        )
        current_reference = current_market.get("price")
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
        row["current_market_data"] = current_market
        if is_option:
            row["option_quote_status"] = current_market.get("status") or "unavailable"
            row["option_quote_reason"] = current_market.get("reason")
            row["option_contract_identity"] = ticket.get("option_contract_identity")
        direction_multiplier = -1 if row.get("direction") == "short" else 1
        contract_multiplier = float(
            row.get("contract_multiplier")
            or ticket.get("contract_multiplier")
            or (100 if is_option else 1)
        )
        invested_value = round(entry * quantity * payout_multiplier * contract_multiplier, 2)
        row["invested_value"] = invested_value
        row["position_notional_value"] = invested_value

        if row.get("status") == "closed":
            exit_price = float(row.get("closed_price") or 0)
            pnl_pct = self._calc_return_pct(entry, exit_price, direction_multiplier, payout_multiplier)
            pnl_value = round(((exit_price - entry) * quantity * direction_multiplier * payout_multiplier * contract_multiplier), 2)
            row["realized_pnl_pct"] = pnl_pct
            row["realized_pnl_value"] = pnl_value
            row["unrealized_pnl_pct"] = None
            row["unrealized_pnl_value"] = None
            row["current_value"] = None
            row["final_value"] = round(invested_value + pnl_value, 2)
            row["result_value_delta"] = pnl_value
            row["result_label"] = "more" if pnl_value > 0 else "less" if pnl_value < 0 else "flat"
        else:
            pnl_pct = self._calc_return_pct(entry, current_price, direction_multiplier, payout_multiplier) if current_price else None
            pnl_value = (
                round(((current_price - entry) * quantity * direction_multiplier * payout_multiplier * contract_multiplier), 2)
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
        configured_max_holding_days = int(trade.get("max_holding_days") or 0)
        setup_type = str(trade.get("setup_type") or "").lower()
        default_holding_days = 0
        if setup_type == "confirmed_news_event":
            default_holding_days = 3
        elif setup_type == "crypto_flow":
            default_holding_days = 7
        elif setup_type == "insider_follow":
            default_holding_days = 10
        elif setup_type == "etf_momentum":
            default_holding_days = 14
        elif setup_type == "political_copy_delay":
            default_holding_days = 15
        elif setup_type.startswith("commodity_"):
            default_holding_days = 7
        elif setup_type.startswith("option_"):
            default_holding_days = 10
        max_holding_days = configured_max_holding_days or default_holding_days
        holding_period_source = "trade_config" if configured_max_holding_days > 0 else "strategy_policy"
        opened_at = self._as_utc_naive_datetime(trade.get("opened_at"))
        if setup_type == "confirmed_news_event":
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            news_evidence = ticket.get("news_evidence") if isinstance(ticket.get("news_evidence"), dict) else {}
            correction = (
                news_evidence.get("correction_status")
                if isinstance(news_evidence.get("correction_status"), dict)
                else {}
            )
            correction_state = str(correction.get("status") or "")
            if correction_state in {"retracted_or_withdrawn", "correction_detected", "source_unavailable"}:
                reporting = (
                    news_evidence.get("reporting_source")
                    if isinstance(news_evidence.get("reporting_source"), dict)
                    else {}
                )
                affected = next(
                    (
                        item
                        for item in (correction.get("checks") or [])
                        if isinstance(item, dict) and item.get("actionable")
                    ),
                    {},
                )
                return {
                    "status": "news_source_invalidated",
                    "action": "close_review",
                    "decision_grade": "exit",
                    "next_check": (
                        "Originalquelle und berichtende Quelle manuell vergleichen. Paper-Exit nur nach Prüfung "
                        "dokumentieren; die Kursbewegung beweist keine Nachrichtenkausalität."
                    ),
                    "summary": (
                        "Die gespeicherte News-Grundlage wurde nach dem Entry korrigiert, zurückgezogen "
                        "oder ist dauerhaft nicht mehr auffindbar. Die ursprüngliche Event-These ist neu zu bewerten."
                    ),
                    "source_status": correction_state,
                    "source_url": affected.get("url") or reporting.get("url") or news_evidence.get("source_url"),
                    "source_type": affected.get("source_type"),
                    "source_checked_at": correction.get("checked_at"),
                    "causality_proven": False,
                    "risk_distance_pct": None,
                    "target_progress_pct": None,
                }
        if max_holding_days > 0 and opened_at is not None:
            expires_at = opened_at + timedelta(days=max_holding_days)
            if datetime.now(timezone.utc).replace(tzinfo=None) >= expires_at:
                return {
                    "status": "holding_period_expired",
                    "action": "price_and_close_review",
                    "decision_grade": "exit",
                    "next_check": (
                        "Aktuellen Optionspreis und Spread erfassen, Paper-Trade schließen "
                        "und die Zeitinvalidierung journalisieren."
                        if trade.get("asset_class") == "option"
                        else "Paper-Trade schließen und die Zeitinvalidierung journalisieren."
                    ),
                    "summary": (
                        f"Maximale Haltedauer von {max_holding_days} Tagen ist erreicht. "
                        "Ohne validierte aktuelle Quote erfolgt kein erfundener Auto-Exit."
                    ),
                    "risk_distance_pct": None,
                    "target_progress_pct": None,
                    "triggered_at": expires_at.isoformat(),
                    "trigger_reference_price": None,
                    "max_holding_days": max_holding_days,
                    "holding_period_source": holding_period_source,
                }
        if not entry or current in (None, 0):
            return {
                "status": "pending_data",
                "action": "wait",
                "decision_grade": "wait",
                "next_check": "Auf verlässlichen aktuellen Kurs warten, bevor die Paper-Position geändert wird.",
                "summary": "Aktueller Kurs fehlt; Paper-Trade weiter prüfen.",
            }

        current_price = float(current)
        current_market = (
            trade.get("current_market_data")
            if isinstance(trade.get("current_market_data"), dict)
            else {}
        )
        monitoring_low = current_market.get("monitoring_low")
        monitoring_high = current_market.get("monitoring_high")
        monitoring_trigger = current_market.get("monitoring_trigger")
        has_ordered_trigger = monitoring_trigger in {"stop_hit", "target_hit"}
        monitored_low_price = current_price if monitoring_low is None else float(monitoring_low)
        monitored_high_price = current_price if monitoring_high is None else float(monitoring_high)
        stop_price = float(stop) if stop not in (None, 0) else None
        target_price = float(target) if target not in (None, 0) else None
        favorable_pct = float(trade.get("unrealized_pnl_pct") or 0)
        is_news_event = str(trade.get("setup_type") or "") == "confirmed_news_event"
        elapsed_hours = (
            max(
                0.0,
                (datetime.now(timezone.utc).replace(tzinfo=None) - opened_at).total_seconds() / 3600,
            )
            if opened_at is not None
            else None
        )
        risk_distance = None
        target_progress = None
        action = "hold"
        status = "monitor"
        summary = "Paper-Position halten, solange der Trigger gültig bleibt."

        if stop_price is not None:
            if direction == "short":
                stop_hit = (
                    monitoring_trigger == "stop_hit"
                    if has_ordered_trigger
                    else monitored_high_price >= stop_price
                )
                risk_distance = ((stop_price - current_price) / entry) * 100
            else:
                stop_hit = (
                    monitoring_trigger == "stop_hit"
                    if has_ordered_trigger
                    else monitored_low_price <= stop_price
                )
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
                    "triggered_at": current_market.get("monitoring_triggered_at"),
                    "trigger_reference_price": current_market.get("monitoring_trigger_price"),
                }
            if risk_distance is not None and risk_distance <= 0.6:
                status = "near_stop"
                action = "reduce_or_close_review"
                summary = "Kurs ist nahe am Stop. Nicht aufstocken; Exit-Prüfung vorbereiten, falls Schwäche anhält."

        if target_price is not None:
            if direction == "short":
                target_hit = (
                    monitoring_trigger == "target_hit"
                    if has_ordered_trigger
                    else monitored_low_price <= target_price
                )
                total_reward = max(0.0001, entry - target_price)
                achieved = entry - current_price
            else:
                target_hit = (
                    monitoring_trigger == "target_hit"
                    if has_ordered_trigger
                    else monitored_high_price >= target_price
                )
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
                    "triggered_at": current_market.get("monitoring_triggered_at"),
                    "trigger_reference_price": current_market.get("monitoring_trigger_price"),
                }
            if target_progress >= 75 and favorable_pct > 0 and status == "monitor":
                status = "near_target"
                action = "protect_profit_review"
                summary = "Trade ist nahe am Ziel. Prüfen, ob Gewinn geschützt oder Paper-Plan enger geführt wird."

        if is_news_event and favorable_pct <= -0.75:
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            news_evidence = ticket.get("news_evidence") if isinstance(ticket.get("news_evidence"), dict) else {}
            return {
                "status": "news_reaction_failed",
                "action": "close_review",
                "decision_grade": "exit",
                "next_check": "Paper-Trade schließen; Reaktionsrichtung, Entry-Timing und Quellenlage journalisieren.",
                "summary": "Die bestätigte News-Reaktion ist deutlich zurückgelaufen. Event-These nicht bis zum normalen Stop aussitzen.",
                "risk_distance_pct": round(risk_distance, 2) if risk_distance is not None else None,
                "target_progress_pct": round(target_progress, 1) if target_progress is not None else None,
                "unrealized_pnl_pct": round(favorable_pct, 2),
                "elapsed_hours": round(elapsed_hours, 1) if elapsed_hours is not None else None,
                "source_url": news_evidence.get("source_url"),
                "causality_proven": False,
            }

        if (
            is_news_event
            and elapsed_hours is not None
            and elapsed_hours >= 24
            and favorable_pct < 0.35
            and status == "monitor"
        ):
            status = "news_momentum_stalled"
            action = "thesis_check"
            summary = "Nach 24 Stunden fehlt nachhaltiger News-Follow-through. These und Kapitalbindung erneut prüfen."
        elif favorable_pct <= -1.5 and status == "monitor":
            status = "weak_follow_through"
            action = "thesis_check"
            summary = "Negative Anschlussbewegung. Prüfen, ob der ursprüngliche Trigger versagt."
        elif favorable_pct >= 1.5 and status == "monitor":
            status = "working"
            action = "hold_with_plan"
            summary = "Trade funktioniert. Nur halten, solange die Invalidierung nicht ausgelöst ist."

        decision_grade = "hold"
        next_check = "Geplanten Stop und Ziel halten; nach dem nächsten relevanten Kursupdate erneut prüfen."
        if status in {"near_stop", "weak_follow_through", "news_momentum_stalled"}:
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
            "elapsed_hours": round(elapsed_hours, 1) if elapsed_hours is not None else None,
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
        estimated_cost_value = cost_per_unit * max(0.0, float(quantity or 0)) * max(0.0, float(contract_multiplier or 1))
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
            "market_source": (market_data or {}).get("source"),
            "contract_symbol": (market_data or {}).get("contract_symbol"),
            "quote_side": (market_data or {}).get("quote_side"),
            "spread_pct": (market_data or {}).get("spread_pct"),
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

    def _get_market_snapshot(
        self,
        ticker: Optional[str],
        since: Any = None,
        stop_price: Any = None,
        target_price: Any = None,
        direction: Any = None,
    ) -> Dict[str, Any]:
        if not ticker:
            return {}
        try:
            hist, interval = self._load_market_history(ticker)
            if hist is None or hist.empty:
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
            average_volume = None
            if len(volume_values):
                if interval == "5m":
                    daily_volume: Dict[Any, float] = {}
                    for bar_timestamp, value in volume_values.items():
                        bar_datetime = self._as_utc_naive_datetime(bar_timestamp)
                        if bar_datetime is None:
                            continue
                        day = bar_datetime.date()
                        daily_volume[day] = daily_volume.get(day, 0.0) + float(value or 0)
                    daily_totals = [value for _, value in sorted(daily_volume.items()) if value > 0]
                    completed_totals = daily_totals[:-1] if len(daily_totals) > 1 else daily_totals
                    if completed_totals:
                        average_volume = sum(completed_totals[-5:]) / len(completed_totals[-5:])
                else:
                    average_volume = float(volume_values.tail(5).mean())

            monitoring_low = None
            monitoring_high = None
            monitoring_trigger = None
            monitoring_triggered_at = None
            monitoring_trigger_price = None
            since_datetime = self._as_utc_naive_datetime(since)
            if interval == "5m" and since_datetime is not None:
                monitored_positions = []
                for position, bar_timestamp in enumerate(hist.index):
                    bar_datetime = self._as_utc_naive_datetime(bar_timestamp)
                    if bar_datetime is not None and bar_datetime >= since_datetime:
                        monitored_positions.append(position)
                if monitored_positions:
                    monitored = hist.iloc[monitored_positions[0]:]
                    lows = monitored["Low"].dropna() if "Low" in monitored else []
                    highs = monitored["High"].dropna() if "High" in monitored else []
                    monitoring_low = float(lows.min()) if len(lows) else None
                    monitoring_high = float(highs.max()) if len(highs) else None
                    normalized_direction = str(direction or "").lower()
                    stop_barrier = float(stop_price) if stop_price not in (None, 0) else None
                    target_barrier = float(target_price) if target_price not in (None, 0) else None
                    if normalized_direction in {"long", "short"} and (
                        stop_barrier is not None or target_barrier is not None
                    ):
                        for bar_timestamp, bar in monitored.iterrows():
                            try:
                                bar_low = float(bar.get("Low"))
                                bar_high = float(bar.get("High"))
                            except (TypeError, ValueError):
                                continue
                            if normalized_direction == "short":
                                stop_touched = stop_barrier is not None and bar_high >= stop_barrier
                                target_touched = target_barrier is not None and bar_low <= target_barrier
                            else:
                                stop_touched = stop_barrier is not None and bar_low <= stop_barrier
                                target_touched = target_barrier is not None and bar_high >= target_barrier
                            if not stop_touched and not target_touched:
                                continue
                            monitoring_trigger = "stop_hit" if stop_touched else "target_hit"
                            if monitoring_trigger == "stop_hit":
                                monitoring_trigger_price = stop_barrier
                                try:
                                    bar_open = float(bar.get("Open"))
                                except (TypeError, ValueError):
                                    bar_open = None
                                if bar_open is not None and bar_open > 0:
                                    monitoring_trigger_price = (
                                        max(float(stop_barrier), bar_open)
                                        if normalized_direction == "short"
                                        else min(float(stop_barrier), bar_open)
                                    )
                            else:
                                monitoring_trigger_price = target_barrier
                            triggered_datetime = self._as_utc_naive_datetime(bar_timestamp)
                            monitoring_triggered_at = (
                                triggered_datetime.isoformat()
                                if triggered_datetime is not None
                                else None
                            )
                            break

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
                "source": "yfinance_intraday" if interval == "5m" else "yfinance_daily",
                "interval": interval,
                "age_hours": round(age_hours, 2),
                "freshness": "fresh" if age_hours <= max_age_hours else "stale",
                "average_volume_5d": round(average_volume, 2) if average_volume is not None else None,
                "average_dollar_volume_5d": round(dollar_volume, 2) if dollar_volume is not None else None,
                "volume_basis": "reported_quote_volume" if is_crypto_pair else "shares_times_price",
                "liquidity_status": liquidity_status,
                "minimum_dollar_volume": min_dollar_volume,
                "monitoring_since": since_datetime.isoformat() if monitoring_low is not None and since_datetime else None,
                "monitoring_low": round(monitoring_low, 4) if monitoring_low is not None else None,
                "monitoring_high": round(monitoring_high, 4) if monitoring_high is not None else None,
                "monitoring_trigger": monitoring_trigger,
                "monitoring_triggered_at": monitoring_triggered_at,
                "monitoring_trigger_price": (
                    round(float(monitoring_trigger_price), 4)
                    if monitoring_trigger_price is not None
                    else None
                ),
            }
        except Exception:
            return {}

    def _load_market_history(self, ticker: str):
        cache = getattr(self, "_market_history_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._market_history_cache = cache

        cache_key = str(ticker).strip().upper()
        try:
            ttl_seconds = max(
                5.0,
                float(os.getenv("PAPER_MARKET_HISTORY_CACHE_SECONDS", "120")),
            )
        except (TypeError, ValueError):
            ttl_seconds = 120.0
        now_monotonic = time.monotonic()
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and now_monotonic - float(cached.get("stored_at") or 0) <= ttl_seconds:
            return cached.get("history"), str(cached.get("interval") or "1d")

        ticker_client = yf.Ticker(ticker)
        history = None
        interval = "5m"
        try:
            history = ticker_client.history(period="5d", interval=interval)
        except Exception:
            history = None
        if history is None or history.empty:
            interval = "1d"
            try:
                history = ticker_client.history(period="5d", interval=interval)
            except Exception:
                history = None
        if history is not None and not history.empty:
            cache[cache_key] = {
                "stored_at": now_monotonic,
                "history": history,
                "interval": interval,
            }
        return history, interval

    def _get_last_price(self, ticker: Optional[str]) -> Optional[float]:
        return self._get_market_snapshot(ticker).get("price")

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def _as_utc_naive_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        try:
            parsed = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
            if not isinstance(parsed, datetime):
                parsed = datetime.fromisoformat(str(parsed).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except Exception:
            return None
