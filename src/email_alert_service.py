"""
Email alert service for signal watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from html import escape, unescape
import hashlib
import json
import math
import os
import re
import smtplib
import time
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse
import requests

from src.public_signal_service import PublicSignalService
from src.session_list_service import SessionListService
from src.signal_score_service import SignalScoreService
from src.storage import PortfolioManager
from src.morning_brief_service import MorningBriefService
from src.provider_observability import classify_provider_error, record_provider_result


DEFAULT_MORNING_BRIEF_TIME = "08:30"
DEFAULT_EUROPE_OPEN_BRIEF_TIME = "08:40"
DEFAULT_MIDDAY_BRIEF_TIME = "12:30"
DEFAULT_US_OPEN_BRIEF_TIME = "15:10"
DEFAULT_EUROPE_CLOSE_BRIEF_TIME = "17:30"
DEFAULT_CLOSE_RECAP_TIME = "21:45"
DEFAULT_US_CLOSE_BRIEF_TIME = "22:15"
DEFAULT_DAILY_OVERVIEW_TIME = "20:30"


@dataclass
class EmailAlertConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_to: str
    smtp_starttls: bool
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    scheduled_briefs_enabled: bool
    daily_overview_enabled: bool = False


class EmailAlertService:
    def __init__(
        self,
        portfolio_manager: PortfolioManager,
        public_signal_service: PublicSignalService,
        morning_brief_service: MorningBriefService | None = None,
        session_list_service: SessionListService | None = None,
        signal_score_service: SignalScoreService | None = None,
        push_service: "Any | None" = None,
        forecast_learning_service: "Any | None" = None,
    ) -> None:
        self.portfolio_manager = portfolio_manager
        self.public_signal_service = public_signal_service
        self.morning_brief_service = morning_brief_service or MorningBriefService()
        self.session_list_service = session_list_service or SessionListService()
        self.signal_score_service = signal_score_service or SignalScoreService()
        self.push_service = push_service
        self.forecast_learning_service = forecast_learning_service
        self._brief_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="brief-send")

    def get_config(self) -> EmailAlertConfig:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_from = os.getenv("SMTP_FROM", "").strip() or smtp_user
        smtp_to = os.getenv("ALERT_EMAIL_TO", "").strip()
        enabled = os.getenv("SIGNAL_ALERTS_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return EmailAlertConfig(
            enabled=enabled,
            smtp_host=os.getenv("SMTP_HOST", "").strip(),
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
            smtp_from=smtp_from,
            smtp_to=smtp_to,
            smtp_starttls=os.getenv("SMTP_STARTTLS", "true").strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            },
            telegram_enabled=os.getenv("TELEGRAM_ALERTS_ENABLED", "false").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            },
            telegram_bot_token=self._normalize_telegram_bot_token(
                os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            ),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            scheduled_briefs_enabled=os.getenv("SCHEDULED_BRIEFS_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            daily_overview_enabled=os.getenv("DAILY_OVERVIEW_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
        )

    def get_notification_status(self) -> Dict[str, Any]:
        config = self.get_config()
        macro_audit: Dict[str, Any] = {}
        try:
            macro_audit = json.loads(self.portfolio_manager.get_app_setting("macro_alert_last_audit", "{}") or "{}")
            if not isinstance(macro_audit, dict):
                macro_audit = {}
        except (TypeError, ValueError, json.JSONDecodeError):
            macro_audit = {}
        return {
            "alerts_enabled": config.enabled,
            "email": {
                "configured": False,
                "disabled": True,
                "message": "Email delivery is disabled. Telegram is the only briefing channel.",
            },
            "telegram": {
                "enabled": config.telegram_enabled,
                "configured": bool(config.telegram_bot_token and config.telegram_chat_id),
            },
            "browser_push": {
                "enabled": os.getenv("BROWSER_PUSH_ENABLED", "false").strip().lower()
                in {"1", "true", "yes", "on"},
                "channel": "browser"
                if os.getenv("BROWSER_PUSH_ENABLED", "false").strip().lower()
                in {"1", "true", "yes", "on"}
                else "telegram_only",
            },
            "macro_alerts": {
                "enabled": os.getenv("CRITICAL_MARKET_ALERTS_ENABLED", "true").strip().lower()
                not in {"0", "false", "no", "off"},
                "channel": "telegram",
                "min_score": self._safe_int_env("CRITICAL_MARKET_ALERT_MIN_SCORE", 82, minimum=1),
                "cooldown_hours": self._safe_int_env("MACRO_ALERT_COOLDOWN_HOURS", 3, minimum=1),
                "max_items": self._safe_int_env("CRITICAL_MARKET_ALERT_MAX_ITEMS", 5, minimum=1),
                "last_audit": macro_audit,
            },
            "schedule": {
                "enabled": config.scheduled_briefs_enabled,
                "timezone": os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"),
                "weekdays": os.getenv("BRIEF_SCHEDULE_WEEKDAYS", "mon,tue,wed,thu,fri"),
                "morning": os.getenv("MORNING_BRIEF_TIME", DEFAULT_MORNING_BRIEF_TIME),
                "europe_open": os.getenv("EUROPE_OPEN_BRIEF_TIME", DEFAULT_EUROPE_OPEN_BRIEF_TIME),
                "midday": os.getenv("MIDDAY_BRIEF_TIME", DEFAULT_MIDDAY_BRIEF_TIME),
                "us_open": os.getenv("US_OPEN_BRIEF_TIME", DEFAULT_US_OPEN_BRIEF_TIME),
                "close_recap": os.getenv("CLOSE_RECAP_TIME", DEFAULT_CLOSE_RECAP_TIME),
                "on_time_window_minutes": self._brief_on_time_window_minutes(),
                "delivery_grace_minutes": self._brief_delivery_grace_minutes(),
                "daily_overview": {
                    "enabled": config.daily_overview_enabled,
                    "time": os.getenv("DAILY_OVERVIEW_TIME", DEFAULT_DAILY_OVERVIEW_TIME),
                    "channel": "telegram",
                    "priority": "summary_only",
                    "immediate_risk_alerts_independent": True,
                    "delivery_grace_minutes": self._safe_int_env(
                        "DAILY_OVERVIEW_GRACE_MINUTES", 180, minimum=1
                    ),
                    "last_result": self.get_brief_job_status("daily-overview"),
                },
            },
        }

    def check_and_send_alerts(self, force: bool = False) -> Dict[str, Any]:
        config = self.get_config()
        if not force and not config.enabled:
            return {"status": "disabled", "message": "Signal alerts are disabled."}

        self._validate_config(config)
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        settings = self.portfolio_manager.get_signal_score_settings()
        new_events = self._extract_new_events(snapshot, settings)

        if not new_events:
            return {"status": "ok", "sent": 0, "message": "No new events."}

        self._send_notifications(
            config,
            new_events,
            subject=f"Signal Alert: {len(new_events)} neue Watchlist-Signale",
        )
        self.portfolio_manager.mark_signal_events_sent(new_events)
        return {"status": "ok", "sent": len(new_events), "message": "Telegram alerts sent."}

    def check_and_send_critical_market_alerts(self, force: bool = False) -> Dict[str, Any]:
        """Send immediate Telegram alerts for high-impact market events.

        This is intentionally Telegram-only through _send_notifications; email delivery
        stays disabled for the private beta.
        """
        if not force and os.getenv("CRITICAL_MARKET_ALERTS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return {"status": "disabled", "message": "Critical market alerts are disabled."}

        config = self.get_config()
        self._validate_telegram_config(config)
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        brief = self.morning_brief_service.get_brief_fast(snapshot, False)
        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        events = self._extract_critical_market_events(brief, sent_keys)
        if not events:
            return {"status": "ok", "sent": 0, "message": "No critical market alerts."}

        selected_events = events[: self._safe_int_env("CRITICAL_MARKET_ALERT_MAX_ITEMS", 5, minimum=1)]
        self._send_notifications(config, selected_events, subject="Sofort-Alert: Wichtige Marktinformation")
        self.portfolio_manager.mark_signal_events_sent(selected_events)
        self._record_macro_alert_delivery(selected_events)
        return {"status": "ok", "sent": len(selected_events), "message": "Critical Telegram alerts sent."}

    def send_test_telegram(self) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        sample_event = {
            "event_key": f"test:{datetime.now().isoformat()}",
            "category": "test",
            "title": "Telegram Test Alert",
            "line": "Telegram ist aktiv. Briefings, Price Alerts und wichtige Marktinfos laufen ueber diesen Kanal.",
            "source_url": "",
        }
        self._send_notifications(config, [sample_event], subject="Test Alert: Telegram aktiv")
        return {"status": "ok", "message": "Telegram test sent."}

    def send_operational_alert(self, code: str, title: str, detail: str, action: str) -> Dict[str, Any]:
        """Send a deduplicated operational alert and persist it only after delivery."""
        cooldown_hours = self._safe_int_env("OPERATIONAL_ALERT_COOLDOWN_HOURS", 6, minimum=1)
        bucket = int(datetime.now().timestamp() // (cooldown_hours * 3600))
        event = {
            "event_key": f"operational:{code}:{bucket}",
            "category": "operational",
            "title": title,
            "line": f"{title}: {detail} | Aktion: {action}",
            "severity": "critical",
            "event_type": code,
        }
        if event["event_key"] in self.portfolio_manager.get_sent_signal_event_keys():
            return {"status": "deduplicated", "sent": 0, "event_key": event["event_key"]}
        config = self.get_config()
        self._validate_telegram_config(config)
        self._send_notifications(config, [event], subject="Broker Freund: Betriebsalarm")
        self.portfolio_manager.mark_signal_events_sent([event])
        return {"status": "ok", "sent": 1, "event_key": event["event_key"]}

    def send_test_email(self) -> Dict[str, Any]:
        """Backward-compatible endpoint name; delivery is Telegram-only."""
        return self.send_test_telegram()

    def send_price_alert(
        self,
        symbol: str,
        direction: str,
        target_price: float,
        current_price: float,
    ) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        normalized_symbol = (symbol or "").strip().upper()
        normalized_direction = (direction or "").strip().lower()
        if normalized_direction not in {"above", "below"}:
            raise ValueError("direction must be 'above' or 'below'")

        condition = ">=" if normalized_direction == "above" else "<="
        line = (
            f"{normalized_symbol} hit {current_price:.2f} "
            f"(Alert {condition} {float(target_price):.2f})"
        )
        event = {
            "event_key": f"price-alert:{normalized_symbol}:{datetime.now().isoformat()}",
            "category": "price_alert",
            "title": f"Price Alert {normalized_symbol}",
            "line": line,
            "source_url": "",
            "source_label": "Realtime monitor",
            "conviction_score": None,
        }
        self._send_notifications(
            config,
            [event],
            subject=f"Price Alert: {normalized_symbol}",
        )
        return {"status": "ok", "message": "Price alert notification sent."}

    def send_paper_learning_alerts(self, learning: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        if not force and os.getenv("PAPER_LEARNING_ALERTS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return {"status": "disabled", "message": "Paper-Learning-Alerts sind deaktiviert."}

        config = self.get_config()
        self._validate_telegram_config(config)
        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        events = self._extract_paper_learning_events(learning, sent_keys)
        if not events:
            return {"status": "ok", "sent": 0, "message": "Keine neuen Paper-Learning-Alerts."}

        self._send_notifications(config, events[:5], subject="Learning Alert: Paper-Trading Feedback")
        self.portfolio_manager.mark_signal_events_sent(events[:5])
        return {"status": "ok", "sent": len(events[:5]), "message": "Paper-Learning-Telegram-Alerts gesendet."}

    def send_paper_trade_opened_alerts(
        self,
        opened: List[Dict[str, Any]],
        selected: List[Dict[str, Any]],
        demo_account: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if os.getenv("PAPER_TRADE_OPEN_ALERTS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return {"status": "disabled", "message": "Paper-Trade-Open-Alerts sind deaktiviert."}
        if not opened:
            return {"status": "ok", "sent": 0, "message": "Keine geöffneten Paper-Trades."}

        config = self.get_config()
        self._validate_telegram_config(config)
        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        by_id = {str(item.get("id") or ""): item for item in selected or []}
        events: List[Dict[str, Any]] = []
        for trade in opened[:5]:
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            management = trade.get("management_plan") if isinstance(trade.get("management_plan"), dict) else {}
            source_label = str(trade.get("alert_source_label") or ticket.get("entry_source_label") or "Paper-Autopilot")
            playbook_id = str(trade.get("playbook_id") or "")
            selected_item = by_id.get(playbook_id) or next(
                (
                    item
                    for item in selected or []
                    if item.get("ticker") == trade.get("ticker")
                    and item.get("direction") == trade.get("direction")
                    and item.get("setup_type") == trade.get("setup_type")
                ),
                {},
            )
            event_key = f"paper-open:{trade.get('id') or datetime.utcnow().isoformat()}"
            if event_key in sent_keys:
                continue
            events.append(
                {
                    "event_key": event_key,
                    "category": "paper_trade_opened",
                    "title": f"Paper-Trade geöffnet: {trade.get('ticker')} {trade.get('direction')}",
                    "ticker": trade.get("ticker"),
                    "asset_class": trade.get("asset_class"),
                    "direction": trade.get("direction"),
                    "setup_type": trade.get("setup_type"),
                    "opened_at": trade.get("opened_at"),
                    "entry_price": trade.get("entry_price"),
                    "stop_price": trade.get("stop_price"),
                    "target_price": trade.get("target_price"),
                    "quantity": trade.get("quantity"),
                    "invested_value": trade.get("invested_value"),
                    "current_value": trade.get("current_value"),
                    "result_value_delta": trade.get("result_value_delta"),
                    "result_label": trade.get("result_label"),
                    "risk_reward": trade.get("risk_reward"),
                    "confidence_score": trade.get("confidence_score"),
                    "trigger": selected_item.get("trigger"),
                    "invalidation": selected_item.get("invalidation"),
                    "management_action": management.get("action"),
                    "management_next_check": management.get("next_check"),
                    "management_summary": management.get("summary"),
                    "strategy_context": selected_item.get("strategy_context") or {},
                    "suggested_max_loss_value": selected_item.get("suggested_max_loss_value"),
                    "account_equity": (demo_account or {}).get("equity"),
                    "account_cash_available": (demo_account or {}).get("cash_available_value"),
                    "account_open_exposure": (demo_account or {}).get("open_exposure_value"),
                    "account_net_pnl_value": (demo_account or {}).get("net_pnl_value"),
                    "account_net_pnl_pct": (demo_account or {}).get("net_pnl_pct"),
                    "account_performance": (demo_account or {}).get("performance") or {},
                    "account_capital_flow": (demo_account or {}).get("capital_flow") or {},
                    "account_asset_class_limits": (demo_account or {}).get("asset_class_limits") or {},
                    "account_cash_reserve_target": (demo_account or {}).get("cash_reserve_target_value"),
                    "trade_ticket": trade.get("trade_ticket") or selected_item.get("trade_ticket") or {},
                    "option_contract": ticket.get("option_contract") or selected_item.get("option_contract") or None,
                    "option_decision": ticket.get("option_decision") or selected_item.get("option_decision") or None,
                    "line": f"{trade.get('ticker')} {trade.get('direction')} Paper-Trade geöffnet.",
                    "source_label": source_label,
                    "source_url": "",
                }
            )
        if not events:
            return {"status": "ok", "sent": 0, "message": "Keine neuen Paper-Open-Alerts."}
        self._send_notifications(config, events, subject=self._paper_trade_open_subject(events))
        self.portfolio_manager.mark_signal_events_sent(events)
        return {"status": "ok", "sent": len(events), "message": "Paper-Trade-Telegram-Alerts gesendet."}

    def _paper_trade_open_subject(self, events: List[Dict[str, Any]]) -> str:
        labels = {str(event.get("source_label") or "") for event in events}
        if labels == {"Paper-Autopilot"}:
            source = "Paper Autopilot"
        elif labels == {"Paper-Playbook manuell"}:
            source = "Paper Playbook"
        else:
            source = "Paper Trading"
        return f"{source}: Demo-Trade geöffnet"

    def send_paper_trade_management_alerts(self, open_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        if os.getenv("PAPER_TRADE_MANAGEMENT_ALERTS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return {"status": "disabled", "message": "Paper-Trade-Management-Alerts sind deaktiviert."}
        if not open_trades:
            return {"status": "ok", "sent": 0, "message": "Keine offenen Paper-Trades."}

        config = self.get_config()
        self._validate_telegram_config(config)
        alert_statuses = {
            "stop_hit",
            "target_hit",
            "near_stop",
            "near_target",
            "weak_follow_through",
            "holding_period_expired",
            "news_reaction_failed",
            "news_momentum_stalled",
            "news_source_invalidated",
        }
        events: List[Dict[str, Any]] = []
        for trade in open_trades:
            management = trade.get("management_plan") or {}
            status = str(management.get("status") or "")
            if status not in alert_statuses:
                continue
            if not self._paper_trade_management_can_send(trade, management):
                continue
            sent_bucket = datetime.now(
                ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))
            ).strftime("%Y%m%d%H%M")
            event_key = f"paper-manage:{trade.get('id')}:{status}:{sent_bucket}"
            events.append(
                {
                    "event_key": event_key,
                    "category": "paper_trade_management",
                    "trade_id": trade.get("id"),
                    "title": f"Paper-Management: {trade.get('ticker')} {status}",
                    "ticker": trade.get("ticker"),
                    "direction": trade.get("direction"),
                    "asset_class": trade.get("asset_class"),
                    "setup_type": trade.get("setup_type"),
                    "opened_at": trade.get("opened_at"),
                    "closed_at": trade.get("closed_at"),
                    "entry_price": trade.get("entry_price"),
                    "current_price": trade.get("current_price"),
                    "stop_price": trade.get("stop_price"),
                    "target_price": trade.get("target_price"),
                    "quantity": trade.get("quantity"),
                    "invested_value": trade.get("invested_value"),
                    "current_value": trade.get("current_value"),
                    "unrealized_pnl_pct": trade.get("unrealized_pnl_pct"),
                    "unrealized_pnl_value": trade.get("unrealized_pnl_value"),
                    "risk_distance_pct": management.get("risk_distance_pct"),
                    "target_progress_pct": management.get("target_progress_pct"),
                    "management_status": status,
                    "management_action": management.get("action"),
                    "decision_grade": management.get("decision_grade"),
                    "next_check": management.get("next_check"),
                    "management_summary": management.get("summary"),
                    "elapsed_hours": management.get("elapsed_hours"),
                    "source_status": management.get("source_status"),
                    "source_checked_at": management.get("source_checked_at"),
                    "affected_source_url": management.get("source_url"),
                    "max_holding_days": trade.get("max_holding_days"),
                    "news_evidence": (trade.get("trade_ticket") or {}).get("news_evidence")
                    if isinstance(trade.get("trade_ticket"), dict)
                    else None,
                    "line": f"{trade.get('ticker')} Paper-Trade-Management-Alert: {status}.",
                    "source_label": "Paper-Trade-Management",
                    "source_url": "",
                }
            )
        if not events:
            return {"status": "ok", "sent": 0, "message": "Keine neuen Paper-Management-Alerts."}

        self._send_notifications(config, events[:5], subject="Paper Trade Management")
        self.portfolio_manager.mark_signal_events_sent(events[:5])
        self._record_paper_trade_management_deliveries(events[:5])
        return {"status": "ok", "sent": len(events[:5]), "message": "Paper-Management-Telegram-Alerts gesendet."}

    def send_paper_account_status_alert(
        self,
        demo_account: Dict[str, Any],
        open_trades: List[Dict[str, Any]],
        force: bool = False,
        evidence_campaign: Dict[str, Any] | None = None,
        strategy_candidate_coverage: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        if not force and os.getenv("PAPER_ACCOUNT_STATUS_ALERTS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return {"status": "disabled", "message": "Paper-Konto-Status-Alerts sind deaktiviert."}

        status = str(demo_account.get("day_status") or "monitor")
        actionable_statuses = {"action_required", "risk_review", "risk_halt", "protect_profit"}
        monitor_enabled = os.getenv("PAPER_ACCOUNT_STATUS_ALERT_MONITOR_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        evidence_progress_changed = self._paper_evidence_progress_changed(evidence_campaign)
        candidate_coverage_changed = self._paper_candidate_coverage_changed(strategy_candidate_coverage)
        if (
            not force
            and status not in actionable_statuses
            and not monitor_enabled
            and not evidence_progress_changed
            and not candidate_coverage_changed
        ):
            return {"status": "ok", "sent": 0, "message": f"Paper-Konto-Status ist {status}; kein Telegram nötig."}

        config = self.get_config()
        self._validate_telegram_config(config)
        if not force and not self._paper_account_status_can_send(
            demo_account,
            evidence_campaign,
            strategy_candidate_coverage,
        ):
            return {"status": "cooldown", "sent": 0, "message": "Paper-Konto-Status-Cooldown aktiv."}

        evidence_signature = self._paper_evidence_progress_signature(evidence_campaign)

        ranked = sorted(
            open_trades or [],
            key=lambda trade: self._paper_trade_status_rank(
                str((trade.get("management_plan") or {}).get("decision_grade") or "hold")
            ),
        )
        top_trades: List[Dict[str, Any]] = []
        for trade in ranked[:3]:
            management = trade.get("management_plan") or {}
            top_trades.append(
                {
                    "ticker": trade.get("ticker"),
                    "direction": trade.get("direction"),
                    "grade": management.get("decision_grade"),
                    "status": management.get("status"),
                    "result_value_delta": trade.get("result_value_delta"),
                    "unrealized_pnl_pct": trade.get("unrealized_pnl_pct"),
                    "summary": management.get("summary"),
                    "next_check": management.get("next_check"),
                }
            )

        event = {
            "event_key": (
                f"paper-account-status:{status}:{datetime.utcnow().date().isoformat()}:"
                f"c{evidence_signature.get('closed_milestone', 0)}:"
                f"o{evidence_signature.get('outcome_milestone', 0)}:"
                f"r{evidence_signature.get('strategies_ready', 0)}"
            ),
            "category": "paper_account_status",
            "title": f"Paper-Konto-Status: {status}",
            "day_status": status,
            "day_action": demo_account.get("day_action"),
            "capital_status": demo_account.get("capital_status"),
            "starting_capital": demo_account.get("starting_capital"),
            "equity": demo_account.get("equity"),
            "net_pnl_value": demo_account.get("net_pnl_value"),
            "net_pnl_pct": demo_account.get("net_pnl_pct"),
            "open_exposure_value": demo_account.get("open_exposure_value"),
            "cash_available_value": demo_account.get("cash_available_value"),
            "open_trade_count": demo_account.get("open_trade_count"),
            "closed_trade_count": demo_account.get("closed_trade_count"),
            "management_counts": demo_account.get("management_counts") or {},
            "trade_action_queue": demo_account.get("trade_action_queue") or {},
            "risk_circuit": demo_account.get("risk_circuit") or {},
            "performance": demo_account.get("performance") or {},
            "capital_flow": demo_account.get("capital_flow") or {},
            "top_trades": top_trades,
            "evidence_campaign": evidence_campaign or {},
            "strategy_candidate_coverage": strategy_candidate_coverage or [],
            "line": f"Paper-Konto-Status: {status}",
            "source_label": "Paper-Konto-Monitor",
            "source_url": "",
        }
        self._send_notifications(config, [event], subject="Paper Account Status")
        self._record_paper_account_status_delivery(
            demo_account,
            evidence_campaign,
            strategy_candidate_coverage,
        )
        return {
            "status": "ok",
            "sent": 1,
            "trigger": (
                "evidence_progress"
                if evidence_progress_changed
                else "candidate_coverage"
                if candidate_coverage_changed
                else "account_status"
            ),
            "message": "Paper-Konto-Status-Telegram-Alert gesendet.",
        }

    def send_paper_trade_closed_alerts(
        self,
        closed: List[Dict[str, Any]],
        demo_account: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if os.getenv("PAPER_TRADE_CLOSE_ALERTS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return {"status": "disabled", "message": "Paper-Trade-Close-Alerts sind deaktiviert."}
        if not closed:
            return {"status": "ok", "sent": 0, "message": "Keine geschlossenen Paper-Trades."}

        config = self.get_config()
        self._validate_telegram_config(config)
        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        events: List[Dict[str, Any]] = []
        for trade in closed[:5]:
            event_key = f"paper-close:{trade.get('id')}"
            if event_key in sent_keys:
                continue
            events.append(
                {
                    "event_key": event_key,
                    "category": "paper_trade_closed",
                    "title": f"Paper-Trade geschlossen: {trade.get('ticker')} {trade.get('direction')}",
                    "ticker": trade.get("ticker"),
                    "direction": trade.get("direction"),
                    "asset_class": trade.get("asset_class"),
                    "setup_type": trade.get("setup_type"),
                    "entry_price": trade.get("entry_price"),
                    "closed_price": trade.get("closed_price"),
                    "quantity": trade.get("quantity"),
                    "invested_value": trade.get("invested_value"),
                    "final_value": trade.get("final_value"),
                    "result_value_delta": trade.get("result_value_delta"),
                    "result_label": trade.get("result_label"),
                    "realized_pnl_pct": trade.get("realized_pnl_pct"),
                    "realized_pnl_value": trade.get("realized_pnl_value"),
                    "exit_reason": trade.get("exit_reason"),
                    "lessons_learned": trade.get("lessons_learned"),
                    "risk_reward": trade.get("risk_reward"),
                    "trade_ticket": trade.get("trade_ticket") or {},
                    "account_equity": (demo_account or {}).get("equity"),
                    "account_cash_available": (demo_account or {}).get("cash_available_value"),
                    "account_open_exposure": (demo_account or {}).get("open_exposure_value"),
                    "account_net_pnl_value": (demo_account or {}).get("net_pnl_value"),
                    "account_net_pnl_pct": (demo_account or {}).get("net_pnl_pct"),
                    "account_performance": (demo_account or {}).get("performance") or {},
                    "account_capital_flow": (demo_account or {}).get("capital_flow") or {},
                    "account_asset_class_limits": (demo_account or {}).get("asset_class_limits") or {},
                    "account_cash_reserve_target": (demo_account or {}).get("cash_reserve_target_value"),
                    "line": f"{trade.get('ticker')} Paper-Trade geschlossen.",
                    "source_label": "Paper-Trade-Exit",
                    "source_url": "",
                }
            )
        if not events:
            return {"status": "ok", "sent": 0, "message": "Keine neuen Paper-Close-Alerts."}

        self._send_notifications(config, events, subject="Paper Trade Closed")
        self.portfolio_manager.mark_signal_events_sent(events)
        return {"status": "ok", "sent": len(events), "message": "Paper-Close-Telegram-Alerts gesendet."}

    def _extract_paper_learning_events(self, learning: Dict[str, Any], sent_keys: set[str]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        summary = learning.get("learning_summary") or {}
        review_focus = summary.get("review_focus") or []
        manual_review_checklist = summary.get("manual_review_checklist") or []
        setup_adjustments = learning.get("setup_adjustments") or {}
        for setup_type, adjustment in setup_adjustments.items():
            if not adjustment.get("block") and float(adjustment.get("score_delta") or 0) > -8:
                continue
            key = f"paper-learning:{setup_type}:{adjustment.get('block')}:{adjustment.get('score_delta')}:{adjustment.get('decisive')}"
            if key in sent_keys:
                continue
            severity = "BLOCK" if adjustment.get("block") else "DOWNGRADE"
            line = (
                f"{severity}: {setup_type} | Treffer {adjustment.get('hit_rate')}% über "
                f"{adjustment.get('decisive')} Prüfungen | Score {adjustment.get('score_delta')}. "
                f"{adjustment.get('reason')}"
            )
            events.append(
                {
                    "event_key": key,
                    "category": "paper_learning",
                    "severity": severity.lower(),
                    "title": f"Paper-Lernen {severity.lower()}",
                    "line": line,
                    "setup_type": setup_type,
                    "hit_rate": adjustment.get("hit_rate"),
                    "decisive": adjustment.get("decisive"),
                    "score_delta": adjustment.get("score_delta"),
                    "blocked": bool(adjustment.get("block")),
                    "reason": adjustment.get("reason") or "",
                    "review_focus": review_focus[:3],
                    "manual_review_checklist": manual_review_checklist[:5],
                    "critical_check": "Dieses Setup nicht mit Echtgeld nutzen, bis der Fehlergrund behoben ist und neue Paper-Beweise besser werden.",
                    "action": "Setup blockieren" if adjustment.get("block") else "Größe reduzieren und stärkere Bestätigung verlangen",
                    "source_label": "Paper-Outcome-Lernen",
                    "source_url": "",
                    "conviction_score": None,
                }
            )

        option = learning.get("option_readiness") or {}
        if option and not option.get("real_money_ready") and int(option.get("decisive") or 0) in {5, 10, 15, 19}:
            key = f"paper-learning:options:not-ready:{option.get('decisive')}:{option.get('hit_rate')}"
            if key not in sent_keys:
                events.append(
                    {
                        "event_key": key,
                        "category": "paper_learning",
                        "severity": "options_gate",
                        "title": "Optionen bleiben Paper-only",
                        "line": (
                            f"CALL/PUT-Lernen: {option.get('decisive')} klare Prüfungen, "
                            f"{option.get('hit_rate')}% Trefferquote. {option.get('reason')}"
                        ),
                        "setup_type": "call_put_learning",
                        "hit_rate": option.get("hit_rate"),
                        "decisive": option.get("decisive"),
                        "score_delta": None,
                        "blocked": True,
                        "reason": option.get("reason") or "",
                        "review_focus": review_focus[:3],
                        "manual_review_checklist": manual_review_checklist[:5],
                        "critical_check": "Keine Echtgeld-Calls oder -Puts, bevor genug Paper-Prüfungen, Strike/Laufzeit/Spread-Review und maximaler Prämienverlust dokumentiert sind.",
                        "action": "Optionen Paper-only lassen",
                        "source_label": "Options-Paper-Lernen",
                        "source_url": "",
                        "conviction_score": None,
                    }
                )
        return events

    def send_daily_brief(self) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        brief_lines = self._build_daily_brief_lines(snapshot)
        events = [
            {
                "event_key": f"daily-brief:{datetime.now().strftime('%Y-%m-%d')}:{index}",
                "category": "brief",
                "title": "Daily Brief",
                "line": line,
                "source_url": "",
            }
            for index, line in enumerate(brief_lines)
        ]
        self._send_notifications(config, events, subject="Daily Brief: Watchlist-Update")
        return {"status": "ok", "message": "Daily brief sent."}

    def send_morning_brief(self) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        events = self._build_open_brief_events(session_label="global")
        self._send_notifications(config, events, subject="Morning Brief: Global opening setup")
        return {"status": "ok", "message": "Morning brief sent."}

    def send_session_brief_now(self, session: str = "global") -> Dict[str, Any]:
        """Manually fire a rich Telegram brief for the requested session.

        session: one of global, europe, midday, usa, europe_close,
                 close, usa_close. Defaults to 'global' (full morning brief).
        """
        config = self.get_config()
        self._validate_telegram_config(config)
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        try:
            self.morning_brief_service.get_brief_fast(snapshot, True)
        except Exception as exc:
            print(f"Brief warm-cache failed before manual {session}: {exc}")
        brief = dict(self.morning_brief_service.get_brief(snapshot))
        brief = self._attach_delivery_market_movers(brief, snapshot)
        try:
            brief["trading_edge"] = self.morning_brief_service.get_trading_edge(snapshot)
        except Exception:
            brief["trading_edge"] = {}
        try:
            self._telegram_preflight(config)
            self._send_telegram_rich_brief(config, brief, session)
        except Exception as e:
            raise RuntimeError(f"Telegram send failed: {e}") from e
        learning = self._record_brief_forecasts(
            brief,
            session,
            f"manual-brief:{session}:{datetime.utcnow().isoformat()}",
        )
        return {
            "status": "ok",
            "message": f"Session brief '{session}' sent to Telegram.",
            "forecasts_recorded": learning.get("recorded", 0),
        }

    def _attach_delivery_market_movers(
        self,
        brief: Dict[str, Any],
        snapshot: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        enriched = dict(brief or {})
        watchlist_tickers = [
            str(item.get("value") or "").upper().strip()
            for item in (snapshot or {}).get("items", [])
            if isinstance(item, dict)
            and item.get("kind") == "ticker"
            and str(item.get("value") or "").strip()
        ]
        timeout_seconds = self._safe_int_env("SCHEDULED_BRIEF_MOVERS_TIMEOUT_SECONDS", 15, minimum=3)
        try:
            movers = self._run_with_timeout(
                "session market movers",
                lambda: self.morning_brief_service.collect_market_movers_for_delivery(watchlist_tickers),
                timeout_seconds,
            )
            gainers = movers.get("gainers") if isinstance(movers, dict) else []
            losers = movers.get("losers") if isinstance(movers, dict) else []
            if not gainers and not losers:
                raise RuntimeError("no valid one-day mover quotes")
            enriched["market_movers"] = {
                "gainers": list(gainers or []),
                "losers": list(losers or []),
            }
            universe = list(
                dict.fromkeys(
                    [*watchlist_tickers, *getattr(self.morning_brief_service, "MARKET_MOVER_UNIVERSE", [])]
                )
            )
            sample = next(iter([*(gainers or []), *(losers or [])]), {})
            enriched["market_movers_meta"] = {
                "status": "ready",
                "window": "1d",
                "scope": "configured_universe_plus_watchlist",
                "universe_size": len(universe),
                "as_of": sample.get("as_of") or datetime.now(ZoneInfo("UTC")).isoformat(),
            }
        except Exception as exc:
            print(f"Session market movers unavailable: {exc}")
            enriched["market_movers"] = {"gainers": [], "losers": []}
            enriched["market_movers_meta"] = {
                "status": "unavailable",
                "window": "1d",
                "scope": "configured_universe_plus_watchlist",
            }
        return enriched

    async def send_a_setup_digest_async(self) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        settings = self.portfolio_manager.get_signal_score_settings()
        scoreboard = await self.signal_score_service.build_scoreboard(snapshot, settings)
        min_score = float(settings.get("high_conviction_min_score") or 75)
        top_ideas = [
            item for item in scoreboard.get("top_ideas", [])
            if float(item.get("total_score") or 0) >= min_score
        ][:8]
        if not top_ideas:
            return {"status": "ok", "message": "No A-setups available right now."}
        events = []
        for index, item in enumerate(top_ideas):
            line = f"{item.get('label')} | {item.get('headline')} | score {item.get('total_score')}"
            if item.get("detail"):
                line += f" | {item.get('detail')}"
            events.append(
                {
                    "event_key": f"a-setup-digest:{datetime.now().strftime('%Y-%m-%d')}:{index}:{item.get('label')}",
                    "category": "a_setup",
                    "title": item.get("label") or "A-Setup",
                    "line": line,
                    "source_url": "",
                    "source_label": item.get("source_label") or item.get("bucket"),
                    "conviction_score": item.get("total_score"),
                }
            )
        self._send_notifications(config, events, subject="A-Setup Digest: High-conviction ideas")
        return {"status": "ok", "message": f"A-Setup digest sent with {len(events)} ideas."}

    def send_a_setup_digest(self) -> Dict[str, Any]:
        return asyncio.run(self.send_a_setup_digest_async())

    def send_open_brief(self, session_label: str) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        session = (session_label or "").strip().lower()
        if session not in {"europe", "usa"}:
            raise ValueError("session must be 'europe' or 'usa'")
        events = self._build_open_brief_events(session)
        self._send_notifications(
            config,
            events,
            subject=f"{session.title()} Open Brief: Market opening setup",
        )
        return {"status": "ok", "message": f"{session.title()} open brief sent."}

    async def send_session_list_alert_async(self, region: str, phase: str) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        events = await self._build_session_list_events(region, phase)
        self._send_notifications(
            config,
            events,
            subject=f"{region.title()} {phase.replace('_', ' ').title()}: Session list",
        )
        return {"status": "ok", "message": f"{region.title()} {phase} session list sent."}

    def send_session_list_alert(self, region: str, phase: str) -> Dict[str, Any]:
        return asyncio.run(self.send_session_list_alert_async(region, phase))

    def send_scheduled_open_briefs(self, include_missed: bool = False) -> List[Dict[str, Any]]:
        config = self.get_config()
        if not config.scheduled_briefs_enabled:
            self.portfolio_manager.set_app_setting(
                "brief_scheduler_last_result",
                json.dumps([{"status": "disabled", "message": "Scheduled briefs are disabled."}]),
            )
            return []

        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        self.portfolio_manager.set_app_setting("brief_scheduler_last_checked_at", now.isoformat())
        if not self._schedule_day_matches(now):
            self.portfolio_manager.set_app_setting(
                "brief_scheduler_last_result",
                json.dumps([{"status": "skipped", "message": "Today is outside BRIEF_SCHEDULE_WEEKDAYS."}]),
            )
            return []

        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        jobs = [
            {
                "job_key": "morning-brief",
                "scheduled_time": os.getenv("MORNING_BRIEF_TIME", DEFAULT_MORNING_BRIEF_TIME),
                "subject": "Morning Brief: Global macro, news and setup",
                "title": "Morning Brief",
                "category": "scheduled_brief",
                "session_label": "global",
                "build_events": lambda: self._build_open_brief_events("global"),
                "is_brief": True,
            },
            {
                "job_key": "open-brief:europe",
                "scheduled_time": os.getenv("EUROPE_OPEN_BRIEF_TIME", DEFAULT_EUROPE_OPEN_BRIEF_TIME),
                "subject": "Europe Open Brief: Market opening setup",
                "title": "Europe Open Brief",
                "category": "open_brief",
                "session_label": "europe",
                "build_events": lambda: self._build_open_brief_events("europe"),
                "is_brief": True,
            },
            {
                "job_key": "midday-brief",
                "scheduled_time": os.getenv("MIDDAY_BRIEF_TIME", DEFAULT_MIDDAY_BRIEF_TIME),
                "subject": "Midday Update: What changed since the open",
                "title": "Midday Update",
                "category": "scheduled_brief",
                "session_label": "midday",
                "build_events": self._build_midday_update_events,
                "is_brief": True,
            },
            {
                "job_key": "open-brief:usa",
                "scheduled_time": os.getenv("US_OPEN_BRIEF_TIME", DEFAULT_US_OPEN_BRIEF_TIME),
                "subject": "US Open Brief: Market opening setup",
                "title": "US Open Brief",
                "category": "open_brief",
                "session_label": "usa",
                "build_events": lambda: self._build_open_brief_events("usa"),
                "is_brief": True,
            },
            {
                "job_key": "close-brief:europe",
                "scheduled_time": os.getenv("EUROPE_CLOSE_BRIEF_TIME", DEFAULT_EUROPE_CLOSE_BRIEF_TIME),
                "subject": "Europe Close Brief: Session wrap + US watch",
                "title": "Europe Close Brief",
                "category": "close_brief",
                "session_label": "europe_close",
                "build_events": lambda: self._build_close_brief_events("europe"),
                "is_brief": True,
            },
            {
                "job_key": "close-brief:usa",
                "scheduled_time": os.getenv("US_CLOSE_BRIEF_TIME", DEFAULT_US_CLOSE_BRIEF_TIME),
                "subject": "US Close Brief: Session wrap + overnight watch",
                "title": "US Close Brief",
                "category": "close_brief",
                "session_label": "usa_close",
                "build_events": lambda: self._build_close_brief_events("usa"),
                "is_brief": True,
            },
            {
                "job_key": "close-recap",
                "scheduled_time": os.getenv("CLOSE_RECAP_TIME", DEFAULT_CLOSE_RECAP_TIME),
                "subject": "End of Day Recap: Stocks, macro and next risks",
                "title": "End of Day Recap",
                "category": "scheduled_brief",
                "session_label": "close",
                "build_events": self._build_close_recap_events,
                "is_brief": True,
            },
        ]
        results: List[Dict[str, Any]] = []
        max_jobs_per_run = self._safe_int_env("BRIEF_MAX_JOBS_PER_RUN", 6, minimum=1)
        on_time_window_minutes = self._brief_on_time_window_minutes()
        catchup_window_minutes = self._brief_delivery_grace_minutes()
        sent_this_run = 0
        due_jobs: List[Dict[str, Any]] = []

        for job in jobs:
            event_key = f"{job['job_key']}:{now.date().isoformat()}"
            if event_key in sent_keys:
                continue
            scheduled_at = self._scheduled_datetime(now, str(job["scheduled_time"]))
            if scheduled_at is None:
                continue
            delta_minutes = (now - scheduled_at).total_seconds() / 60
            if delta_minutes < 0:
                continue
            on_time = delta_minutes < on_time_window_minutes
            catchup = include_missed and delta_minutes < catchup_window_minutes
            if not (on_time or catchup):
                if delta_minutes >= catchup_window_minutes:
                    missed = {
                        "job": job["job_key"],
                        "status": "missed",
                        "event_key": event_key,
                        "scheduled_at": scheduled_at.isoformat(),
                        "minutes_late": int(delta_minutes),
                        "message": "Brief verpasst: Grace-Zeit abgelaufen. Pruefe Scheduler/Telegram und sende bei Bedarf manuell.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), missed)
                continue
            due_jobs.append(
                {
                    **job,
                    "event_key": event_key,
                    "scheduled_at": scheduled_at,
                    "minutes_late": max(0, int(delta_minutes)),
                    "on_time": on_time,
                    "catchup": bool(catchup and not on_time),
                }
            )

        # Prioritize the current slot first. Catchup jobs remain available but
        # cannot block the midday or US-open brief after a restart.
        due_jobs.sort(key=lambda item: (0 if item.get("on_time") else 1, item["scheduled_at"]))

        for job in due_jobs:
            if sent_this_run >= max_jobs_per_run:
                break
            event_key = str(job["event_key"])

            try:
                self._validate_config(config)
            except Exception as exc:
                failure = {
                    "job": job["job_key"],
                    "status": "failed",
                    "event_key": event_key,
                    "scheduled_at": job["scheduled_at"].isoformat(),
                    "minutes_late": job["minutes_late"],
                    "error": f"config_failed: {exc}",
                    "message": "Telegram-Konfiguration unvollstaendig. Job bleibt offen und wird nach Korrektur erneut versucht.",
                }
                self._set_brief_job_status(str(job["job_key"]), failure)
                results.append(failure)
                continue
            self._set_brief_job_status(
                str(job["job_key"]),
                {
                    "status": "running",
                    "event_key": event_key,
                    "scheduled_at": job["scheduled_at"].isoformat(),
                    "started_at": datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
                    "message": "Brief wird gebaut: Cache wird vorbereitet, Daten werden geladen, Versand wird vorbereitet.",
                },
            )
            events: List[Dict[str, Any]] = []
            if not job.get("is_brief"):
                try:
                    events = job["build_events"]()
                except Exception as exc:
                    failure = {
                        "job": job["job_key"],
                        "status": "failed",
                        "event_key": event_key,
                        "scheduled_at": job["scheduled_at"].isoformat(),
                        "minutes_late": job["minutes_late"],
                        "error": f"build_failed: {exc}",
                        "message": "Alert konnte nicht gebaut werden. Logs und Datenquellen pruefen; der Job kann innerhalb der Grace-Zeit erneut laufen.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), failure)
                    results.append(failure)
                    continue
            delivered = False
            brief = None

            # Scheduled briefs use the richer multi-part Telegram format.
            if job.get("is_brief"):
                items = self.portfolio_manager.get_signal_watch_items()
                snapshot_timeout = self._safe_int_env("SCHEDULED_BRIEF_SNAPSHOT_TIMEOUT_SECONDS", 8, minimum=2)
                brief_timeout = self._safe_int_env("SCHEDULED_BRIEF_BUILD_TIMEOUT_SECONDS", 35, minimum=5)
                edge_timeout = self._safe_int_env("SCHEDULED_BRIEF_EDGE_TIMEOUT_SECONDS", 10, minimum=2)
                try:
                    snapshot = self._run_with_timeout(
                        f"{job['job_key']} snapshot",
                        lambda: self.public_signal_service.build_watchlist_snapshot(items),
                        snapshot_timeout,
                    )
                except Exception as exc:
                    failure = {
                        "job": job["job_key"],
                        "status": "failed",
                        "event_key": event_key,
                        "scheduled_at": job["scheduled_at"].isoformat(),
                        "minutes_late": job["minutes_late"],
                        "error": f"snapshot_failed: {exc}",
                        "message": "Watchlist-Snapshot fehlgeschlagen. Der Brief wurde nicht ohne Basisdaten gesendet.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), failure)
                    results.append(failure)
                    continue
                try:
                    self._run_with_timeout(
                        f"{job['job_key']} warm brief",
                        lambda: self.morning_brief_service.get_brief_fast(snapshot, True),
                        brief_timeout,
                    )
                except Exception as exc:
                    print(f"Brief warm-cache failed before {job['job_key']}: {exc}")
                try:
                    brief = self._run_with_timeout(
                        f"{job['job_key']} brief",
                        lambda: self.morning_brief_service.get_brief_fast(snapshot, False),
                        brief_timeout,
                    )
                except Exception as exc:
                    failure = {
                        "job": job["job_key"],
                        "status": "failed",
                        "event_key": event_key,
                        "scheduled_at": job["scheduled_at"].isoformat(),
                        "minutes_late": job["minutes_late"],
                        "error": f"brief_failed: {exc}",
                        "message": "Morning Brief konnte nicht geladen werden. Warm-Cache und Provider pruefen.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), failure)
                    results.append(failure)
                    continue
                # Trading edge is decoupled from the cached brief — fetch
                # fresh here so scheduled briefs always include MSG 5.
                if not self.morning_brief_service._is_usable_brief(brief):
                    failure = {
                        "job": job["job_key"],
                        "status": "blocked",
                        "event_key": event_key,
                        "scheduled_at": job["scheduled_at"].isoformat(),
                        "minutes_late": job["minutes_late"],
                        "error": "brief_quality_gate_failed",
                        "message": "Brief nicht gesendet: Kernmarktdaten oder verwertbare Regionen fehlen. Retry statt leeres Signal.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), failure)
                    results.append(failure)
                    continue
                brief = self._attach_delivery_market_movers(dict(brief), snapshot)
                try:
                    brief["trading_edge"] = self._run_with_timeout(
                        f"{job['job_key']} trading edge",
                        lambda: self.morning_brief_service.get_trading_edge(snapshot),
                        edge_timeout,
                    )
                except Exception as exc:
                    print(f"Brief trading-edge skipped for {job['job_key']}: {exc}")
                telegram_required = bool(
                    config.telegram_enabled
                    and config.telegram_bot_token
                    and config.telegram_chat_id
                )
                telegram_delivered = False
                telegram_error = None
                try:
                    if telegram_required:
                        self._telegram_preflight(config)
                    self._send_telegram_rich_brief(config, brief, str(job["session_label"]))
                    telegram_delivered = telegram_required
                    delivered = telegram_delivered or delivered
                except Exception as exc:
                    telegram_error = str(exc)
                    print(f"Scheduled Telegram brief failed for {job['job_key']}: {exc}")
                if telegram_required and not telegram_delivered:
                    failure = {
                        "job": job["job_key"],
                        "status": "failed",
                        "event_key": event_key,
                        "scheduled_at": job["scheduled_at"].isoformat(),
                        "minutes_late": job["minutes_late"],
                        "error": telegram_error or "telegram_not_delivered",
                        "email_delivered": delivered,
                        "message": "Telegram-Versand fehlgeschlagen; der Job wird innerhalb der Grace-Zeit erneut versucht.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), failure)
                    results.append(failure)
                    continue
            else:
                delivered = self._send_notifications(config, events, subject=str(job["subject"]))
            if not delivered:
                failure = {
                    "job": job["job_key"],
                    "status": "failed",
                    "event_key": event_key,
                    "scheduled_at": job["scheduled_at"].isoformat(),
                    "minutes_late": job["minutes_late"],
                    "message": "Kein Versandkanal hat erfolgreich geliefert; der Job wird innerhalb der Grace-Zeit erneut versucht.",
                }
                self._set_brief_job_status(str(job["job_key"]), failure)
                results.append(failure)
                continue
            self.portfolio_manager.mark_signal_events_sent(
                [
                    {
                        "event_key": event_key,
                        "category": str(job["category"]),
                        "title": str(job["title"]),
                    }
                ]
            )
            learning = (
                self._record_brief_forecasts(
                    brief,
                    str(job["session_label"]),
                    event_key,
                )
                if isinstance(brief, dict)
                else {"recorded": 0, "skipped": 0}
            )
            success = {
                "job": job["job_key"],
                "status": "sent",
                "event_key": event_key,
                "scheduled_at": job["scheduled_at"].isoformat(),
                "sent_at": datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
                "minutes_late": job["minutes_late"],
                "catchup": bool(job.get("catchup")),
                "forecasts_recorded": learning.get("recorded", 0),
                "message": "Brief erfolgreich gesendet.",
            }
            self._set_brief_job_status(str(job["job_key"]), success)
            results.append(success)
            sent_this_run += 1

        if not results:
            results.append(
                {
                    "status": "idle",
                    "message": "Kein geplanter Brief ist im aktuellen Zeitfenster faellig.",
                    "checked_at": now.isoformat(),
                }
            )
        self.portfolio_manager.set_app_setting("brief_scheduler_last_result", json.dumps(results[-5:]))
        return results

    def send_scheduled_daily_overview(
        self,
        include_missed: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Send one optional local-data summary without competing with rich briefs."""
        config = self.get_config()
        job_key = "daily-overview"
        if not config.daily_overview_enabled and not force:
            result = {
                "job": job_key,
                "status": "disabled",
                "message": "Die optionale Tagesuebersicht ist deaktiviert.",
            }
            self._set_brief_job_status(job_key, result)
            return result

        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        event_key = f"{job_key}:{now.date().isoformat()}"
        if event_key in self.portfolio_manager.get_sent_signal_event_keys():
            result = {
                "job": job_key,
                "status": "deduplicated",
                "event_key": event_key,
                "message": "Die Tagesuebersicht wurde heute bereits zugestellt.",
            }
            self._set_brief_job_status(job_key, result)
            return result

        scheduled_at = self._scheduled_datetime(
            now, os.getenv("DAILY_OVERVIEW_TIME", DEFAULT_DAILY_OVERVIEW_TIME)
        )
        if not force:
            if not self._schedule_day_matches(now):
                result = {"job": job_key, "status": "skipped", "event_key": event_key}
                self._set_brief_job_status(job_key, result)
                return result
            if scheduled_at is None:
                result = {
                    "job": job_key,
                    "status": "failed",
                    "event_key": event_key,
                    "error": "invalid_schedule_time",
                }
                self._set_brief_job_status(job_key, result)
                return result
            delta_minutes = (now - scheduled_at).total_seconds() / 60
            on_time = 0 <= delta_minutes < self._brief_on_time_window_minutes()
            grace = self._safe_int_env("DAILY_OVERVIEW_GRACE_MINUTES", 180, minimum=1)
            catchup = include_missed and 0 <= delta_minutes < grace
            if not (on_time or catchup):
                status = "missed" if delta_minutes >= grace else "idle"
                result = {
                    "job": job_key,
                    "status": status,
                    "event_key": event_key,
                    "scheduled_at": scheduled_at.isoformat(),
                }
                self._set_brief_job_status(job_key, result)
                return result

        try:
            self._validate_config(config)
            events = self._build_daily_overview_events(now, event_key)
            delivered = self._send_notifications(
                config,
                events,
                subject="Geplante Tagesuebersicht: Paper-Konto und Lernstand",
            )
            if not delivered:
                raise RuntimeError("Telegram hat keine Zustellung bestaetigt.")
        except Exception as exc:
            result = {
                "job": job_key,
                "status": "failed",
                "event_key": event_key,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "error": str(exc),
                "message": "Nicht als gesendet markiert; der naechste Lauf darf erneut versuchen.",
            }
            self._set_brief_job_status(job_key, result)
            return result

        marker = {
            "event_key": event_key,
            "category": "daily_overview",
            "line": "Geplante Telegram-Tagesuebersicht",
        }
        self.portfolio_manager.mark_signal_events_sent([marker])
        result = {
            "job": job_key,
            "status": "sent",
            "event_key": event_key,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "sent_at": now.isoformat(),
            "message": "Tagesuebersicht zugestellt; Echtzeit-Risikoalarme bleiben unabhaengig.",
        }
        self._set_brief_job_status(job_key, result)
        return result

    def _build_daily_overview_events(self, now: datetime, event_key: str) -> List[Dict[str, Any]]:
        trades = self.portfolio_manager.list_paper_trades(limit=1000)
        outcomes = self.portfolio_manager.list_paper_trade_outcomes(limit=2000)
        portfolios = self.portfolio_manager.get_portfolios()
        today = now.date()

        def local_date(value: Any) -> Any:
            if not value:
                return None
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(now.tzinfo)
                return parsed.date()
            except (TypeError, ValueError):
                return None

        open_trades = [trade for trade in trades if str(trade.get("status") or "").lower() == "open"]
        closed_today = [
            trade
            for trade in trades
            if str(trade.get("status") or "").lower() == "closed"
            and local_date(trade.get("closed_at")) == today
        ]
        realized_today = 0.0
        for trade in closed_today:
            entry = float(trade.get("entry_price") or 0)
            exit_price = float(trade.get("closed_price") or 0)
            quantity = float(trade.get("quantity") or 0)
            multiplier = float(trade.get("contract_multiplier") or 1)
            leverage = float(trade.get("leverage") or 1)
            ticket = trade.get("trade_ticket") if isinstance(trade.get("trade_ticket"), dict) else {}
            product = ticket.get("leveraged_product") if isinstance(ticket.get("leveraged_product"), dict) else {}
            payout = 1.0 if product.get("leverage_is_embedded_in_product_price") is True else leverage
            direction = -1.0 if str(trade.get("direction") or "long").lower() == "short" else 1.0
            realized_today += (exit_price - entry) * quantity * multiplier * payout * direction

        evaluated = [item for item in outcomes if str(item.get("status") or "").lower() == "evaluated"]
        decisive = [item for item in evaluated if str(item.get("result") or "").lower() in {"hit", "miss"}]
        pending = [
            item for item in outcomes if str(item.get("status") or "").lower() in {"pending", "pending_data"}
        ]
        holding_count = sum(len(item.get("holdings") or []) for item in portfolios)
        lines = [
            "Geplante Zusammenfassung - keine neue Handelsentscheidung.",
            f"Portfolios: {len(portfolios)} | echte Positionen: {holding_count}",
            f"Paper-Konto: {len(open_trades)} offen | heute {len(closed_today)} geschlossen | realisiert {realized_today:+.2f}",
            f"Lernstand: {len(evaluated)} ausgewertet | {len(decisive)} entscheidend | {len(pending)} offen",
            "Kauf-, Verkauf-, Management- und Risiko-Pushes laufen sofort und unabhaengig von dieser Uebersicht.",
        ]
        return [
            {"event_key": f"{event_key}:{index}", "category": "daily_overview", "line": line}
            for index, line in enumerate(lines, start=1)
        ]

    def get_brief_job_status(self, job_key: str) -> Dict[str, Any]:
        raw = self.portfolio_manager.get_app_setting(self._brief_status_key(job_key), "{}")
        try:
            payload = json.loads(raw or "{}")
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def mark_manual_brief_job_sent(
        self,
        job_key: str,
        title: str,
        category: str,
        event_key: str,
        session_label: str,
    ) -> Dict[str, Any]:
        sent_at = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat()
        self.portfolio_manager.mark_signal_events_sent(
            [
                {
                    "event_key": event_key,
                    "category": category,
                    "title": title,
                }
            ]
        )
        payload = {
            "job": job_key,
            "status": "sent",
            "event_key": event_key,
            "sent_at": sent_at,
            "manual": True,
            "session_label": session_label,
            "message": "Brief wurde manuell als Rich-Telegram-Brief gesendet.",
        }
        self._set_brief_job_status(job_key, payload)
        return payload

    def _brief_status_key(self, job_key: str) -> str:
        safe_key = re.sub(r"[^a-zA-Z0-9:_-]+", "_", str(job_key or "unknown"))
        return f"brief_scheduler_job_status:{safe_key}"

    def _set_brief_job_status(self, job_key: str, payload: Dict[str, Any]) -> None:
        previous = self.get_brief_job_status(job_key)
        status = str(payload.get("status") or "")
        enriched = {
            **previous,
            **payload,
            "job": payload.get("job") or job_key,
            "updated_at": datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
        }
        if status == "sent":
            enriched["last_success_at"] = payload.get("sent_at") or enriched["updated_at"]
            enriched["last_error"] = None
        elif status in {"failed", "blocked"}:
            enriched["last_error"] = payload.get("error") or payload.get("message") or "failed"
        elif status == "missed":
            enriched["last_error"] = payload.get("message") or "missed"
        self.portfolio_manager.set_app_setting(self._brief_status_key(job_key), json.dumps(enriched))

    def _record_brief_forecasts(
        self,
        brief: Dict[str, Any] | None,
        session_label: str,
        delivery_key: str,
    ) -> Dict[str, Any]:
        if not self.forecast_learning_service or not isinstance(brief, dict):
            return {"status": "disabled", "recorded": 0, "skipped": 0}
        try:
            return self.forecast_learning_service.record_brief_forecasts(
                brief=brief,
                session_label=session_label,
                delivery_key=delivery_key,
            )
        except Exception as exc:
            print(f"Forecast recording failed for {delivery_key}: {exc}")
            return {"status": "error", "recorded": 0, "skipped": 0, "error": str(exc)}

    def _schedule_day_matches(self, now: datetime) -> bool:
        raw_value = os.getenv("BRIEF_SCHEDULE_WEEKDAYS", "mon,tue,wed,thu,fri")
        day_aliases = {
            "mon": 0,
            "monday": 0,
            "tue": 1,
            "tues": 1,
            "tuesday": 1,
            "wed": 2,
            "wednesday": 2,
            "thu": 3,
            "thur": 3,
            "thurs": 3,
            "thursday": 3,
            "fri": 4,
            "friday": 4,
            "sat": 5,
            "saturday": 5,
            "sun": 6,
            "sunday": 6,
        }
        allowed_days = {
            day_aliases[token.strip().lower()]
            for token in raw_value.split(",")
            if token.strip().lower() in day_aliases
        }
        if not allowed_days:
            allowed_days = {0, 1, 2, 3, 4}
        return now.weekday() in allowed_days

    def _time_window_matches(self, now: datetime, scheduled_hhmm: str) -> bool:
        scheduled = self._scheduled_datetime(now, scheduled_hhmm)
        if scheduled is None:
            return False
        grace_minutes = self._brief_on_time_window_minutes()
        delta_minutes = (now - scheduled).total_seconds() / 60
        return 0 <= delta_minutes < grace_minutes

    def _brief_on_time_window_minutes(self) -> int:
        loop_minutes = self._safe_int_env("BRIEF_SCHEDULER_INTERVAL_MINUTES", 5, minimum=1)
        signal_minutes = self._safe_int_env("SIGNAL_ALERTS_INTERVAL_MINUTES", 15, minimum=1)
        minimum_window = max(loop_minutes, min(signal_minutes, 15))
        return self._safe_int_env("BRIEF_ON_TIME_WINDOW_MINUTES", 30, minimum=minimum_window)

    def _brief_delivery_grace_minutes(self) -> int:
        loop_minutes = self._safe_int_env("BRIEF_SCHEDULER_INTERVAL_MINUTES", 5, minimum=1)
        return max(loop_minutes, self._safe_int_env("BRIEF_DELIVERY_GRACE_MINUTES", 720, minimum=loop_minutes))

    def _safe_int_env(self, name: str, default: int, minimum: int | None = None) -> int:
        raw_value = os.getenv(name, str(default)).strip()
        try:
            value = int(raw_value)
        except Exception:
            value = default
        if minimum is not None:
            value = max(minimum, value)
        return value

    def _run_with_timeout(self, label: str, fn: "Any", timeout_seconds: int) -> Any:
        future = self._brief_executor.submit(fn)
        try:
            return future.result(timeout=max(1, int(timeout_seconds)))
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"{label} timed out after {timeout_seconds}s") from exc

    def _scheduled_datetime(self, now: datetime, scheduled_hhmm: str) -> datetime | None:
        try:
            hour, minute = [int(part) for part in scheduled_hhmm.split(":", 1)]
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            return None

    def _build_open_brief_events(self, session_label: str) -> List[Dict[str, Any]]:
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        brief = self.morning_brief_service.get_brief(snapshot)

        session_key = None if session_label == "global" else session_label
        timeline = brief.get("opening_timeline", [])
        economic_calendar = brief.get("economic_calendar", [])
        earnings_calendar = brief.get("earnings_calendar", [])

        focus_line = brief.get("headline", "Morning Brief")
        if session_key:
            session_timeline = next(
                (item for item in timeline if item.get("label", "").lower() == session_key),
                None,
            )
            if session_timeline:
                focus_line = (
                    f"{session_timeline.get('label')}: {session_timeline.get('tone')} "
                    f"{session_timeline.get('move', 0):+.2f}% | {session_timeline.get('driver')}"
                )

        lines = [
            focus_line,
            "",
            *brief.get("summary_points", [])[:4],
            "",
            "Trusted source policy:",
            "- Top News: nur priorisierte serioese Publisher und Domains.",
            "- Social/X/Stocktwits/Telegram werden ausgeschlossen.",
            "- Reddit erscheint nur separat als Crowd-Signal bei Wiederholung.",
            "",
            "Economic calendar:",
        ]

        calendar_items = [
            item for item in economic_calendar
            if session_key is None or item.get("region") in {session_key, "global"}
        ]
        if calendar_items:
            lines.extend(
                f"- {item['title']} ({item['region']}) {item['scheduled_for'][11:16]}"
                for item in calendar_items[:4]
            )
        else:
            lines.append("- Keine spezifischen Makrofenster fuer diesen Open-Block.")

        lines.extend(["", "Earnings radar:"])
        earnings_items = [
            item for item in earnings_calendar
            if session_key is None or item.get("region") in {session_key, "global", "usa"}
        ]
        if earnings_items:
            lines.extend(
                f"- {item['ticker']} {item['session']} {item['scheduled_for'][:10]}"
                for item in earnings_items[:4]
            )
        else:
            lines.append("- Kein nahes Earnings-Setup aus Watchlist und Leitwerten.")

        lines.extend(["", "Watchlist impact:"])
        impacts = brief.get("watchlist_impact", [])
        if impacts:
            lines.extend(f"- {item['summary']}" for item in impacts[:6])
        else:
            lines.append("- Keine direkten Watchlist-Treffer.")

        lines.extend(["", "Crowd radar:"])
        crowd_signals = brief.get("crowd_signals", [])
        if crowd_signals:
            lines.extend(
                f"- {item.get('ticker') or 'Macro'} {item.get('event_type')} | {item.get('mentions')} Reddit/Crowd-Mentions"
                for item in crowd_signals[:3]
            )
        else:
            lines.append("- Kein relevantes Crowd-Cluster.")

        return [
            {
                "event_key": f"{session_label}-brief:{datetime.now().strftime('%Y-%m-%d')}:{index}",
                "category": "morning_brief",
                "title": f"{session_label.title()} Brief",
                "line": line,
                "source_url": "",
            }
            for index, line in enumerate(lines)
        ]

    def _build_midday_update_events(self) -> List[Dict[str, Any]]:
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        brief = self.morning_brief_service.get_brief(snapshot)
        settings = self.portfolio_manager.get_signal_score_settings()
        conviction = self.signal_score_service.build_conviction_index(snapshot, settings)
        top_signals = self._extract_new_events(snapshot, settings)[:5]

        lines = [
            brief.get("headline", "Midday Update"),
            "",
            "What changed since the open:",
            *brief.get("summary_points", [])[:3],
            "",
            "World and macro:",
        ]

        event_layer = brief.get("event_layer", [])
        if event_layer:
            lines.extend(
                f"- {item.get('region', 'global').title()} | {item.get('event_type')} | {item.get('title')}"
                for item in event_layer[:4]
            )
        else:
            lines.append("- Kein dominanter Geo- oder Makrotreiber.")

        lines.extend(["", "High-conviction setups:"])
        if top_signals:
            lines.extend(f"- {event['line']}" for event in top_signals[:4])
        else:
            lines.append("- Keine frischen A-Setups seit dem Open.")

        lines.extend(["", "Portfolio Brain:"])
        congress_watch = brief.get("congress_watch") or []
        if congress_watch:
            lines.append("")
            lines.append("Congress Watch")
            for item in congress_watch[:4]:
                ticker = self._tg_esc(item.get("ticker") or "")
                name = self._tg_esc(str(item.get("name") or "PTR")[:36])
                action = self._tg_esc(str(item.get("action") or item.get("setup") or "watch"))
                amount = self._tg_esc(str(item.get("amount_range") or "amount offen"))
                delay = item.get("delay_days")
                conf = item.get("confidence")
                delay_text = f" | delay {delay}d" if delay is not None else ""
                conf_text = f" | {conf}% conf" if isinstance(conf, int) else ""
                lines.append(f"- {ticker} {action} - {name} ({amount}){delay_text}{conf_text}")
                trigger = self._tg_esc(str(item.get("trigger") or "")[:110])
                invalidation = self._tg_esc(str(item.get("invalidation") or "")[:100])
                if trigger:
                    lines.append(f"   Trigger: {trigger}")
                if invalidation:
                    lines.append(f"   Invalid: {invalidation}")

        portfolio_brain = brief.get("portfolio_brain", {})
        cards = (
            (portfolio_brain.get("at_risk") or [])[:2]
            + (portfolio_brain.get("beneficiaries") or [])[:2]
            + (portfolio_brain.get("hedge_ideas") or [])[:2]
        )
        if cards:
            for card in cards[:5]:
                action = card.get("action") or card.get("bucket") or "watch"
                holding = card.get("holding") or card.get("ticker") or card.get("label") or "Portfolio"
                reason = card.get("reason") or card.get("summary") or card.get("trigger") or ""
                lines.append(f"- {holding} | {action} | {reason}".strip())
        else:
            lines.append("- Kein direkter Portfolio-Handlungsbedarf zur Mittagslage.")

        return [
            {
                "event_key": f"midday-brief:{datetime.now().strftime('%Y-%m-%d')}:{index}",
                "category": "scheduled_brief",
                "title": "Midday Update",
                "line": line,
                "source_url": "",
                "conviction_score": max(conviction.values()) if conviction else None,
            }
            for index, line in enumerate(lines)
        ]

    def _build_close_brief_events(self, session: str) -> List[Dict[str, Any]]:
        """Build events for Europe Close (17:30) or US Close (22:15)."""
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        brief = self.morning_brief_service.get_brief(snapshot)
        region_label = "Europe" if session == "europe" else "US"
        region_key = "europe" if session == "europe" else "usa"
        next_session = "US open (15:30)" if session == "europe" else "Asia open + overnight"
        region_data = brief.get("regions", {}).get(region_key, {})
        avg_chg = region_data.get("avg_change_1d") or 0
        tone = region_data.get("tone") or "mixed"

        lines = [
            f"{region_label} Close Brief",
            "",
            f"Session: {tone} {avg_chg:+.2f}%",
            "",
            "Session summary:",
        ]
        timeline = brief.get("opening_timeline", [])
        session_data = next((t for t in timeline if t.get("label", "").lower() == region_key), None)
        if session_data:
            driver = session_data.get("driver") or ""
            lines.append(f"- Driver: {driver}")
        lines.extend(["", "Top moves today:"])
        for asset in region_data.get("assets", [])[:3]:
            chg = asset.get("change_1d")
            chg_str = f"{chg:+.2f}%" if chg is not None else "—"
            lines.append(f"- {asset.get('label', '')} {chg_str}")
        lines.extend(["", f"Watch for {next_session}:"])
        impacts = brief.get("watchlist_impact", [])
        if impacts:
            lines.extend(f"- {item['summary']}" for item in impacts[:4])
        else:
            lines.append("- Keine Watchlist-Treffer.")
        lines.extend(["", "Overnight risks:"])
        event_layer = brief.get("event_layer", [])
        if event_layer:
            lines.extend(
                f"- {item.get('event_type', 'macro')} | {item.get('region', 'global').title()} | {item.get('title', '')}"
                for item in event_layer[:3]
            )
        else:
            lines.append("- Kein dominanter Overnight-Risikotreiber.")
        return [
            {
                "event_key": f"close-brief:{session}:{datetime.now().strftime('%Y-%m-%d')}:{i}",
                "category": "close_brief",
                "title": f"{region_label} Close Brief",
                "line": line,
                "source_url": "",
            }
            for i, line in enumerate(lines)
        ]

    def _build_close_recap_events(self) -> List[Dict[str, Any]]:
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        brief = self.morning_brief_service.get_brief(snapshot)

        lines = [
            "End of Day Recap",
            "",
            "Closing read:",
            *brief.get("summary_points", [])[:3],
            "",
            "Session pulse:",
        ]

        timeline = brief.get("opening_timeline", [])
        if timeline:
            lines.extend(
                f"- {item.get('label')}: {item.get('tone')} {float(item.get('move') or 0):+.2f}% | {item.get('driver')}"
                for item in timeline[:3]
            )
        else:
            lines.append("- Keine Session-Zusammenfassung verfuegbar.")

        lines.extend(["", "Top risks into next session:"])
        event_layer = brief.get("event_layer", [])
        if event_layer:
            lines.extend(
                f"- {item.get('event_type')} | {item.get('region', 'global').title()} | {item.get('title')}"
                for item in event_layer[:4]
            )
        else:
            lines.append("- Kein dominanter uebernachtlicher Risikotreiber erkannt.")

        lines.extend(["", "Next watchlist focus:"])
        impacts = brief.get("watchlist_impact", [])
        if impacts:
            lines.extend(f"- {item.get('summary')}" for item in impacts[:4])
        else:
            lines.append("- Keine direkte Watchlist-Verschiebung fuer morgen erkannt.")

        return [
            {
                "event_key": f"close-recap:{datetime.now().strftime('%Y-%m-%d')}:{index}",
                "category": "scheduled_brief",
                "title": "End of Day Recap",
                "line": line,
                "source_url": "",
            }
            for index, line in enumerate(lines)
        ]

    async def _build_session_list_events(self, region: str, phase: str) -> List[Dict[str, Any]]:
        region_key = (region or "").strip().lower()
        phase_key = (phase or "").strip().lower()
        if region_key not in {"asia", "europe", "usa"}:
            raise ValueError("region must be asia, europe or usa")
        if phase_key not in {"pre_open", "post_open", "end_of_day"}:
            raise ValueError("phase must be pre_open, post_open or end_of_day")

        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        payload = await self.session_list_service.build_session_lists(snapshot)
        session = payload.get("sessions", {}).get(region_key, {})
        bucket = session.get("phases", {}).get(phase_key, {})

        lines = [
            f"{session.get('label', region_key.title())} {bucket.get('label', phase_key)}",
            "",
            "Equities:",
        ]
        equities = bucket.get("equities") or []
        if equities:
            lines.extend(
                f"- {item['ticker']} | score {item['phase_score']} | {item['change_1w']:+.2f}%"
                for item in equities[:6]
            )
        else:
            lines.append("- Keine Equity-Treffer.")

        lines.extend(["", "ETFs:"])
        etfs = bucket.get("etfs") or []
        if etfs:
            lines.extend(
                f"- {item['ticker']} | score {item['phase_score']} | {item['change_1w']:+.2f}%"
                for item in etfs[:4]
            )
        else:
            lines.append("- Keine ETF-Treffer.")

        lines.extend(["", "Crypto:"])
        crypto = bucket.get("crypto") or []
        if crypto:
            lines.extend(
                f"- {item['ticker']} | score {item['phase_score']} | {item['change_1w']:+.2f}%"
                for item in crypto[:4]
            )
        else:
            lines.append("- Keine Crypto-Treffer.")

        lines.extend(["", "News:"])
        news_items = bucket.get("news") or []
        if news_items:
            lines.extend(
                f"- {item.get('title')} ({item.get('publisher')})"
                for item in news_items[:4]
            )
        else:
            lines.append("- Keine priorisierten News.")

        return [
            {
                "event_key": f"session-list:{region_key}:{phase_key}:{datetime.now().strftime('%Y-%m-%d')}:{index}",
                "category": "session_list",
                "title": f"{region_key.title()} {phase_key}",
                "line": line,
                "source_url": "",
            }
            for index, line in enumerate(lines)
        ]

    def _extract_new_events(self, snapshot: Dict[str, Any], settings: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        new_events: List[Dict[str, Any]] = []
        settings = settings or self.portfolio_manager.get_signal_score_settings()
        high_conviction = self.signal_score_service.build_conviction_index(snapshot, settings)

        for signal in snapshot.get("ticker_signals", []):
            conviction_score = high_conviction.get(("ticker", signal.get("ticker")))
            if conviction_score is None:
                continue
            for event in signal.get("events", []):
                event_key = (
                    f"ticker:{signal.get('ticker')}:{event.get('owner_name')}:{event.get('trade_date')}:"
                    f"{event.get('transaction_code')}:{event.get('shares')}"
                )
                if event_key in sent_keys:
                    continue
                action = (event.get("action") or "").upper()
                line = (
                    f"{signal.get('ticker')}: {action} by {event.get('owner_name')} "
                    f"on {event.get('trade_date')} | filed {event.get('filed_date')} | "
                    f"{event.get('shares')} shares"
                )
                if event.get("value_label"):
                    line += f" | {event.get('value_label')}"
                new_events.append(
                    {
                        "event_key": event_key,
                        "category": "ticker",
                        "title": signal.get("ticker") or "Ticker Signal",
                        "line": line,
                        "source_url": event.get("source_url") or signal.get("source_url") or "",
                        "source_label": "SEC Form 4",
                        "conviction_score": conviction_score,
                    }
                )

        for signal in snapshot.get("politician_signals", []):
            for trade in signal.get("trades", []):
                conviction_score = high_conviction.get(("politician", signal.get("name"), trade.get("ticker")))
                if conviction_score is None:
                    continue
                event_key = (
                    f"politician:{signal.get('name')}:{trade.get('ticker') or trade.get('asset')}:"
                    f"{trade.get('trade_date')}:{trade.get('action')}:{trade.get('amount_range')}"
                )
                if event_key in sent_keys:
                    continue
                action = (trade.get("action") or "").upper()
                line = (
                    f"{signal.get('name')}: {action} {trade.get('ticker') or trade.get('asset')} "
                    f"on {trade.get('trade_date')} | filed {trade.get('notification_date')} | "
                    f"{trade.get('amount_range')}"
                )
                new_events.append(
                    {
                        "event_key": event_key,
                        "category": "politician",
                        "title": signal.get("name") or "Congress Signal",
                        "line": line,
                        "source_url": trade.get("source_url") or signal.get("source_url") or "",
                        "source_label": "House PTR",
                        "conviction_score": conviction_score,
                    }
                )

        new_events.sort(key=self._event_priority)
        return new_events

    def _extract_critical_market_events(self, brief: Dict[str, Any], sent_keys: set[str]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        today = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).strftime("%Y-%m-%d")
        min_critical_score = self._safe_int_env("CRITICAL_MARKET_ALERT_MIN_SCORE", 82, minimum=50)
        portfolio_tickers = self._portfolio_tickers()
        watchlist_tickers = self._watchlist_tickers()

        macro_candidates = [
            *(brief.get("event_layer") or [])[:12],
            *(brief.get("event_pings") or [])[:10],
            *(brief.get("top_news") or [])[:12],
        ]
        macro_audit = {
            "scanned_at": datetime.utcnow().isoformat(),
            "candidates": len(macro_candidates),
            "quality_passed": 0,
            "already_sent": 0,
            "cooldown_blocked": 0,
            "story_duplicate": 0,
            "eligible": 0,
        }
        story_registry = self._news_story_registry()
        for item in macro_candidates:
            macro_event = self._normalize_macro_alert_event(item, min_critical_score)
            if not macro_event:
                continue
            macro_audit["quality_passed"] += 1
            if macro_event["event_key"] in sent_keys:
                macro_audit["already_sent"] += 1
                continue
            if not self._macro_alert_can_send(macro_event):
                macro_audit["cooldown_blocked"] += 1
                continue
            if not self._news_story_can_send(macro_event, story_registry):
                macro_audit["story_duplicate"] += 1
                continue
            macro_audit["eligible"] += 1
            events.append(macro_event)
            story_registry.append(self._news_story_descriptor(macro_event))

        for item in (brief.get("watchlist_impact") or [])[:10]:
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            severity = str(item.get("severity") or item.get("impact") or "").lower()
            ticker = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
            if severity not in {"high", "critical", "risk"} or not ticker:
                continue
            event_key = f"critical-watchlist:{today}:{ticker}:{re.sub(r'[^a-zA-Z0-9]+', '-', summary.lower())[:70]}"
            if event_key in sent_keys:
                continue
            direction = self._event_direction_label(item)
            events.append(
                {
                    "event_key": event_key,
                    "category": "critical_watchlist",
                    "title": str(ticker),
                    "line": f"{direction} Watchlist | {ticker}: {summary}",
                    "source_url": item.get("source_url") or item.get("url") or "",
                    "source_label": "Watchlist impact",
                    "priority": 5,
                }
            )

        for item in (brief.get("earnings_results") or [])[:10]:
            ticker = str(item.get("ticker") or "").upper()
            status = str(item.get("status") or "").lower()
            if not ticker or status not in {"beat", "miss"}:
                continue
            revenue_yoy = item.get("revenue_yoy")
            guidance_label = str(item.get("guidance_label") or "").lower()
            portfolio_hit = ticker in portfolio_tickers
            watchlist_hit = ticker in watchlist_tickers
            important = portfolio_hit or watchlist_hit or status == "miss" or "raise" in guidance_label or "cut" in guidance_label
            if not important:
                continue
            event_key = f"critical-earnings-result:{today}:{ticker}:{status}:{guidance_label[:24]}"
            if event_key in sent_keys:
                continue
            direction = "↑" if status == "beat" and "cut" not in guidance_label else "↓" if status == "miss" or "cut" in guidance_label else "→"
            revenue_label = f"{float(revenue_yoy):+.1f}% YoY Umsatz" if isinstance(revenue_yoy, (int, float)) else "Umsatz offen"
            scope = "Portfolio" if portfolio_hit else "Watchlist" if watchlist_hit else "Earnings"
            events.append(
                {
                    "event_key": event_key,
                    "category": "critical_earnings_result",
                    "title": f"{ticker} Earnings {status}",
                    "line": f"{direction} {scope} | {ticker}: {status.upper()} | {revenue_label} | Guidance {guidance_label or 'offen'}",
                    "source_url": item.get("source_url") or item.get("url") or "",
                    "source_label": "Earnings results",
                    "priority": 4 if portfolio_hit else 8,
                }
            )

        for item in (brief.get("earnings_calendar") or [])[:12]:
            ticker = str(item.get("ticker") or "").upper()
            days_until = item.get("days_until")
            importance = str(item.get("importance") or "").lower()
            try:
                near = int(days_until) <= 1
            except Exception:
                scheduled = str(item.get("scheduled_for") or "")
                near = scheduled.startswith(today)
            if not ticker or not (near and importance in {"watchlist", "portfolio", "sp500"}):
                continue
            event_key = f"critical-earnings:{today}:{ticker}"
            if event_key in sent_keys:
                continue
            portfolio_hit = ticker in portfolio_tickers
            watchlist_hit = ticker in watchlist_tickers
            events.append(
                {
                    "event_key": event_key,
                    "category": "critical_earnings",
                    "title": f"{ticker} Earnings",
                    "line": f"→ {'Portfolio' if portfolio_hit else 'Watchlist' if watchlist_hit else 'Earnings'} | {ticker}: Earnings-Fenster steht an. Danach Umsatz, EPS, Guidance und Kursreaktion gegen Plan pruefen.",
                    "source_url": "",
                    "source_label": "Earnings radar",
                    "priority": 9,
                }
            )

        min_future_star_score = self._safe_int_env("FUTURE_STAR_ALERT_MIN_SCORE", 72, minimum=50)
        for item in (brief.get("future_stars") or [])[:8]:
            ticker = str(item.get("ticker") or "").upper()
            if not ticker:
                continue
            score = item.get("score")
            try:
                numeric_score = float(score)
            except Exception:
                numeric_score = 0.0
            quality_gate = str(item.get("quality_gate") or "").lower()
            if quality_gate != "passed" or numeric_score < min_future_star_score:
                continue
            event_key = f"future-star:{today}:{ticker}"
            if event_key in sent_keys:
                continue
            revenue = item.get("revenue_growth")
            revenue_label = f"{float(revenue):+.1f}% Umsatz" if revenue not in (None, "") else "Umsatz n/a"
            catalyst = str(item.get("catalyst") or item.get("reason") or "").strip()
            risk = str(item.get("risk") or "").strip()
            line = f"↑ Future Star | {ticker}: Kandidat {numeric_score:.0f}/100 | {revenue_label}"
            if catalyst:
                line += f" | Katalysator: {catalyst}"
            if risk:
                line += f" | Risiko: {risk}"
            events.append(
                {
                    "event_key": event_key,
                    "category": "future_star",
                    "title": f"Future Star {ticker}",
                    "line": line,
                    "source_url": "",
                    "source_label": "Future Stars scanner",
                    "conviction_score": numeric_score,
                    "priority": 18,
                }
            )

        self.portfolio_manager.set_app_setting("macro_alert_last_audit", json.dumps(macro_audit))
        return sorted(events, key=lambda event: (int(event.get("priority") or 99), str(event.get("event_key") or "")))

    def _normalize_macro_alert_event(self, item: Dict[str, Any], min_score: int) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        title = str(item.get("title") or item.get("headline") or item.get("summary") or "").strip()
        if not title:
            return None

        intelligence = item.get("event_intelligence") if isinstance(item.get("event_intelligence"), dict) else {}
        trade_impact = item.get("trade_impact") if isinstance(item.get("trade_impact"), dict) else {}
        intelligence_with_trade = {**trade_impact, **intelligence}
        event_type = self._macro_event_type(item, title)
        if not event_type:
            return None

        country = self._macro_event_country(item, title)
        if not country and event_type == "IPO":
            country = "IPO Market"
        region = str(item.get("region") or country or "Global").strip()
        if not country and region.lower() == "global":
            return None

        impact_score = self._macro_impact_score(item, intelligence)
        severity = self._macro_severity(item, impact_score)
        if severity not in {"high", "critical"} and impact_score < min_score:
            return None

        affected_assets = self._macro_affected_assets(item, intelligence_with_trade, event_type)
        if not affected_assets:
            return None

        source_status = str(item.get("source_status") or item.get("source_label") or item.get("publisher") or "Market radar").strip()
        why = str(
            intelligence.get("why_now")
            or item.get("summary")
            or item.get("reason")
            or "Makro-Event mit potenzieller Auswirkung auf Risiko, Sektoren und Indizes."
        ).strip()
        source_quality = self._macro_source_quality(item, source_status)
        source_contract = self._telegram_news_source_contract(item, require_tier_1=True)
        if source_contract.get("valid") is not True:
            return None
        explicit_trigger = str(intelligence.get("trigger") or trade_impact.get("trigger") or item.get("trigger") or "").strip()
        explicit_invalidation = str(
            intelligence.get("invalidation") or trade_impact.get("invalidation") or item.get("invalidation") or ""
        ).strip()
        if not self._macro_alert_quality_gate(
            event_type=event_type,
            title=title,
            why=why,
            affected_assets=affected_assets,
            source_quality=source_quality,
            explicit_trigger=explicit_trigger,
            explicit_invalidation=explicit_invalidation,
            impact_score=impact_score,
            severity=severity,
        ):
            return None

        trigger = explicit_trigger or self._default_macro_trigger(event_type)
        invalidation = explicit_invalidation or self._default_macro_invalidation(event_type)
        meaning = self._macro_alert_meaning(event_type, country or region, affected_assets)
        read_through = self._macro_alert_read_through(event_type, country or region, affected_assets, title)
        critical_check = self._macro_alert_critical_check(event_type, source_quality)
        confidence_label = self._macro_confidence_label(source_quality, explicit_trigger, explicit_invalidation, impact_score)
        signal_status = self._macro_signal_status(source_quality, explicit_trigger, explicit_invalidation)
        horizon = self._macro_alert_horizon(event_type)
        mechanism = self._macro_alert_mechanism(event_type, affected_assets)
        base_case = self._macro_alert_base_case(event_type, affected_assets)
        next_check = self._macro_alert_next_check(event_type)
        edge_question = self._macro_alert_edge_question(event_type, affected_assets)
        fact_status = "bestaetigt" if source_quality == "strong" else "plausibel - zweite Quelle ausstehend"
        action = str(intelligence.get("action") or trade_impact.get("action") or item.get("action") or "watch").strip().lower()
        identity = self._macro_event_identity(event_type, country or region, title)
        bucket_identity = self._macro_event_bucket_identity(event_type, country or region, affected_assets)
        event = {
            "event_key": f"macro-alert:{identity}:{severity}",
            "macro_identity": identity,
            "macro_bucket_identity": bucket_identity,
            "category": "macro_alert",
            "title": title,
            "line": f"{country or region} / {event_type}: {title}",
            "event_type": event_type,
            "severity": severity,
            "impact_score": int(round(impact_score)),
            "country": country or region,
            "region": region,
            "why_it_matters": why,
            "meaning": meaning,
            "read_through": read_through,
            "critical_check": critical_check,
            "affected_assets": affected_assets[:8],
            "trigger": trigger,
            "invalidation": invalidation,
            "action": action,
            "confidence_label": confidence_label,
            "signal_status": signal_status,
            "fact_status": fact_status,
            "horizon": horizon,
            "market_mechanism": mechanism,
            "base_case": base_case,
            "next_check": next_check,
            "edge_question": edge_question,
            "source_quality": source_quality,
            "source_url": source_contract.get("source_url"),
            "source_label": source_status,
            "published_at": source_contract.get("published_at"),
            "conviction_score": int(round(impact_score)),
            "priority": 1 if severity == "critical" else 3,
        }
        event["story_identity"] = self._news_story_descriptor(event).get("identity")
        return event

    def _macro_alert_quality_gate(
        self,
        *,
        event_type: str,
        title: str,
        why: str,
        affected_assets: List[str],
        source_quality: str,
        explicit_trigger: str,
        explicit_invalidation: str,
        impact_score: float,
        severity: str,
    ) -> bool:
        if source_quality == "weak":
            return False
        if len(title.strip()) < 18 or len(why.strip()) < 36:
            return False
        if len(affected_assets) < 2:
            return False
        allows_generated_context = event_type in {"Public Figure", "IPO"} and source_quality == "strong" and impact_score >= 90
        if not (explicit_trigger or explicit_invalidation or allows_generated_context):
            return False
        if severity != "critical" and impact_score < self._safe_int_env("MACRO_ALERT_STRICT_MIN_SCORE", 86, minimum=50):
            return False
        return True

    def _macro_source_quality(self, item: Dict[str, Any], source_status: str) -> str:
        text = " ".join(
            str(value or "")
            for value in [
                source_status,
                item.get("source_status"),
                item.get("source_label"),
                item.get("publisher"),
                item.get("source"),
            ]
        ).lower()
        if re.search(r"\b(rumou?r|unconfirmed|social|reddit|fast mode|unknown|n/a|none)\b", text):
            return "weak"
        if re.search(r"\b(official|confirmed|filing|central bank|government|sec|exchange|trusted|provider|wire|reuters|bloomberg|ap news|associated press|wsj|wall street journal|financial times|ft.com|cnbc|marketwatch)\b", text):
            return "strong"
        if item.get("source_url") or item.get("url") or item.get("link"):
            return "medium"
        return "weak"

    def _macro_alert_meaning(self, event_type: str, country: str, assets: List[str]) -> str:
        asset_label = ", ".join(assets[:4]) if assets else "Risk assets"
        templates = {
            "Conflict": f"Risk-off check fuer {asset_label}: Energie, Gold, Defense und Index-Risiko muessen gegen die erste Reaktion geprueft werden.",
            "Energy": f"Inflations- und Margencheck fuer {asset_label}: Oel/Gas kann Indizes, Airlines, Chemie und Konsum kurzfristig verzerren.",
            "Central Bank": f"Zins- und Bewertungscheck fuer {asset_label}: Duration, Growth, Banken und FX reagieren oft schneller als Fundamentaldaten.",
            "Election": f"Policy- und Sektorrotationscheck fuer {asset_label}: erst Gewinner/Verlierer nach bestaetigtem Resultat trennen.",
            "Policy": f"Regulierungs- und Lieferkettencheck fuer {asset_label}: wichtig ist, ob die Meldung offiziell ist und wer Umsatz/Margen verliert.",
            "Public Figure": f"Aussagen-Risiko fuer {asset_label}: entscheidend ist, ob Politik, Regulierung, Zinsen oder Sektorumsatz wirklich betroffen sind.",
            "IPO": f"IPO-Read-through fuer {asset_label}: relevant sind Bewertung, Nachfrage, Lock-up, Peer-Multiples und ob der Sektor Kapital anzieht.",
            "Disaster": f"Supply- und Versicherungsschadencheck fuer {asset_label}: nur relevant, wenn operative Schaeden oder Rohstoffpreise reagieren.",
        }
        return templates.get(event_type, f"Makro-Kontext fuer {country}: {asset_label} nur mit bestaetigter Preisreaktion einordnen.")

    def _macro_alert_read_through(self, event_type: str, country: str, assets: List[str], title: str) -> str:
        asset_label = ", ".join(assets[:4]) if assets else "Risk assets"
        templates = {
            "Conflict": (
                f"Erst Rohstoffe, Defense, Gold und breite Futures gegenpruefen. Fuer {asset_label} ist die Aussage nur stark, "
                "wenn die erste Risk-off-Reaktion nicht sofort verkauft wird."
            ),
            "Energy": (
                f"Kosten-, Inflations- und Margendruck fuer {asset_label} pruefen. Relevant wird es erst, wenn Futures und "
                "Energieaktien gemeinsam bestaetigen."
            ),
            "Central Bank": (
                f"Duration-Read-through fuer {asset_label}: Zinsen und Dollar muessen dieselbe Richtung zeigen, sonst ist die "
                "Aktienreaktion oft nur Rauschen."
            ),
            "Election": (
                f"Policy-Read-through fuer {asset_label}: keine voreilige Rotation, bis Resultat, Koalition oder Umfragen belastbar sind."
            ),
            "Policy": (
                f"Umsatz- und Margen-Read-through fuer {asset_label}: nur handeln, wenn betroffene Firmen/Sektoren wirklich Exposure haben."
            ),
            "Public Figure": (
                f"Statement-Read-through fuer {asset_label}: wichtig ist nicht die Person, sondern ob Politik, Zinsen, Tarife, "
                "Regulierung oder Nachfrage konkret betroffen sind."
            ),
            "IPO": (
                f"Kapitalmarkt-Read-through fuer {asset_label}: stark nur, wenn Nachfrage, Bewertung, Lock-up und Peer-Reaktion zusammenpassen."
            ),
            "Disaster": (
                f"Operationaler Read-through fuer {asset_label}: wichtig nur bei messbarem Schaden an Produktion, Transport oder Versicherung."
            ),
        }
        return templates.get(
            event_type,
            f"Read-through fuer {country}: {title[:90]} nur mit Quelle, Preisreaktion und Volumen ernst nehmen.",
        )

    def _macro_alert_critical_check(self, event_type: str, source_quality: str) -> str:
        source_part = "Primaerquelle oder verifizierte Wire" if source_quality == "strong" else "zweite bestaetigende Quelle"
        checks = {
            "Conflict": "Kein Reflex-Trade: offizielle Bestaetigung, Oel/Gold/Defense und Index-Futures muessen gemeinsam reagieren.",
            "Energy": "Nicht handeln, wenn nur Oel spike't: Energieaktien, Spreads und betroffene Margensektoren muessen bestaetigen.",
            "Central Bank": "Statement erst nach Rates/Dollar/Index-Reaktion einordnen; Pressekonferenz kann die erste Bewegung drehen.",
            "Election": "Keine These auf einzelne Schlagzeile: Resultat/Koalition und Sektorreaktion abwarten.",
            "Policy": "Nur ernst nehmen, wenn Massnahme offiziell, zeitlich konkret und Umsatz-/Kostenexposure klar ist.",
            "Public Figure": "Zitat auf Kontext pruefen: offizieller Kanal, voller Wortlaut, direkte Policy-Relevanz und Marktreaktion.",
            "IPO": "Filing/Pricing bestaetigen: Umsatzwachstum, Bewertung, Free Float, Lock-up und Peer-Multiples vergleichen.",
            "Disaster": "Schaden quantifizieren: betroffene Anlagen, Lieferketten, Versicherer und Rohstoffpreise pruefen.",
        }
        return f"{source_part} noetig. {checks.get(event_type, 'Quelle, Preisreaktion, Volumen und Gegenargument vor Aktion pruefen.')}"

    def _macro_alert_horizon(self, event_type: str) -> str:
        return {
            "Conflict": "sofort bis 3 Handelstage; strukturell nur bei anhaltender Eskalation",
            "Energy": "intraday bis mehrere Wochen, abhaengig von Angebotsausfall und Lagerdaten",
            "Central Bank": "erste Reaktion intraday; Bewertungswirkung ueber Wochen bis Monate",
            "Election": "Tage bis Monate, sobald Ergebnis und umsetzbare Politik feststehen",
            "Policy": "Tage bis Quartale, je nach Inkrafttreten und Unternehmens-Exposure",
            "Public Figure": "Minuten bis Tage; laenger nur bei konkreter politischer Umsetzung",
            "IPO": "Pricing bis 30 Tage; Peer-Read-through meist in den ersten Handelstagen",
            "Disaster": "Tage bis Wochen, bis Schaden und Lieferketteneffekt quantifiziert sind",
        }.get(event_type, "intraday zuerst, mittelfristig nur nach fundamentaler Bestaetigung")

    def _macro_alert_mechanism(self, event_type: str, assets: List[str]) -> str:
        asset_label = ", ".join(assets[:4]) if assets else "betroffene Maerkte"
        mechanisms = {
            "Conflict": "Geopolitische Risikopraemie wirkt zuerst ueber Energie, sichere Haefen, Defense und Index-Futures.",
            "Energy": "Rohstoffpreise veraendern Inflationserwartungen und die Margen von Produzenten und Verbrauchern.",
            "Central Bank": "Zinsen und Liquiditaet veraendern Diskontsaetze, Waehrungen und damit Bewertungsmultiplikatoren.",
            "Election": "Erwartete Steuer-, Handels- und Regulierungspolitik verschiebt sektorale Gewinner und Verlierer.",
            "Policy": "Neue Regeln wirken ueber Umsatz, Kosten, Zugang zu Maerkten und Lieferketten.",
            "Public Figure": "Die Aussage bewegt Kurse nur nachhaltig, wenn daraus konkrete Politik oder Nachfragewirkung folgt.",
            "IPO": "Pricing und Nachfrage liefern ein Signal fuer Risikobereitschaft und Vergleichsbewertungen im Sektor.",
            "Disaster": "Produktionsausfaelle, Transportstoerungen und versicherte Schaeden veraendern Angebot und Kosten.",
        }
        return f"{mechanisms.get(event_type, 'Die Meldung muss ueber Preise, Volumen oder Fundamentaldaten in den Markt uebertragen werden.')} Beobachtungskorb: {asset_label}."

    def _macro_alert_base_case(self, event_type: str, assets: List[str]) -> str:
        asset_label = ", ".join(assets[:3]) if assets else "der betroffene Korb"
        cases = {
            "Conflict": "Bedingtes Risk-off-Szenario; keine dauerhafte Bewegung ohne bestaetigte Eskalation und Anschlusskaeufe.",
            "Energy": "Bedingter Inflations- und Margenimpuls; Richtung haengt von Dauer und Groesse des Angebotseffekts ab.",
            "Central Bank": "Rates und FX geben die Richtung vor; Aktienreaktion bleibt zweitrangig, bis beide bestaetigen.",
            "Election": "Zunaechst Volatilitaet statt klarer Richtung; belastbare Sektorrotation erst nach umsetzbarer Politik.",
            "Policy": "Selektiver Firmen- und Sektoreffekt statt pauschaler Index-These.",
            "Public Figure": "Kurzfristiger Volatilitaetsimpuls; Basisszenario bleibt neutral ohne offiziellen Folgeschritt.",
            "IPO": "Sentiment-Signal, keine Aussage ueber die Qualitaet aller Peers; Bewertung und Nachfrage entscheiden.",
            "Disaster": "Lokaler Risikoimpuls; breiter Markteffekt nur bei messbarer Produktions- oder Lieferstoerung.",
        }
        return f"{cases.get(event_type, 'Neutral starten und erst nach Markt- und Quellenbestaetigung einordnen.')} Fokus: {asset_label}."

    def _macro_alert_next_check(self, event_type: str) -> str:
        return {
            "Conflict": "Offizielle Updates sowie Oel, Gold, Defense und Index-Futures gemeinsam pruefen.",
            "Energy": "Brent/WTI, Terminkurve, Energieaktien und betroffene Margensektoren vergleichen.",
            "Central Bank": "2Y/10Y-Renditen, Dollar, Statement und Pressekonferenz gegen die erste Aktienreaktion halten.",
            "Election": "Bestaetigtes Ergebnis, Koalition, Umsetzbarkeit und relative Sektorstaerke abwarten.",
            "Policy": "Originaldokument, Startdatum und konkretes Umsatz-/Kostenexposure der Firmen pruefen.",
            "Public Figure": "Originalzitat und offiziellen Policy-Folgeschritt suchen; erst dann Preis und Volumen bewerten.",
            "IPO": "Filing, Preisspanne, Nachfrage, Free Float, Lock-up und Peer-Reaktion vergleichen.",
            "Disaster": "Schadensumfang, Produktionsstillstand, Transportwege und Versicherungs-Exposure quantifizieren.",
        }.get(event_type, "Primaerquelle, zweite Bestaetigung, Preisreaktion und Volumen pruefen.")

    def _macro_alert_edge_question(self, event_type: str, assets: List[str]) -> str:
        asset_label = ", ".join(assets[:3]) if assets else "betroffene Maerkte"
        questions = {
            "Conflict": f"Bestaetigen Oel, Gold, Defense und Futures dieselbe Risk-off-These fuer {asset_label}?",
            "Energy": f"Ist das ein echter Angebots-/Inflationsimpuls oder nur ein kurzer Oel-Headline-Spike fuer {asset_label}?",
            "Central Bank": f"Stimmen Renditen, Dollar und Growth/Value-Reaktion ueberein, oder widerspricht der Markt der ersten Schlagzeile?",
            "Election": f"Entsteht daraus eine umsetzbare Policy-These fuer {asset_label}, oder nur kurzfristige Wahl-Volatilitaet?",
            "Policy": f"Ist das Umsatz-/Margen-Exposure fuer {asset_label} konkret genug, um eine These zu rechtfertigen?",
            "Public Figure": f"Hat die Aussage offiziellen Policy-Folgeeffekt, oder ist es nur lautes Schlagzeilenrisiko fuer {asset_label}?",
            "IPO": f"Zeigen Nachfrage, Bewertung und Peer-Reaktion echte Kapitalmarktstaerke fuer {asset_label}?",
            "Disaster": f"Ist der Schaden fuer Produktion, Transport oder Versicherung messbar genug, um {asset_label} zu bewegen?",
        }
        return questions.get(event_type, f"Welche Preisreaktion wuerde die These fuer {asset_label} bestaetigen oder widerlegen?")

    def _macro_confidence_label(
        self,
        source_quality: str,
        explicit_trigger: str,
        explicit_invalidation: str,
        impact_score: float,
    ) -> str:
        if source_quality == "strong" and explicit_trigger and explicit_invalidation and impact_score >= 90:
            return "hoch - Quelle und These pruefbar"
        if source_quality in {"strong", "medium"} and (explicit_trigger or explicit_invalidation):
            return "mittel - erst Marktreaktion bestaetigen"
        return "niedrig - nur beobachten"

    def _macro_signal_status(
        self,
        source_quality: str,
        explicit_trigger: str,
        explicit_invalidation: str,
    ) -> str:
        if source_quality == "strong" and explicit_trigger and explicit_invalidation:
            return "SETUP PRUEFEN - kein Trade ohne Preis- und Volumenbestaetigung"
        if source_quality in {"strong", "medium"}:
            return "NUR BEOBACHTEN - Quelle und Marktreaktion weiter bestaetigen"
        return "BLOCKIERT - Quellenlage reicht nicht fuer eine Entscheidung"

    def _macro_event_type_label(self, event_type: str) -> str:
        return {
            "Conflict": "Krieg / Konflikt",
            "Energy": "Energie / Rohstoffe",
            "Central Bank": "Zentralbank / Zinsen",
            "Election": "Wahl / Politik",
            "Policy": "Regulierung / Handelspolitik",
            "Public Figure": "Aussage einer Schluesselperson",
            "IPO": "Boersengang / IPO",
            "Disaster": "Naturereignis / Lieferkette",
        }.get(event_type, event_type or "Makro")

    def _macro_action_label(self, action: str) -> str:
        return {
            "watch": "beobachten und bestaetigen",
            "hedge": "Absicherung pruefen",
            "reduce": "Risiko reduzieren",
            "add": "Aufbau erst nach Bestaetigung pruefen",
            "long": "Long erst nach Bestaetigung pruefen",
            "short": "Short-Risiko pruefen",
            "watch-short": "Short-Risiko beobachten",
            "rebound_or_avoid": "schwache Erholung meiden",
        }.get((action or "watch").lower(), "beobachten und bestaetigen")

    def _macro_source_quality_label(self, source_quality: str) -> str:
        return {
            "strong": "hoch - belastbare Primaer- oder Nachrichtenquelle",
            "medium": "mittel - zweite unabhaengige Quelle suchen",
            "weak": "niedrig - nicht als Push-Signal verwenden",
        }.get((source_quality or "").lower(), "offen - Quelle manuell pruefen")

    def _macro_event_type(self, item: Dict[str, Any], title: str) -> str | None:
        raw = str(item.get("event_type") or item.get("type") or "").lower()
        haystack = f"{title} {raw} {item.get('impact') or ''} {item.get('severity') or ''}".lower()
        if raw in {"conflict", "war"} or re.search(r"\b(war|missile|attack|conflict|invasion|strike|terror|escalation)\b", haystack):
            return "Conflict"
        if raw in {"election", "vote"} or re.search(r"\b(election|vote|ballot|president|parliament|coalition|campaign)\b", haystack):
            return "Election"
        if raw in {"central_bank", "cb"} or re.search(r"\b(fed|ecb|boj|central bank|rate decision|yield|inflation)\b", haystack):
            return "Central Bank"
        if raw in {"energy", "oil"} or re.search(r"\b(oil|crude|brent|opec|gas|lng|energy|red sea)\b", haystack):
            return "Energy"
        if raw in {"public_figure", "person", "statement"} or (
            re.search(r"\b(trump|powell|yellen|bessent|lutnick|musk|huang|cook|zuckerberg|bezos|dimon|lagarde|leyen)\b", haystack)
            and re.search(r"\b(says|said|warns|warned|backs|calls for|announces|threatens|plans|pledges|statement|speech|interview|tariff|rate|crypto|oil|china|defense|ai)\b", haystack)
        ):
            return "Public Figure"
        if raw in {"policy", "sanction"} or re.search(r"\b(tariff|sanction|policy|regulation|trade war|export control)\b", haystack):
            return "Policy"
        if raw in {"ipo", "listing"} or re.search(r"\b(ipo|initial public offering|go public|goes public|listing|listed|debut|prices shares|files for ipo|confidentially files)\b", haystack):
            return "IPO"
        if raw in {"disaster", "nat"} or re.search(r"\b(earthquake|flood|wildfire|hurricane|typhoon|disaster)\b", haystack):
            return "Disaster"
        return None

    def _macro_event_country(self, item: Dict[str, Any], title: str) -> str | None:
        geo = item.get("geo") if isinstance(item.get("geo"), dict) else {}
        direct = str(item.get("country") or geo.get("country") or geo.get("place") or "").strip()
        if direct:
            return direct
        haystack = f"{title} {item.get('region') or ''}".lower()
        lookup = [
            ("Ukraine", ["ukraine", "kyiv", "odesa"]),
            ("Russia", ["russia", "moscow"]),
            ("United States", ["usa", "u.s.", "washington", "new york", "wall street", "federal reserve", "fed"]),
            ("United States", ["trump", "white house", "powell", "yellen", "bessent", "lutnick"]),
            ("Germany", ["germany", "berlin", "dax"]),
            ("France", ["france", "paris"]),
            ("United Kingdom", ["united kingdom", "britain", "uk ", "london"]),
            ("Israel", ["israel", "gaza", "jerusalem"]),
            ("Iran", ["iran", "tehran"]),
            ("Saudi Arabia", ["saudi", "riyadh", "opec"]),
            ("Middle East", ["middle east", "red sea", "gulf"]),
            ("China", ["china", "beijing", "shanghai"]),
            ("Taiwan", ["taiwan", "taipei"]),
            ("Japan", ["japan", "tokyo"]),
            ("South Korea", ["korea", "seoul"]),
            ("India", ["india", "mumbai", "delhi"]),
            ("Europe", ["europe", "ecb", "eu "]),
        ]
        for country, terms in lookup:
            if any(term in haystack for term in terms):
                return country
        region = str(item.get("region") or "").strip()
        return region if region and region.lower() != "global" else None

    def _macro_impact_score(self, item: Dict[str, Any], intelligence: Dict[str, Any]) -> float:
        for value in [intelligence.get("impact_score"), item.get("impact_score"), item.get("score"), item.get("confidence")]:
            try:
                numeric = float(value)
                if numeric > 0:
                    return min(100.0, numeric)
            except Exception:
                pass
        severity = str(item.get("severity") or item.get("impact") or "").lower()
        if severity == "critical":
            return 92.0
        if severity in {"high", "risk", "risk_off"}:
            return 84.0
        if severity == "medium":
            return 68.0
        return 55.0

    def _macro_severity(self, item: Dict[str, Any], impact_score: float) -> str:
        raw = str(item.get("severity") or item.get("impact") or "").lower()
        if raw in {"critical", "high"}:
            return raw
        if impact_score >= 90:
            return "critical"
        if impact_score >= 78:
            return "high"
        return "medium"

    def _macro_affected_assets(self, item: Dict[str, Any], intelligence: Dict[str, Any], event_type: str) -> List[str]:
        assets: List[str] = []
        raw_values = [
            intelligence.get("affected_assets"),
            intelligence.get("symbols"),
            item.get("affected_assets"),
            item.get("symbols"),
            item.get("tickers"),
            item.get("ticker"),
            item.get("symbol"),
            item.get("asset"),
        ]
        for raw in raw_values:
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                text = str(value or "").strip().upper()
                if text and text not in assets:
                    assets.append(text)
        defaults = {
            "Conflict": ["GLD", "XLE", "TLT", "SPY"],
            "Energy": ["CL=F", "XLE", "USO", "DAX"],
            "Central Bank": ["TLT", "QQQ", "SPY", "EUR/USD"],
            "Election": ["SPY", "DAX", "XLF", "XLI"],
            "Policy": ["SPY", "DAX", "CNH", "XLI"],
            "Public Figure": ["SPY", "QQQ", "DXY", "TLT"],
            "IPO": ["IPO", "QQQ", "IWM", "XLY"],
            "Disaster": ["GLD", "DBA", "XLE"],
        }
        for value in defaults.get(event_type, []):
            if value not in assets:
                assets.append(value)
        return assets

    def _default_macro_trigger(self, event_type: str) -> str:
        defaults = {
            "Conflict": "Vertrauenswürdige Bestätigung, steigendes Volumen und erste Marktreaktion nach der nächsten liquiden Eröffnung.",
            "Energy": "Öl- und Energie-Futures halten die Bewegung 30 bis 60 Minuten und verbundene Sektoren bestätigen.",
            "Central Bank": "Renditen, Dollar und Wachstumsindizes bestätigen die Neubewertung nach der Erklärung.",
            "Election": "Bestätigtes Ergebnis oder Umfrageverschiebung plus Sektorrotation in der ersten liquiden Sitzung.",
            "Policy": "Offizielle Bestätigung und Reaktion betroffener Sektoren oder Indizes, nicht nur Gerüchtefluss.",
            "Public Figure": "Offizielles Zitat und erste sektorübergreifende Reaktion bei Sektoren, Renditen, Dollar oder Index-Futures.",
            "IPO": "Bestätigte Anmeldung, Preisfestsetzung oder Debütdaten plus Reaktion der Vergleichsgruppe nach dem ersten liquiden Kurs.",
            "Disaster": "Bestätigter operativer oder wirtschaftlicher Schaden und Reaktion bei Rohstoffen oder Versicherern.",
        }
        return defaults.get(event_type, "Bestätigte Quelle plus Anschlussbewegung bei Kurs und Volumen.")

    def _default_macro_invalidation(self, event_type: str) -> str:
        defaults = {
            "Conflict": "Ungültig, wenn offizielle Quellen die Eskalation verneinen oder Risikoanlagen die erste Bewegung vollständig umkehren.",
            "Energy": "Ungültig, wenn Öl unter das Niveau vor der Meldung fällt oder der Angebotseffekt verneint wird.",
            "Central Bank": "Ungültig, wenn die Rendite- und Dollarreaktion nachlässt und Aktien in das vorherige Regime zurückkehren.",
            "Election": "Ungültig, wenn das Ergebnis unbestätigt bleibt oder betroffene Sektoren nicht reagieren.",
            "Policy": "Ungültig, wenn es nur bei einem Vorschlag bleibt oder keine betroffene Anlage reagiert.",
            "Public Figure": "Ungültig, wenn die Aussage zurückgenommen wird, offizieller Kontext fehlt oder der Marktkorb nicht reagiert.",
            "IPO": "Ungültig, wenn Bewertung, Streubesitz, Haltefrist oder erste Kursreaktion keine Sektorwirkung stützen.",
            "Disaster": "Ungültig, wenn der wirtschaftliche Schaden begrenzt bleibt und die sektorübergreifende Reaktion nachlässt.",
        }
        return defaults.get(event_type, "Ungültig, wenn die Meldung unbestätigt bleibt oder der Kurs nicht reagiert.")

    def _macro_event_identity(self, event_type: str, country: str, title: str) -> str:
        safe = re.sub(r"[^a-z0-9]+", "-", f"{event_type}-{country}-{title}".lower()).strip("-")
        return safe[:96] or "macro-event"

    def _macro_event_bucket_identity(self, event_type: str, country: str, assets: List[str]) -> str:
        normalized_assets = sorted(
            {
                re.sub(r"[^a-z0-9.-]+", "", str(asset or "").lower())
                for asset in assets[:6]
                if str(asset or "").strip()
            }
        )
        asset_part = "-".join(normalized_assets[:4]) or "market"
        safe = re.sub(r"[^a-z0-9.-]+", "-", f"{event_type}-{country}-{asset_part}".lower()).strip("-")
        return safe[:120] or "macro-bucket"

    def _telegram_news_source_contract(
        self,
        item: Dict[str, Any],
        require_tier_1: bool = True,
    ) -> Dict[str, Any]:
        evidence = item.get("source_evidence") if isinstance(item.get("source_evidence"), dict) else {}
        correction = evidence.get("correction_status") if isinstance(evidence.get("correction_status"), dict) else {}
        source_url = str(item.get("source_url") or item.get("url") or item.get("link") or evidence.get("url") or "").strip()
        parsed = urlparse(source_url)
        published_raw = item.get("published_at") or evidence.get("published_at")
        published_dt = self._paper_trade_datetime(published_raw)
        published_at = self._paper_trade_time(published_raw)
        source_quality = str(item.get("source_quality") or evidence.get("quality") or "").strip().lower()
        errors: List[str] = []
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            errors.append("clickable_source_url_required")
        if evidence.get("link_verified") is not True:
            errors.append("source_link_not_verified")
        if not published_at:
            errors.append("publication_timestamp_required")
        elif published_dt:
            now = datetime.now(published_dt.tzinfo or ZoneInfo("UTC"))
            max_age_hours = self._safe_int_env("TELEGRAM_NEWS_MAX_AGE_HOURS", 24, minimum=1)
            if published_dt > now + timedelta(minutes=10):
                errors.append("publication_timestamp_in_future")
            elif published_dt < now - timedelta(hours=max_age_hours):
                errors.append("publication_timestamp_stale")
        if require_tier_1 and source_quality not in {"tier_1", "official_primary"}:
            errors.append("tier_1_or_primary_source_required")
        if str(correction.get("status") or "") in {
            "correction_detected",
            "retracted_or_withdrawn",
            "source_unavailable",
        }:
            errors.append("source_corrected_retracted_or_unavailable")
        return {
            "valid": not errors,
            "errors": errors,
            "source_url": source_url,
            "published_at": published_dt.isoformat() if published_dt else "",
            "published_display": published_at,
            "source_quality": source_quality,
        }

    def _canonical_news_url(self, value: Any) -> str:
        raw = str(value or "").strip()
        try:
            parsed = urlparse(raw)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return ""
            path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
            return urlunparse((parsed.scheme.lower(), parsed.hostname.lower(), path, "", "", ""))
        except Exception:
            return ""

    def _news_story_descriptor(self, item: Dict[str, Any]) -> Dict[str, Any]:
        title = str(item.get("title") or item.get("headline") or item.get("line") or "").strip()
        normalized_title = re.sub(r"[^a-z0-9äöüß]+", " ", title.lower()).strip()
        stop_words = {
            "a", "an", "and", "as", "at", "auf", "aus", "bei", "das", "der", "die", "ein", "eine",
            "for", "from", "für", "im", "in", "ist", "mit", "nach", "of", "on", "sagt", "says",
            "the", "to", "und", "von", "vor", "with", "zu", "zur", "zum", "update", "breaking",
        }
        tokens = sorted(
            {
                token
                for token in normalized_title.split()
                if len(token) >= 3 and token not in stop_words
            }
        )[:24]
        precomputed_identity = str(item.get("story_identity") or "").strip()
        explicit_id = str(
            item.get("story_id")
            or item.get("event_cluster_id")
            or item.get("cluster_id")
            or ""
        ).strip()
        canonical_url = self._canonical_news_url(
            item.get("source_url") or item.get("url") or item.get("link")
        )
        event_type = str(item.get("event_type") or item.get("type") or "news").strip().lower()
        ticker = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
        country = str(item.get("country") or item.get("region") or "global").strip().lower()
        # Keep the scope stable when the same story is enriched differently by the
        # rich brief and critical-alert pipelines.
        scope = f"{event_type}:{ticker or country}"
        published_raw = item.get("published_at")
        published = None
        try:
            published = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00")) if published_raw else None
            if published and published.tzinfo is None:
                published = published.replace(tzinfo=ZoneInfo("UTC"))
        except Exception:
            published = None
        correction = item.get("source_evidence") if isinstance(item.get("source_evidence"), dict) else {}
        correction = correction.get("correction_status") if isinstance(correction.get("correction_status"), dict) else {}
        revision = str(correction.get("status") or "original")
        raw_identity = explicit_id or f"{scope}|{published.isoformat() if published else ''}|{' '.join(tokens)}|{revision}"
        identity = precomputed_identity or (
            "news-story:" + hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:24]
        )
        return {
            "identity": identity,
            "explicit_id": explicit_id,
            "canonical_url": canonical_url,
            "scope": scope,
            "tokens": tokens,
            "published_at": published.isoformat() if published else None,
            "revision": revision,
            "title": title,
        }

    def _news_story_registry(self) -> List[Dict[str, Any]]:
        if not getattr(self, "portfolio_manager", None):
            return []
        raw = self.portfolio_manager.get_app_setting("telegram_news_story_registry_v1", "[]")
        try:
            rows = json.loads(raw or "[]")
        except Exception:
            rows = []
        if not isinstance(rows, list):
            rows = []
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(
            hours=self._safe_int_env("NEWS_STORY_DEDUPE_HOURS", 168, minimum=1)
        )
        active = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                delivered = datetime.fromisoformat(str(row.get("delivered_at") or "").replace("Z", "+00:00"))
                if delivered.tzinfo is None:
                    delivered = delivered.replace(tzinfo=ZoneInfo("UTC"))
            except Exception:
                continue
            if delivered >= cutoff:
                active.append(row)
        return active[-300:]

    def _news_story_descriptors_match(self, current: Dict[str, Any], previous: Dict[str, Any]) -> bool:
        if current.get("revision") != previous.get("revision"):
            return False
        if current.get("explicit_id") and current.get("explicit_id") == previous.get("explicit_id"):
            return True
        if current.get("canonical_url") and current.get("canonical_url") == previous.get("canonical_url"):
            return True
        if current.get("identity") == previous.get("identity"):
            return True
        if not current.get("scope") or current.get("scope") != previous.get("scope"):
            return False
        try:
            current_time = datetime.fromisoformat(str(current.get("published_at") or ""))
            previous_time = datetime.fromisoformat(str(previous.get("published_at") or ""))
            if abs((current_time - previous_time).total_seconds()) > 12 * 3600:
                return False
        except Exception:
            return False
        current_tokens = set(current.get("tokens") or [])
        previous_tokens = set(previous.get("tokens") or [])
        if not current_tokens or not previous_tokens:
            return False
        intersection = len(current_tokens & previous_tokens)
        union = len(current_tokens | previous_tokens)
        containment = intersection / max(1, min(len(current_tokens), len(previous_tokens)))
        jaccard = intersection / max(1, union)
        return containment >= 0.70 or jaccard >= 0.55

    def _news_story_can_send(self, item: Dict[str, Any], registry: Optional[List[Dict[str, Any]]] = None) -> bool:
        descriptor = self._news_story_descriptor(item)
        return not any(
            self._news_story_descriptors_match(descriptor, previous)
            for previous in (registry if registry is not None else self._news_story_registry())
        )

    def _select_new_verified_news(
        self,
        items: List[Dict[str, Any]],
        limit: int = 7,
    ) -> List[Dict[str, Any]]:
        registry = self._news_story_registry()
        selected: List[Dict[str, Any]] = []
        selected_descriptors: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source = self._telegram_news_source_contract(item, require_tier_1=True)
            if source.get("valid") is not True:
                continue
            normalized = {
                **item,
                "source_url": source.get("source_url"),
                "published_at": source.get("published_at"),
            }
            descriptor = self._news_story_descriptor(normalized)
            if any(self._news_story_descriptors_match(descriptor, previous) for previous in [*registry, *selected_descriptors]):
                continue
            normalized["story_identity"] = descriptor["identity"]
            selected.append(normalized)
            selected_descriptors.append(descriptor)
            if len(selected) >= limit:
                break
        return selected

    def _record_news_story_deliveries(self, items: List[Dict[str, Any]], channel: str) -> None:
        if not items or not getattr(self, "portfolio_manager", None):
            return
        registry = self._news_story_registry()
        delivered_at = datetime.now(ZoneInfo("UTC")).isoformat()
        for item in items:
            descriptor = self._news_story_descriptor(item)
            if any(self._news_story_descriptors_match(descriptor, previous) for previous in registry):
                continue
            registry.append({**descriptor, "delivered_at": delivered_at, "channel": channel})
        self.portfolio_manager.set_app_setting(
            "telegram_news_story_registry_v1",
            json.dumps(registry[-300:], ensure_ascii=True, default=str),
        )

    def _macro_alert_state_key(self, identity: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9:_-]+", "-", identity)[:120]
        return f"macro_alert_state:{safe}"

    def _macro_alert_can_send(self, event: Dict[str, Any]) -> bool:
        identities = self._macro_alert_identities(event)
        if not identities:
            return False
        cooldown_hours = self._safe_int_env("MACRO_ALERT_COOLDOWN_HOURS", 3, minimum=1)
        current_score = float(event.get("impact_score") or 0)
        current_severity_rank = self._macro_alert_severity_rank(str(event.get("severity") or ""))
        blocked = False
        for identity in identities:
            raw = self.portfolio_manager.get_app_setting(self._macro_alert_state_key(identity), "{}")
            try:
                previous = json.loads(raw) if raw else {}
            except Exception:
                previous = {}
            previous_score = float(previous.get("impact_score") or 0)
            previous_severity_rank = self._macro_alert_severity_rank(str(previous.get("severity") or ""))
            if current_severity_rank > previous_severity_rank:
                continue
            if current_score >= previous_score + 8:
                continue
            sent_at = previous.get("sent_at")
            if not sent_at:
                continue
            try:
                sent_dt = datetime.fromisoformat(str(sent_at))
            except Exception:
                continue
            still_in_cooldown = datetime.now(sent_dt.tzinfo or ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))) < (
                sent_dt + timedelta(hours=cooldown_hours)
            )
            if still_in_cooldown:
                blocked = True
        return not blocked

    def _macro_alert_identities(self, event: Dict[str, Any]) -> List[str]:
        identities = [
            str(event.get("macro_bucket_identity") or "").strip(),
            str(event.get("macro_identity") or event.get("event_key") or "").strip(),
        ]
        deduped: List[str] = []
        for identity in identities:
            if identity and identity not in deduped:
                deduped.append(identity)
        return deduped

    def _macro_alert_severity_rank(self, severity: str) -> int:
        return {"low": 0, "medium": 1, "high": 2, "risk": 2, "critical": 3}.get((severity or "").lower(), 0)

    def _record_macro_alert_delivery(self, events: List[Dict[str, Any]]) -> None:
        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat()
        delivered_news: List[Dict[str, Any]] = []
        for event in events:
            if event.get("category") != "macro_alert":
                continue
            delivered_news.append(event)
            identities = self._macro_alert_identities(event)
            if not identities:
                continue
            payload = {
                "sent_at": now,
                "event_key": event.get("event_key"),
                "impact_score": event.get("impact_score"),
                "severity": event.get("severity"),
                "title": event.get("title"),
            }
            for identity in identities:
                self.portfolio_manager.set_app_setting(self._macro_alert_state_key(identity), json.dumps(payload))
        self._record_news_story_deliveries(delivered_news, "critical_macro_alert")

    def _paper_account_status_state_key(self) -> str:
        return "paper_account_status_alert_state"

    def _paper_trade_management_state_key(self, trade_id: Any) -> str:
        return f"paper_trade_management_alert_state:{trade_id}"

    def _paper_trade_management_can_send(self, trade: Dict[str, Any], management: Dict[str, Any]) -> bool:
        trade_id = trade.get("id")
        if trade_id in (None, ""):
            return True
        raw = self.portfolio_manager.get_app_setting(self._paper_trade_management_state_key(trade_id), "{}")
        try:
            previous = json.loads(raw) if raw else {}
        except Exception:
            previous = {}

        status = str(management.get("status") or "")
        grade = str(management.get("decision_grade") or "")
        if status != str(previous.get("status") or "") or grade != str(previous.get("decision_grade") or ""):
            return True

        try:
            current_pnl = float(trade.get("unrealized_pnl_pct") or 0)
            previous_pnl = float(previous.get("unrealized_pnl_pct") or 0)
            pnl_delta = abs(current_pnl - previous_pnl)
        except (TypeError, ValueError):
            pnl_delta = 0
        material_pnl_delta = self._safe_int_env("PAPER_TRADE_MANAGEMENT_PNL_DELTA_PCT", 3, minimum=1)
        if pnl_delta >= material_pnl_delta:
            return True

        sent_at = previous.get("sent_at")
        if not sent_at:
            return True
        try:
            sent_dt = datetime.fromisoformat(str(sent_at))
        except Exception:
            return True
        cooldown_hours = self._safe_int_env("PAPER_TRADE_MANAGEMENT_ALERT_COOLDOWN_HOURS", 4, minimum=1)
        now = datetime.now(sent_dt.tzinfo or ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        return now >= sent_dt + timedelta(hours=cooldown_hours)

    def _record_paper_trade_management_deliveries(self, events: List[Dict[str, Any]]) -> None:
        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat()
        for event in events:
            trade_id = event.get("trade_id")
            if trade_id in (None, ""):
                continue
            payload = {
                "sent_at": now,
                "status": event.get("management_status"),
                "decision_grade": event.get("decision_grade"),
                "unrealized_pnl_pct": event.get("unrealized_pnl_pct"),
            }
            self.portfolio_manager.set_app_setting(
                self._paper_trade_management_state_key(trade_id),
                json.dumps(payload, ensure_ascii=True, default=str),
            )

    def _paper_trade_status_rank(self, grade: str) -> int:
        return {
            "exit": 0,
            "review": 1,
            "protect": 2,
            "hold": 3,
            "wait": 4,
        }.get((grade or "").lower(), 5)

    def _paper_evidence_progress_signature(self, evidence_campaign: Dict[str, Any] | None) -> Dict[str, Any]:
        campaign = evidence_campaign if isinstance(evidence_campaign, dict) else {}
        if not campaign:
            return {}
        closed_step = self._safe_int_env("PAPER_EVIDENCE_STATUS_CLOSED_STEP", 5, minimum=1)
        outcome_step = self._safe_int_env("PAPER_EVIDENCE_STATUS_OUTCOME_STEP", 10, minimum=1)
        next_priority = campaign.get("next_priority") if isinstance(campaign.get("next_priority"), dict) else {}
        zero_rows = campaign.get("zero_evidence_strategies") if isinstance(campaign.get("zero_evidence_strategies"), list) else []
        zero_ids = sorted(
            str(item.get("id") or "")
            for item in zero_rows
            if isinstance(item, dict) and item.get("id")
        )
        closed_total = int(campaign.get("closed_trades_total") or 0)
        outcome_total = int(campaign.get("decisive_outcomes_total") or 0)
        return {
            "closed_milestone": closed_total // closed_step,
            "outcome_milestone": outcome_total // outcome_step,
            "strategies_ready": int(campaign.get("strategies_ready") or 0),
            "next_priority_id": str(next_priority.get("id") or ""),
            "zero_evidence_strategy_ids": zero_ids,
        }

    def _paper_evidence_progress_changed(self, evidence_campaign: Dict[str, Any] | None) -> bool:
        current = self._paper_evidence_progress_signature(evidence_campaign)
        if not current:
            return False
        raw = self.portfolio_manager.get_app_setting(self._paper_account_status_state_key(), "{}")
        try:
            previous = json.loads(raw) if raw else {}
        except Exception:
            previous = {}
        prior_signature = previous.get("evidence_progress_signature") if isinstance(previous, dict) else None
        return current != prior_signature

    @staticmethod
    def _paper_candidate_coverage_signature(
        strategy_candidate_coverage: List[Dict[str, Any]] | None,
    ) -> List[Dict[str, Any]]:
        rows = strategy_candidate_coverage if isinstance(strategy_candidate_coverage, list) else []
        signature = []
        for item in rows:
            if not isinstance(item, dict) or not item.get("strategy_id"):
                continue
            qualified = item.get("qualified_counts") if isinstance(item.get("qualified_counts"), dict) else {}
            signature.append(
                {
                    "strategy_id": str(item.get("strategy_id")),
                    "status": str(item.get("status") or "unknown"),
                    "has_candidate": int(item.get("candidate_count") or 0) > 0,
                    "has_qualified_candidate": any(int(value or 0) > 0 for value in qualified.values()),
                }
            )
        return sorted(signature, key=lambda item: item["strategy_id"])

    def _paper_candidate_coverage_changed(
        self,
        strategy_candidate_coverage: List[Dict[str, Any]] | None,
    ) -> bool:
        current = self._paper_candidate_coverage_signature(strategy_candidate_coverage)
        if not current:
            return False
        raw = self.portfolio_manager.get_app_setting(self._paper_account_status_state_key(), "{}")
        try:
            previous = json.loads(raw) if raw else {}
        except Exception:
            previous = {}
        return current != previous.get("candidate_coverage_signature")

    def _paper_account_status_can_send(
        self,
        demo_account: Dict[str, Any],
        evidence_campaign: Dict[str, Any] | None = None,
        strategy_candidate_coverage: List[Dict[str, Any]] | None = None,
    ) -> bool:
        status = str(demo_account.get("day_status") or "monitor")
        raw = self.portfolio_manager.get_app_setting(self._paper_account_status_state_key(), "{}")
        try:
            previous = json.loads(raw) if raw else {}
        except Exception:
            previous = {}
        current_evidence_signature = self._paper_evidence_progress_signature(evidence_campaign)
        if current_evidence_signature and current_evidence_signature != previous.get("evidence_progress_signature"):
            return True
        current_coverage_signature = self._paper_candidate_coverage_signature(strategy_candidate_coverage)
        if current_coverage_signature and current_coverage_signature != previous.get("candidate_coverage_signature"):
            return True
        if status != str(previous.get("day_status") or ""):
            return True

        current_counts = demo_account.get("management_counts") if isinstance(demo_account.get("management_counts"), dict) else {}
        previous_counts = previous.get("management_counts") if isinstance(previous.get("management_counts"), dict) else {}
        if current_counts != previous_counts:
            return True
        current_queue = demo_account.get("trade_action_queue") if isinstance(demo_account.get("trade_action_queue"), dict) else {}
        previous_queue = previous.get("trade_action_queue") if isinstance(previous.get("trade_action_queue"), dict) else {}
        current_top = current_queue.get("top_priority") if isinstance(current_queue.get("top_priority"), dict) else {}
        previous_top = previous_queue.get("top_priority") if isinstance(previous_queue.get("top_priority"), dict) else {}
        current_identity = (
            current_queue.get("status"),
            current_top.get("ticker"),
            current_top.get("direction"),
            current_top.get("decision_grade"),
            current_top.get("management_status"),
        )
        previous_identity = (
            previous_queue.get("status"),
            previous_top.get("ticker"),
            previous_top.get("direction"),
            previous_top.get("decision_grade"),
            previous_top.get("management_status"),
        )
        if current_identity != previous_identity:
            return True
        current_circuit = demo_account.get("risk_circuit") if isinstance(demo_account.get("risk_circuit"), dict) else {}
        previous_circuit = previous.get("risk_circuit") if isinstance(previous.get("risk_circuit"), dict) else {}
        if current_circuit.get("status") != previous_circuit.get("status"):
            return True
        if current_circuit.get("reasons") != previous_circuit.get("reasons"):
            return True

        sent_at = previous.get("sent_at")
        if not sent_at:
            return True
        try:
            sent_dt = datetime.fromisoformat(str(sent_at))
        except Exception:
            return True
        cooldown_hours = self._safe_int_env("PAPER_ACCOUNT_STATUS_ALERT_COOLDOWN_HOURS", 4, minimum=1)
        now = datetime.now(sent_dt.tzinfo or ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        return now >= sent_dt + timedelta(hours=cooldown_hours)

    def _record_paper_account_status_delivery(
        self,
        demo_account: Dict[str, Any],
        evidence_campaign: Dict[str, Any] | None = None,
        strategy_candidate_coverage: List[Dict[str, Any]] | None = None,
    ) -> None:
        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat()
        risk_circuit = demo_account.get("risk_circuit") if isinstance(demo_account.get("risk_circuit"), dict) else {}
        raw_previous = self.portfolio_manager.get_app_setting(self._paper_account_status_state_key(), "{}")
        try:
            previous = json.loads(raw_previous) if raw_previous else {}
        except Exception:
            previous = {}
        payload = {
            "sent_at": now,
            "day_status": demo_account.get("day_status"),
            "day_action": demo_account.get("day_action"),
            "management_counts": demo_account.get("management_counts") or {},
            "trade_action_queue": demo_account.get("trade_action_queue") or {},
            "risk_circuit": {
                "status": risk_circuit.get("status"),
                "reasons": risk_circuit.get("reasons") or [],
            },
            "equity": demo_account.get("equity"),
            "net_pnl_value": demo_account.get("net_pnl_value"),
        }
        evidence_signature = self._paper_evidence_progress_signature(evidence_campaign)
        if evidence_signature:
            payload["evidence_progress_signature"] = evidence_signature
        elif previous.get("evidence_progress_signature"):
            payload["evidence_progress_signature"] = previous.get("evidence_progress_signature")
        coverage_signature = self._paper_candidate_coverage_signature(strategy_candidate_coverage)
        if coverage_signature:
            payload["candidate_coverage_signature"] = coverage_signature
        elif previous.get("candidate_coverage_signature"):
            payload["candidate_coverage_signature"] = previous.get("candidate_coverage_signature")
        self.portfolio_manager.set_app_setting(self._paper_account_status_state_key(), json.dumps(payload))

    def _portfolio_tickers(self) -> set[str]:
        tickers: set[str] = set()
        try:
            for portfolio in self.portfolio_manager.get_portfolios():
                for holding in portfolio.get("holdings") or []:
                    ticker = str(holding.get("ticker") or "").upper().strip()
                    if ticker:
                        tickers.add(ticker)
        except Exception:
            return set()
        return tickers

    def _watchlist_tickers(self) -> set[str]:
        tickers: set[str] = set()
        try:
            for item in self.portfolio_manager.get_signal_watch_items():
                value = str(item.get("value") or "").upper().strip()
                kind = str(item.get("kind") or "").lower()
                if value and kind in {"ticker", "symbol", "watchlist"}:
                    tickers.add(value)
        except Exception:
            return set()
        return tickers

    def _event_related_tickers(self, item: Dict[str, Any]) -> set[str]:
        tickers: set[str] = set()
        for key in ("ticker", "symbol", "asset"):
            value = str(item.get(key) or "").upper().strip()
            if value and re.fullmatch(r"[A-Z0-9.\-]{1,12}", value):
                tickers.add(value)
        for key in ("tickers", "symbols", "matched_holdings"):
            values = item.get(key)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, dict):
                        raw = str(value.get("ticker") or value.get("symbol") or "").upper().strip()
                    else:
                        raw = str(value or "").upper().strip()
                    if raw and re.fullmatch(r"[A-Z0-9.\-]{1,12}", raw):
                        tickers.add(raw)
        return tickers

    def _event_direction_label(self, item: Dict[str, Any]) -> str:
        text = " ".join(
            str(item.get(key) or "")
            for key in ("direction", "direction_hint", "action", "summary", "title", "headline", "severity")
        ).lower()
        if any(token in text for token in ("negative", "risk-off", "miss", "cut", "downgrade", "avoid", "hedge", "bear")):
            return "↓"
        if any(token in text for token in ("positive", "risk-on", "beat", "raise", "upgrade", "buy", "bull")):
            return "↑"
        return "→"

    def _critical_event_priority(
        self,
        category: str,
        score: float | None,
        portfolio_hit: bool,
        watchlist_hit: bool,
        hard_impact: bool,
    ) -> int:
        if portfolio_hit:
            return 1
        if watchlist_hit:
            return 2
        if category == "critical_market" and hard_impact:
            return 12
        if score is not None and score >= 90:
            return 14
        return 30

    def _event_priority(self, event: Dict[str, Any]) -> tuple[int, str]:
        category = event.get("category")
        line = (event.get("line") or "").lower()
        if category == "future_star":
            return (0, line)
        if category == "ticker" and " buy " in f" {line} ":
            return (1, line)
        if category == "politician" and " buy " in f" {line} ":
            return (2, line)
        if category == "ticker":
            return (3, line)
        if category == "politician":
            return (4, line)
        return (5, line)

    def _send_notifications(
        self,
        config: "EmailAlertConfig",
        events: List[Dict[str, Any]],
        subject: str,
        telegram: bool = True,
    ) -> bool:
        errors: List[str] = []
        delivered = False

        if telegram:
            try:
                delivered = self._send_telegram(config, events, subject) or delivered
            except Exception as exc:
                errors.append(f"telegram failed: {exc}")

        if not delivered and errors:
            raise RuntimeError("; ".join(errors))
        return delivered

    def _send_email(
        self,
        config: EmailAlertConfig,
        events: List[Dict[str, Any]],
        subject: str,
    ) -> bool:
        if not (config.smtp_host and config.smtp_from and config.smtp_to):
            return False
        msg = EmailMessage()
        msg["From"] = config.smtp_from
        msg["To"] = config.smtp_to
        msg["Subject"] = subject

        lines = [subject, ""]
        for event in events:
            line = (event.get("line") or "").strip()
            if not line:
                lines.append("")
                continue
            if self._is_section_heading(line):
                lines.append(line)
                continue
            lines.append(f"- {line}")
            if event.get("conviction_score") is not None:
                lines.append(f"  A-Setup Score: {event['conviction_score']}")
            if event.get("source_label"):
                lines.append(f"  Quelle: {event['source_label']}")
            if event.get("source_url"):
                lines.append(f"  Link: {event['source_url']}")
        lines.extend(["", f"Erstellt am {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
        msg.set_content("\n".join(lines))
        msg.add_alternative(self._build_html_email(subject, events), subtype="html")

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
            if config.smtp_starttls:
                server.starttls()
            if config.smtp_user:
                server.login(config.smtp_user, config.smtp_password)
            server.send_message(msg)
        return True

    def _tg_post(self, token: str, chat_id: str, text: str, disable_preview: bool = True) -> None:
        """Send a single Telegram message (HTML parse mode)."""
        started = time.perf_counter()
        response = None
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": disable_preview,
                },
                timeout=20,
            )
            if response.status_code == 400:
                # Dynamic headlines can contain malformed or truncated HTML.
                # Retry once as plain text so a formatting issue never blocks a
                # valid Telegram alert.
                plain_text = unescape(re.sub(r"<[^>]*>", "", text))[:4096]
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": plain_text,
                        "disable_web_page_preview": disable_preview,
                    },
                    timeout=20,
                )
            response.raise_for_status()
            record_provider_result(
                "telegram",
                "telegram_bot_api",
                "send_message",
                "ok",
                latency_ms=(time.perf_counter() - started) * 1000,
                http_status=response.status_code,
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            record_provider_result(
                "telegram",
                "telegram_bot_api",
                "send_message",
                "error",
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=classify_provider_error(
                    "telegram", error=exc, http_status=status
                ),
                http_status=status,
                error_type=exc.__class__.__name__,
            )
            if status == 404:
                raise RuntimeError(
                    "Telegram rejected the bot token with 404. Check TELEGRAM_BOT_TOKEN in Railway; "
                    "use the raw token from BotFather, for example 123456:ABC..., not the API URL."
                ) from exc
            if status == 400:
                detail = ""
                try:
                    detail = str((exc.response.json() or {}).get("description") or "").strip()
                except (ValueError, AttributeError):
                    pass
                raise RuntimeError(
                    "Telegram rejected the message with 400 after HTML/plaintext retry. "
                    f"{detail or 'Check the message payload and Telegram chat configuration.'}"
                ) from exc
            if status == 403:
                raise RuntimeError(
                    "Telegram rejected the bot with 403. The bot is not allowed to send to this chat. "
                    "Open Telegram, start the bot with /start, and if this is a group/channel add the bot "
                    "as a member/admin; then verify TELEGRAM_CHAT_ID points to that chat."
                ) from exc
            raise
        except Exception as exc:
            record_provider_result(
                "telegram",
                "telegram_bot_api",
                "send_message",
                "error",
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code=classify_provider_error("telegram", error=exc),
                error_type=exc.__class__.__name__,
            )
            raise

    def _telegram_preflight(self, config: EmailAlertConfig) -> None:
        """Validate that Telegram can send to the configured chat before a scheduled brief."""
        self._validate_telegram_config(config)
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{config.telegram_bot_token}/sendChatAction",
                json={"chat_id": config.telegram_chat_id, "action": "typing"},
                timeout=10,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 403:
                raise RuntimeError(
                    "Telegram preflight failed with 403: bot is not allowed to send to this chat. "
                    "Open the bot and send /start, or add it to the group/channel with send rights."
                ) from exc
            if status == 400:
                raise RuntimeError(
                    "Telegram preflight failed with 400: TELEGRAM_CHAT_ID is wrong or the chat is unavailable."
                ) from exc
            if status == 404:
                raise RuntimeError(
                    "Telegram preflight failed with 404: TELEGRAM_BOT_TOKEN is invalid."
                ) from exc
            raise RuntimeError(f"Telegram preflight failed with HTTP {status}") from exc
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"Telegram preflight failed: {exc}") from exc

    def _tg_esc(self, text: str) -> str:
        """Escape text for Telegram HTML mode."""
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _tg_money(self, value: Any, currency: str = "EUR") -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if not math.isfinite(number):
            return "n/a"
        suffix = currency.upper()
        formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return self._tg_esc(f"{formatted} {suffix}")

    def _tg_signed_money(self, value: Any, currency: str = "EUR") -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if not math.isfinite(number):
            return "n/a"
        prefix = "+" if number > 0 else ""
        return self._tg_esc(f"{prefix}{self._tg_money(number, currency)}")

    def _tg_pct(self, value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if not math.isfinite(number):
            return "n/a"
        prefix = "+" if number > 0 else ""
        return self._tg_esc(f"{prefix}{number:.2f}%")

    def _tg_price(self, value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if not math.isfinite(number):
            return "n/a"
        return self._tg_esc(f"{number:.2f}")

    def _clean_text_value(self, value: Any) -> str:
        text = str(value or "").strip()
        if text.lower() in {"nan", "none", "null", "n/a", "na", "-", "--"}:
            return ""
        return text

    def _brief_line_identity(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
        stop_words = {"the", "a", "an", "to", "of", "and", "or", "for", "on", "in", "with", "as", "at", "is"}
        tokens = [token for token in normalized.split() if token not in stop_words]
        return " ".join(tokens[:12])

    def _tg_arrow(self, change: float | None) -> str:
        if change is None:
            return "⬜"
        return "🟢" if change > 0 else "🔴" if change < 0 else "🟡"

    def _send_telegram_rich_brief(
        self,
        config: "EmailAlertConfig",
        brief: Dict[str, Any],
        session_label: str,
    ) -> None:
        """
        Send brief as up to 4 focused Telegram messages (HTML).
        Structure varies by session:
          global / asia   → Full morning brief (markets + news + social + action)
          europe / usa    → Session open brief (session markets + key news + action)
          midday          → What changed + setups + portfolio brain
          close           → Session close + tomorrow risks + earnings preview
        """
        if not (config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id):
            return
        token = config.telegram_bot_token
        chat = config.telegram_chat_id
        tz = ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))
        now_str = datetime.now(tz).strftime("%a %d.%m.%Y · %H:%M")
        regime = brief.get("macro_regime", "mixed").upper()
        bias = brief.get("opening_bias", "")
        sl = session_label.lower()

        META = {
            "global":       ("🌅", "Morning Brief"),
            "europe":       ("🇪🇺", "Europe Open"),
            "europe_close": ("🇪🇺", "Europe Close"),
            "usa":          ("🇺🇸", "US Open"),
            "usa_close":    ("🇺🇸", "US Close"),
            "asia":         ("🌏", "Asia Close"),
            "midday":       ("☀️", "Midday Update"),
            "close":        ("🌇", "End of Day Recap"),
        }
        icon, session_name = META.get(sl, ("📊", session_label.title()))

        # Which region assets to highlight per session
        REGION_FOCUS: Dict[str, List[str]] = {
            "global":       ["usa", "europe", "asia"],
            "asia":         ["asia"],
            "europe":       ["europe", "usa"],
            "europe_close": ["europe", "usa"],
            "usa":          ["usa", "europe"],
            "usa_close":    ["usa"],
            "midday":       ["usa", "europe"],
            "close":        ["usa", "europe", "asia"],
        }
        focus_regions = REGION_FOCUS.get(sl, ["usa", "europe", "asia"])

        # ── MSG 1: Market Snapshot ──────────────────────────────────────────
        lines1: List[str] = [
            f"{icon} <b>{self._tg_esc(session_name)} — {now_str}</b>",
            f"Regime: <b>{self._tg_esc(regime)}</b> · <i>{self._tg_esc(bias)}</i>",
            "",
            "📊 <b>Märkte</b>",
        ]
        regions_data = brief.get("regions", {})
        region_labels = {"usa": "🇺🇸", "europe": "🇪🇺", "asia": "🌏"}
        for rkey in focus_regions:
            region = regions_data.get(rkey, {})
            flag = region_labels.get(rkey, "")
            tone = region.get("tone", "mixed")
            avg = region.get("avg_change_1d") or 0
            lines1.append(f"{flag} <b>{rkey.title()}</b> {tone} {avg:+.2f}%")
            for asset in region.get("assets", [])[:3]:
                chg = asset.get("change_1d")
                price = asset.get("price")
                arrow = self._tg_arrow(chg)
                chg_str = f"{chg:+.2f}%" if chg is not None else "—"
                price_str = f" <code>${price:,.2f}</code>" if price else ""
                lines1.append(f"  {arrow} {self._tg_esc(asset.get('label', ''))} {chg_str}{price_str}")

        macro_icons = {
            "CL=F": "🛢 Oil", "GC=F": "🥇 Gold", "BTC-USD": "₿ BTC",
            "^TNX": "📉 10Y Yield", "DX-Y.NYB": "💵 DXY",
        }
        macro_assets = brief.get("macro_assets", [])
        if macro_assets:
            lines1.append("")
            lines1.append("💹 <b>Makro</b>")
            for asset in macro_assets:
                chg = asset.get("change_1d")
                price = asset.get("price")
                arrow = self._tg_arrow(chg)
                chg_str = f"{chg:+.2f}%" if chg is not None else "—"
                label = macro_icons.get(asset.get("ticker", ""), self._tg_esc(asset.get("label", "")))
                price_str = f" <code>{price:,.2f}</code>" if price else ""
                lines1.append(f"{arrow} {label}{price_str} ({chg_str})")

        self._tg_post(token, chat, "\n".join(lines1))

        # ── MSG 2: News (Reuters/CNBC/Bloomberg + Google News) ─────────────
        lines2: List[str] = ["📰 <b>News</b>", ""]

        # One shared story registry covers every Telegram news format.
        all_news = self._select_new_verified_news(
            brief.get("top_news", []) + brief.get("google_news_extra", []),
            limit=7,
        )
        important_news = [item for item in all_news if item.get("is_important")][:2]
        important_ids = {self._brief_line_identity(item.get("title") or "") for item in important_news}
        for item in important_news:
            intelligence = item.get("news_intelligence") or {}
            title = self._tg_esc(item.get("title") or "")
            link = (item.get("source_url") or item.get("link") or "").strip()
            publisher = self._tg_esc(item.get("publisher") or "")
            ticker = (item.get("ticker") or "").strip()
            tag = f"<code>{self._tg_esc(ticker)}</code> " if ticker else ""
            score = int(item.get("importance_score") or 0)
            headline = f"🔴 <b>WICHTIG {score}/25</b> {tag}"
            headline += f"<a href=\"{link}\">{title}</a>" if link else title
            lines2.append(headline)
            source_meta = f"Quelle: {publisher or 'unbekannt'}"
            if item.get("source_domain"):
                source_meta += f" · {self._tg_esc(item.get('source_domain'))}"
            publication = self._paper_trade_time(item.get("published_at"))
            if publication:
                source_meta += f" · Veröffentlicht {self._tg_esc(publication)}"
            source_meta += f" · Vertrauen {self._tg_esc(intelligence.get('confidence') or 'offen')}"
            lines2.append(source_meta)
            evidence = item.get("source_evidence") or {}
            publisher_count = int(evidence.get("publisher_count") or 1)
            if publisher_count >= 2:
                lines2.append(
                    f"<b>Quellenabgleich:</b> {publisher_count} verschiedene Publisher berichten ähnlich "
                    "(Unabhängigkeit/Syndizierung technisch nicht verifiziert)."
                )
            else:
                lines2.append("<b>Quellenabgleich:</b> Einzelquelle – noch nicht mehrfach berichtet.")
            if evidence.get("source_agreement") == "mixed_headline_signal":
                lines2.append("<b>⚠ Widerspruch:</b> Ähnliche Headlines zeigen unterschiedliche Richtungssignale.")
            primary_sources = item.get("primary_sources") or []
            for primary in primary_sources[:1]:
                primary_url = str(primary.get("url") or "")
                authority = str(primary.get("authority") or "")
                if "Securities and Exchange Commission" in authority:
                    primary_label = (
                        f"SEC {self._tg_esc(primary.get('form') or '')} · "
                        f"eingereicht {self._tg_esc(primary.get('filed_at') or '')}"
                    )
                else:
                    primary_label = (
                        f"{self._tg_esc(authority or 'Offizielle Behörde')} · "
                        f"{self._tg_esc(primary.get('form') or 'Official Release')}"
                    )
                if primary_url:
                    lines2.append(
                        f"<b>✅ Primärquelle:</b> <a href=\"{primary_url}\">{primary_label}</a>"
                    )
                else:
                    lines2.append(f"<b>✅ Primärquelle:</b> {primary_label}")
                if "Securities and Exchange Commission" in authority:
                    lines2.append(
                        "<i>Filing-Link verifiziert; Publisher-Kennzahlen nicht automatisch einzeln abgeglichen.</i>"
                    )
                else:
                    lines2.append("<i>Offizielle Herkunft verifiziert; Trading-Einordnung bleibt Analyse.</i>")
            market_confirmation = item.get("market_confirmation") or {}
            confirmation_status = str(market_confirmation.get("status") or "")
            if confirmation_status:
                confirmation_labels = {
                    "confirmed": "BESTÄTIGT",
                    "contradicted": "WIDERSPRICHT",
                    "inconclusive": "NOCH UNEINDEUTIG",
                    "observed_only": "BEOBACHTET",
                    "unavailable": "NICHT VERFÜGBAR",
                }
                reaction_line = (
                    f"<b>Preisreaktion {confirmation_labels.get(confirmation_status, confirmation_status.upper())}:</b>"
                )
                asset_move = market_confirmation.get("asset_move_since_publication")
                benchmark_move = market_confirmation.get("benchmark_move_since_publication")
                relative_move = market_confirmation.get("relative_move_since_publication")
                if isinstance(asset_move, (int, float)):
                    reaction_line += (
                        f" {self._tg_esc(market_confirmation.get('ticker') or '')} {float(asset_move):+.2f}%"
                    )
                if isinstance(benchmark_move, (int, float)):
                    reaction_line += (
                        f" · {self._tg_esc(market_confirmation.get('benchmark') or '')} {float(benchmark_move):+.2f}%"
                    )
                if isinstance(relative_move, (int, float)):
                    reaction_line += f" · relativ {float(relative_move):+.2f}%"
                lines2.append(reaction_line)
                if confirmation_status != "unavailable":
                    lines2.append(
                        "<i>15m-Fenster ab Veröffentlichung; relative Stärke beweist keine Kausalität.</i>"
                    )
            decision = item.get("decision_readiness") if isinstance(item.get("decision_readiness"), dict) else {}
            if decision.get("status"):
                decision_label = {
                    "ready_for_paper_review": "PAPER-REVIEW BEREIT",
                    "monitor": "BEOBACHTEN",
                    "reject": "ABLEHNEN",
                }.get(str(decision.get("status")), str(decision.get("status") or "").upper())
                lines2.append(f"<b>Decision Gate:</b> {self._tg_esc(decision_label)}")
                lines2.append(
                    f"<b>Richtung:</b> {self._tg_esc(decision.get('direction') or 'watch')} · Echtgeld gesperrt"
                )
                hard_blockers = decision.get("hard_blockers") if isinstance(decision.get("hard_blockers"), list) else []
                verification_gaps = decision.get("verification_gaps") if isinstance(decision.get("verification_gaps"), list) else []
                if hard_blockers:
                    lines2.append(f"<b>Harte Blocker:</b> {self._tg_esc(' · '.join(hard_blockers[:4]))}")
                if verification_gaps:
                    lines2.append(f"<b>Noch zu verifizieren:</b> {self._tg_esc(' · '.join(verification_gaps[:4]))}")
                lines2.append(f"<b>Aktion:</b> {self._tg_esc(decision.get('action') or '')}")
            fact = self._tg_esc(str(intelligence.get("fact_summary") or "")[:320])
            meaning = self._tg_esc(str(intelligence.get("meaning") or "")[:260])
            if fact:
                basis = {
                    "official_release_summary": "offizielle Behörden-Zusammenfassung",
                    "official_release_headline": "offizielle Behörden-Überschrift",
                    "publisher_summary": "Publisher-Zusammenfassung",
                    "headline_only": "nur Überschrift",
                }.get(str(intelligence.get("fact_basis") or ""), "offen")
                lines2.append(f"<b>Fakt ({basis}):</b> {fact}")
            if meaning:
                lines2.append(f"<b>Bedeutung:</b> {meaning}")
            lines2.append(
                f"<b>Einschätzung:</b> {self._tg_esc(intelligence.get('assessment') or '')} "
                f"Bias {self._tg_esc(intelligence.get('directional_bias') or 'offen')} · "
                f"{self._tg_esc(intelligence.get('execution_horizon') or '')}"
            )
            confirmation = intelligence.get("confirmation") if isinstance(intelligence.get("confirmation"), list) else []
            if confirmation:
                lines2.append(f"<b>Bestätigung:</b> {self._tg_esc(' · '.join(confirmation[:2]))}")
            invalidation = self._tg_esc(str(intelligence.get("invalidation") or "")[:220])
            if invalidation:
                lines2.append(f"<b>Invalidierung:</b> {invalidation}")
            lines2.append("")

        remaining_news = [
            item
            for item in all_news
            if self._brief_line_identity(item.get("title") or "") not in important_ids
        ]
        if remaining_news:
            lines2.append("<b>Weitere bestätigte Meldungen</b>")
        for item in remaining_news[:5]:
            title = self._tg_esc(item.get("title") or "")
            link = (item.get("source_url") or item.get("link") or "").strip()
            publisher = self._tg_esc(item.get("publisher") or "")
            ticker = (item.get("ticker") or "").strip()
            tag = f"<code>{self._tg_esc(ticker)}</code> " if ticker else ""
            line = f"• {tag}<a href=\"{link}\">{title}</a>"
            if publisher:
                line += f" <i>({publisher})</i>"
            publication = self._paper_trade_time(item.get("published_at"))
            if publication:
                line += f" · {self._tg_esc(publication)}"
            lines2.append(line)

        if not all_news:
            lines2.append("<i>Keine neuen, verifizierten Tier-1-Meldungen seit dem letzten Versand.</i>")

        self._tg_post(token, chat, "\n".join(lines2))
        self._record_news_story_deliveries(all_news, f"rich_brief:{sl}")
        lines2 = ["📡 <b>Weitere Trading-Radare</b>"]

        product_catalysts = brief.get("product_catalysts") or []
        if product_catalysts:
            lines2.extend(["", "<b>Product Catalyst Radar</b>"])
            seen_catalysts: set[str] = set()
            for item in product_catalysts[:5]:
                ticker = self._tg_esc(item.get("ticker") or "")
                theme = self._tg_esc(str(item.get("theme") or "product"))
                catalyst_type = self._tg_esc(str(item.get("catalyst_type") or "news").replace("_", " "))
                title = self._tg_esc(item.get("title") or "")
                identity = self._brief_line_identity(f"{ticker} {theme} {title}")
                if identity in seen_catalysts:
                    continue
                seen_catalysts.add(identity)
                hint = str(item.get("direction_hint") or "watch")
                label = "NEGATIVE" if hint == "negative" else "POSITIVE WATCH" if hint == "positive_watch" else "WATCH"
                lines2.append(f"{label} <code>{ticker}</code> {theme} - {catalyst_type}")
                if title:
                    lines2.append(f"   {title[:180]}")

        future_stars = brief.get("future_stars") or []
        if future_stars:
            lines2.extend(["", "<b>Future Stars Radar</b>"])
            for item in future_stars[:5]:
                ticker = self._tg_esc(item.get("ticker") or "")
                score = item.get("score")
                score_str = f"{float(score):.0f}/100" if isinstance(score, (int, float)) else "score offen"
                quality_gate = self._tg_esc(str(item.get("quality_gate") or "watch").upper())
                revenue = item.get("revenue_growth") or item.get("growth")
                revenue_str = (
                    f"{float(revenue):+.1f}% Umsatz"
                    if isinstance(revenue, (int, float))
                    else "Umsatz n/a"
                )
                catalyst = self._tg_esc(str(item.get("catalyst") or item.get("reason") or "")[:180])
                risk_flags = item.get("risk_flags") if isinstance(item.get("risk_flags"), list) else []
                risk_value = item.get("risk") or (risk_flags[0] if risk_flags else "")
                risk = self._tg_esc(str(risk_value)[:160])
                lines2.append(f"{quality_gate} <code>{ticker}</code> {score_str} | {revenue_str}")
                if catalyst:
                    lines2.append(f"   Katalysator: {catalyst}")
                if risk:
                    lines2.append(f"   Risiko: {risk}")

        market_movers = brief.get("market_movers") or {}
        market_movers_meta = brief.get("market_movers_meta") or {}
        gainers = market_movers.get("gainers") or []
        losers = market_movers.get("losers") or []
        if gainers or losers:
            universe_size = market_movers_meta.get("universe_size")
            scope_suffix = f" · {int(universe_size)} Werte + Watchlist" if isinstance(universe_size, int) else ""
            lines2.extend(["", f"<b>Biggest Winners / Losers</b>{scope_suffix}"])
            as_of = self._paper_trade_time(market_movers_meta.get("as_of"))
            if as_of:
                lines2.append(f"<i>1-Tages-Bewegung · Scan {self._tg_esc(as_of)}</i>")
            for label, rows in (("WIN", gainers[:4]), ("LOSE", losers[:4])):
                for item in rows:
                    ticker = self._tg_esc(item.get("ticker") or "")
                    raw_name = str(item.get("name") or "").strip()
                    name = self._tg_esc(raw_name[:28]) if raw_name and raw_name.upper() != str(item.get("ticker") or "").upper() else ""
                    chg = item.get("change_1d")
                    if not isinstance(chg, (int, float)):
                        continue
                    chg_str = f"{chg:+.2f}%"
                    price = item.get("price")
                    price_str = f" ${price:,.2f}" if isinstance(price, (int, float)) else ""
                    name_part = f" {name}" if name else ""
                    lines2.append(f"{label} <code>{ticker}</code>{name_part} {chg_str}{price_str}")
        elif market_movers_meta.get("status") == "unavailable":
            lines2.extend([
                "",
                "<b>Biggest Winners / Losers</b>",
                "<i>Aktuelle 1-Tages-Mover konnten nicht verlässlich geladen werden; keine Ersatzwerte ausgegeben.</i>",
            ])

        # Watchlist impact
        watchlist_impact = brief.get("watchlist_impact", [])
        if watchlist_impact:
            lines2.extend(["", "🎯 <b>Deine Watchlist</b>"])
            for item in watchlist_impact[:5]:
                summary = self._tg_esc(item.get("summary") or "")
                ticker = self._tg_esc(item.get("ticker") or "")
                tag = f"<code>{ticker}</code> " if ticker else ""
                lines2.append(f"• {tag}{summary}")

        # Earnings calendar (broad S&P500 + watchlist)
        raw_earnings = brief.get("broad_earnings") or brief.get("earnings_calendar", [])
        earnings = [
            item for item in raw_earnings
            if not isinstance(item.get("days_until"), int) or item.get("days_until") >= 0
        ]
        if earnings:
            lines2.extend(["", "📅 <b>Earnings nächste 14 Tage</b>"])
            for item in earnings[:6]:
                t = self._tg_esc(item.get("ticker") or "")
                company = self._tg_esc((item.get("company") or t)[:28])
                session = item.get("session") or ""
                session_emoji = "🌅" if "pre" in session else "🌇" if "after" in session else "⏰"
                date_str = (item.get("date") or item.get("scheduled_for") or "")[:10]
                days = item.get("days_until")
                days_str = f" <i>(in {days}d)</i>" if isinstance(days, int) else ""
                cap = item.get("market_cap")
                cap_str = f" ${cap/1e9:.0f}B" if cap and cap > 1e9 else ""
                lines2.append(f"• <code>{t}</code> {company}{cap_str} — {date_str} {session_emoji}{days_str}")

        earnings_results = brief.get("earnings_results") or []
        if earnings_results:
            lines2.extend(["", "<b>Earnings vs Erwartung</b>"])
            for item in earnings_results[:5]:
                ticker = self._tg_esc(item.get("ticker") or "")
                status = str(item.get("status") or "inline").lower()
                icon = "BEAT" if status == "beat" else "MISS" if status == "miss" else "INLINE"
                action_hint = str(item.get("action_hint") or "").strip().lower()
                trade_label = {
                    "constructive_if_follow_through": "Trade: nur Long bei Follow-through",
                    "constructive_watch": "Trade: konstruktiv, Reaktion bestaetigen",
                    "watch_pullback_or_follow_through": "Trade: kein Chase, nur Pullback oder Follow-through",
                    "avoid_until_repair": "Trade: vermeiden bis Reparatur",
                    "caution_until_repair": "Trade: vorsichtig, erst Stabilisierung",
                    "needs_guidance_confirmation": "Trade: erst Guidance/Preis bestaetigen",
                }.get(action_hint, "")
                surprise = item.get("eps_surprise_pct")
                surprise_str = f"{surprise:+.1f}%" if isinstance(surprise, (int, float)) else "offen"
                reported = item.get("reported_eps")
                estimate = item.get("eps_estimate")
                reported_str = f"{reported:.2f}" if isinstance(reported, (int, float)) else "offen"
                estimate_str = f"{estimate:.2f}" if isinstance(estimate, (int, float)) else "offen"
                period = self._tg_esc(str(item.get("period") or "")[:10])
                days_since = item.get("days_since")
                freshness = f" · vor {days_since}d" if isinstance(days_since, int) else ""
                summary = self._tg_esc(item.get("summary") or item.get("action_hint") or "")
                revenue_yoy = item.get("revenue_yoy")
                revenue_str = (
                    f"{float(revenue_yoy):+.1f}% YoY"
                    if isinstance(revenue_yoy, (int, float))
                    else ""
                )
                guidance_label = self._tg_esc(str(item.get("guidance_label") or "").strip())
                lines2.append(
                    f"{icon} <code>{ticker}</code> {status.upper()} {surprise_str} "
                    f"- EPS {reported_str} / Est {estimate_str} {period}{freshness}"
                )
                details = " | ".join(part for part in [revenue_str, guidance_label, trade_label] if part)
                if details:
                    lines2.append(f"   {details}")
                if summary:
                    lines2.append(f"   {summary}")

        # Economic macro windows
        econ = [e for e in brief.get("economic_calendar", []) if e.get("category") != "session"]
        if econ:
            lines2.extend(["", "🗓 <b>Makro-Fenster heute</b>"])
            for item in econ[:4]:
                title = self._tg_esc(item.get("title") or "")
                time_str = (item.get("scheduled_for") or "")[11:16]
                region = self._tg_esc((item.get("region") or "").upper())
                lines2.append(f"• {time_str} <b>{region}</b> — {title}")

        self._tg_post(token, chat, "\n".join(lines2))

        # ── MSG 3: Social Intelligence (Reddit + Stocktwits + Polymarket) ──
        lines3: List[str] = []

        reddit = brief.get("reddit_posts", [])
        filtered_reddit = []
        for post in reddit:
            title_l = str(post.get("title") or "").lower()
            score = int(post.get("score") or 0)
            comments = int(post.get("num_comments") or 0)
            is_ceo_rumor = "ceo" in title_l and any(
                term in title_l
                for term in ["stepping down", "steps down", "replacing", "successor", "names new ceo", "named ceo"]
            )
            if is_ceo_rumor:
                continue
            if score < 250 and comments < 80:
                continue
            filtered_reddit.append(post)

        if filtered_reddit:
            lines3.append("🤖 <b>Reddit Hot Posts</b>")
            for post in filtered_reddit[:4]:
                title = self._tg_esc((post.get("title") or "")[:120])
                sub = self._tg_esc(post.get("subreddit") or "")
                score = post.get("score") or 0
                comments = post.get("num_comments") or 0
                sentiment = post.get("sentiment") or "neutral"
                sent_icon = "📈" if sentiment == "bullish" else "📉" if sentiment == "bearish" else "➡️"
                url = post.get("url") or ""
                tickers = post.get("ticker_matches", [])
                ticker_str = " ".join(f"<code>{t}</code>" for t in tickers[:3])
                line = f"{sent_icon} <a href=\"{url}\">{title}</a>"
                if ticker_str:
                    line += f" {ticker_str}"
                line += f" <i>({sub} · ⬆️{score} 💬{comments})</i>"
                lines3.append(line)

        stocktwits = brief.get("stocktwits", [])
        if stocktwits:
            if lines3:
                lines3.append("")
            lines3.append("💬 <b>Stocktwits Sentiment</b>")
            for item in stocktwits[:4]:
                t = self._tg_esc(item.get("ticker") or "")
                bull = item.get("bull_ratio") or 0
                label = item.get("sentiment_label") or "neutral"
                icon_s = "🐂" if label == "bullish" else "🐻" if label == "bearish" else "➡️"
                msgs = item.get("message_count") or 0
                bar_filled = round(bull / 10)
                bar = "█" * bar_filled + "░" * (10 - bar_filled)
                lines3.append(f"{icon_s} <code>{t}</code> {bar} {bull}% bullish · {msgs} msgs")

        polymarket = brief.get("polymarket", [])
        if polymarket:
            if lines3:
                lines3.append("")
            lines3.append("🎲 <b>Polymarket — Markt-Wahrscheinlichkeiten</b>")
            for item in polymarket[:6]:
                q = self._tg_esc((item.get("question") or "")[:100])
                prob = item.get("probability_yes")
                vol = item.get("volume_usd") or 0
                url = item.get("url") or ""
                end = (item.get("end_date") or "")
                prob_str = f"<b>{prob:.0f}%</b>" if prob is not None else "?"
                vol_str = f"${vol/1000:.0f}K" if vol >= 1000 else f"${vol:.0f}"
                line = f"• <a href=\"{url}\">{q}</a>"
                line += f" → {prob_str} Ja · Vol {vol_str}"
                if end:
                    line += f" (bis {end})"
                lines3.append(line)

        if lines3:
            self._tg_post(token, chat, "\n".join(lines3))

        # ── MSG 4: Action Board + Portfolio Brain + Contrarian ──────────────
        lines4: List[str] = []
        setup_board = brief.get("setup_board") or {}
        setup_now = setup_board.get("now") or []
        setup_next = setup_board.get("next") or []
        setup_avoid = setup_board.get("avoid") or []
        if setup_now or setup_next or setup_avoid:
            lines4.append("🚦 <b>Top Now / Next / Avoid</b>")
            for label, rows in (("NOW", setup_now[:3]), ("NEXT", setup_next[:3]), ("AVOID", setup_avoid[:3])):
                if not rows:
                    continue
                rendered = []
                for row in rows:
                    symbol = self._tg_esc(row.get("symbol") or "")
                    thesis = self._tg_esc((row.get("thesis") or "")[:80])
                    rendered.append(f"<code>{symbol}</code> {thesis}")
                if rendered:
                    lines4.append(f"• <b>{label}</b> — {' | '.join(rendered)}")
            lines4.append("")
        trade_setups = brief.get("trade_setups") or []
        if trade_setups:
            seen_setups: set[str] = set()
            lines4.append("🎯 <b>Highest Conviction Setups</b>")
            for setup_item in trade_setups[:5]:
                symbol = self._tg_esc(setup_item.get("symbol") or "")
                confidence = setup_item.get("confidence")
                thesis = self._tg_esc((setup_item.get("thesis") or "")[:120])
                trigger = self._tg_esc((setup_item.get("trigger") or "")[:120])
                invalidation = self._tg_esc((setup_item.get("invalidation") or "")[:100])
                move = self._tg_esc(setup_item.get("expected_move") or "")
                quality = self._tg_esc(str(setup_item.get("decision_quality") or "").strip())
                sizing = self._tg_esc(str(setup_item.get("size_guidance") or "").strip())
                window = self._tg_esc(str(setup_item.get("window") or "").strip())
                rank = setup_item.get("rank")
                identity = self._brief_line_identity(f"{symbol} {thesis} {trigger}")
                if not symbol or identity in seen_setups:
                    continue
                seen_setups.add(identity)
                rank_text = f"#{rank} " if isinstance(rank, int) else ""
                confidence_text = f" · {confidence}% conf" if isinstance(confidence, int) else ""
                move_text = f" · move {move}" if move else ""
                lines4.append(f"• {rank_text}<code>{symbol}</code>{confidence_text}{move_text} — {thesis}")
                meta_parts = [part for part in [quality, sizing, window] if part]
                if meta_parts:
                    lines4.append(f"   {' | '.join(meta_parts)}")
                if trigger:
                    lines4.append(f"   Trigger: {trigger}")
                if invalidation:
                    lines4.append(f"   Invalid: {invalidation}")
            learning_rows = []
            for setup_item in trade_setups[:5]:
                adjustment = setup_item.get("learning_adjustment") or {}
                try:
                    delta = float(adjustment.get("score_delta") or 0)
                except Exception:
                    delta = 0.0
                if not delta:
                    continue
                symbol = self._tg_esc(setup_item.get("symbol") or "")
                reason = self._tg_esc(str(adjustment.get("reason") or "")[:130])
                source_hit = adjustment.get("source_hit_rate")
                setup_hit = adjustment.get("setup_hit_rate")
                hit_bits = []
                if source_hit is not None:
                    hit_bits.append(f"source {source_hit}%")
                if setup_hit is not None:
                    hit_bits.append(f"setup {setup_hit}%")
                hit_text = f" ({', '.join(hit_bits)})" if hit_bits else ""
                sign = "+" if delta > 0 else ""
                learning_rows.append(
                    f"• <code>{symbol}</code> learning {sign}{delta:.1f}{self._tg_esc(hit_text)} — {reason}"
                )
            if learning_rows:
                lines4.append("")
                lines4.append("🧠 <b>Learning applied</b>")
                lines4.extend(learning_rows[:4])
            learning_adjustments = brief.get("learning_adjustments") or []
            if learning_adjustments and not learning_rows:
                lines4.append("")
                lines4.append("🧠 <b>Learning applied</b>")
                for item in learning_adjustments[:4]:
                    label = self._tg_esc(item.get("label") or "")
                    axis = self._tg_esc(item.get("axis") or "signal")
                    delta = item.get("score_delta")
                    hit_rate = item.get("hit_rate")
                    lines4.append(f"• {axis} <b>{label}</b>: {hit_rate}% hit-rate, rank {delta:+}")

        action_board = brief.get("action_board", [])
        action_rows = []
        seen_action_lines: set[str] = set()
        for item in action_board:
            setup = str(item.get("setup") or "watch").lower()
            ticker = self._tg_esc(item.get("ticker") or "Macro")
            trigger = self._tg_esc(item.get("trigger") or "")
            impact = str(item.get("impact") or "")
            if setup == "watch" and ticker == "Macro" and impact != "high":
                continue
            line_key = f"{ticker}:{setup}:{trigger}"
            if line_key in seen_action_lines:
                continue
            seen_action_lines.add(line_key)
            tag = f"<code>{ticker}</code> " if ticker != "Macro" else ""
            action_rows.append(f"• {tag}<b>{self._tg_esc(setup)}</b> — {trigger}")
        if action_rows:
            if lines4:
                lines4.append("")
            lines4.append("⚡ <b>Action Board</b>")
            lines4.extend(action_rows[:5])

        portfolio_brain = brief.get("portfolio_brain", {})
        pb_actions = portfolio_brain.get("actions") or []
        at_risk = [a for a in pb_actions if a.get("bucket") == "at_risk"][:3]
        beneficiaries = [a for a in pb_actions if a.get("bucket") == "beneficiaries"][:3]
        hedge_ideas = [a for a in pb_actions if a.get("bucket") == "hedges"][:3]
        pb_summary = portfolio_brain.get("summary") or {}
        if at_risk or beneficiaries or hedge_ideas:
            if lines4:
                lines4.append("")
            lines4.append(
                f"🧠 <b>Portfolio Brain</b>"
                f" — ⚠️{pb_summary.get('at_risk', 0)}"
                f" ✅{pb_summary.get('beneficiaries', 0)}"
                f" 🛡{pb_summary.get('hedges', 0)}"
            )
            for card in at_risk:
                h = self._tg_esc(card.get("ticker") or "")
                r = self._tg_esc(card.get("reason") or card.get("trigger") or "")
                act = self._tg_esc(card.get("portfolio_action") or "watch")
                lines4.append(f"⚠️ <code>{h}</code> <b>{act}</b> — {r}")
            for card in beneficiaries:
                h = self._tg_esc(card.get("ticker") or "")
                r = self._tg_esc(card.get("reason") or card.get("trigger") or "")
                act = self._tg_esc(card.get("portfolio_action") or "add")
                lines4.append(f"✅ <code>{h}</code> <b>{act}</b> — {r}")
            for card in hedge_ideas:
                h = self._tg_esc(card.get("ticker") or "")
                r = self._tg_esc(card.get("reason") or card.get("trigger") or "")
                hedges = card.get("hedge_candidates") or []
                hedge_str = ", ".join(self._tg_esc(hc.get("ticker", "")) for hc in hedges[:2])
                lines4.append(f"🛡 <code>{h}</code> hedge — {r}")
                if hedge_str:
                    lines4.append(f"   via {hedge_str}")

        contrarian = brief.get("contrarian_signals", [])
        if contrarian:
            if lines4:
                lines4.append("")
            lines4.append("🔀 <b>Contrarian Signals</b>")
            for item in contrarian[:3]:
                t = self._tg_esc(item.get("ticker") or "")
                pub = self._tg_esc(item.get("publisher") or "Media")
                media_bias = self._tg_esc(item.get("media_bias") or "")
                contra = self._tg_esc(item.get("contrarian_bias") or "")
                score = item.get("score") or 0
                rsi = item.get("rsi_14") or 0
                link = item.get("link") or ""
                title_str = self._tg_esc((item.get("title") or "")[:80])
                title_part = f'<a href="{link}">{title_str}</a>' if link else title_str
                lines4.append(
                    f"• <code>{t}</code> {pub}: {media_bias} → contra <b>{contra}</b>"
                    f" | RSI {rsi} · Score {score}"
                )
                if title_str:
                    lines4.append(f"   <i>{title_part}</i>")

        # Session-close / EOD additions
        if sl in {"close", "europe_close", "usa_close"}:
            timeline = brief.get("opening_timeline", [])
            if timeline:
                if lines4:
                    lines4.append("")
                lines4.append("📈 <b>Session-Abschluss</b>")
                for sess in timeline:
                    label_s = self._tg_esc(sess.get("label") or "")
                    tone_s = self._tg_esc(sess.get("tone") or "")
                    move_s = float(sess.get("move") or 0)
                    driver_s = self._tg_esc((sess.get("driver") or "")[:80])
                    arrow = self._tg_arrow(move_s)
                    lines4.append(f"{arrow} <b>{label_s}</b> {tone_s} {move_s:+.2f}% — {driver_s}")

        if lines4:
            self._tg_post(token, chat, "\n".join(lines4))

        # ── MSG 5: Trading Edge (squeeze, insider, options, analysts, regime) ─
        edge = brief.get("trading_edge") or {}
        lines5: List[str] = []
        if edge:
            regime = edge.get("regime") or {}
            if regime:
                vix = regime.get("vix") or {}
                fng = regime.get("crypto_fng") or {}
                parts = []
                if vix:
                    parts.append(f"VIX <b>{vix.get('value')}</b> ({self._tg_esc(vix.get('regime',''))}, {vix.get('change','+0'):+.2f})")
                if fng:
                    parts.append(f"Crypto F&amp;G <b>{fng.get('value')}</b> ({self._tg_esc(fng.get('label',''))})")
                if parts:
                    lines5.append("🌡 <b>Market Regime</b> — " + " · ".join(parts))

            yc = edge.get("yield_curve") or {}
            if yc:
                inv = "⚠️ <b>INVERTED</b>" if yc.get("inverted") else "normal"
                lines5.append(
                    f"📉 <b>Yield Curve</b> — 10Y {yc.get('us10y','?')}% · 5Y {yc.get('us5y','?')}% · 30Y {yc.get('us30y','?')}% · 10-5 spread {yc.get('spread_10y_5y','?'):+.2f}pp ({inv})"
                )

            sectors = edge.get("sectors") or []
            if sectors:
                lines5.append("")
                lines5.append("🔄 <b>Sector Rotation (5d)</b>")
                top3 = sectors[:3]
                bot3 = sectors[-3:]
                for s in top3:
                    lines5.append(f"🟢 <code>{s['ticker']}</code> {self._tg_esc(s['name'])} {s['change_5d']:+.2f}% (1d {s['change_1d']:+.2f}%)")
                for s in bot3:
                    lines5.append(f"🔴 <code>{s['ticker']}</code> {self._tg_esc(s['name'])} {s['change_5d']:+.2f}% (1d {s['change_1d']:+.2f}%)")

            pre = edge.get("premarket") or []
            if pre:
                lines5.append("")
                lines5.append("⏰ <b>Pre-Market Movers</b>")
                for m in pre[:5]:
                    arrow = self._tg_arrow(m["change_pct"])
                    lines5.append(f"{arrow} <code>{m['ticker']}</code> {m['change_pct']:+.2f}% @ ${m['pre']}")

            squeeze = edge.get("squeeze") or []
            if squeeze:
                lines5.append("")
                lines5.append("🎯 <b>Short-Squeeze Watch</b>")
                for s in squeeze[:5]:
                    lines5.append(
                        f"• <code>{s['ticker']}</code> score <b>{s['score']}</b> · short {s['short_pct_float']}% · DTC {s['days_to_cover']} · RSI {s['rsi']}"
                    )

            options = edge.get("options") or []
            if options:
                lines5.append("")
                lines5.append("🎲 <b>Unusual Options</b>")
                for o in options[:5]:
                    tag = "🐂 bullish" if o["sentiment"] == "bullish" else "🐻 bearish" if o["sentiment"] == "bearish" else "neutral"
                    lines5.append(
                        f"• <code>{o['ticker']}</code> {tag} · P/C {o['pc_ratio']} · calls {o['calls_vol']:,} / puts {o['puts_vol']:,} ({self._tg_esc(o['expiry'])})"
                    )

            analyst = edge.get("analyst") or []
            analyst_lines: List[str] = []
            for a in analyst[:5]:
                tk = self._tg_esc(a.get("ticker", ""))
                latest = a.get("actions", [])[-3:]
                for act in latest:
                    firm_raw = self._clean_text_value(act.get("firm"))[:28]
                    to_raw = self._clean_text_value(act.get("to"))
                    frm_raw = self._clean_text_value(act.get("from"))
                    action_raw = self._clean_text_value(act.get("action"))
                    firm = self._tg_esc(firm_raw)
                    to = self._tg_esc(to_raw)
                    frm = self._tg_esc(frm_raw)
                    action = self._tg_esc(action_raw)
                    if not (firm or to or frm or action):
                        continue
                    if not (to or action):
                        continue
                    transition = f"{frm or 'offen'} → <b>{to}</b>" if to else action
                    suffix = f" ({action})" if action and action not in transition else ""
                    analyst_lines.append(f"• <code>{tk}</code> {firm or 'Analyst'}: {transition}{suffix}")
            if analyst_lines:
                lines5.append("")
                lines5.append("🏦 <b>Analyst Actions (14d)</b>")
                lines5.extend(analyst_lines[:8])

            insider = edge.get("insider") or []
            if insider:
                lines5.append("")
                lines5.append("👔 <b>Insider Cluster Buys (7d)</b>")
                for i in insider[:6]:
                    lines5.append(
                        f"• <code>{self._tg_esc(i.get('ticker',''))}</code> {self._tg_esc(i.get('title',''))[:20]} · {self._tg_esc(i.get('value',''))} ({self._tg_esc(i.get('date',''))})"
                    )

        if lines5:
            self._tg_post(token, chat, "\n".join(lines5))

    def _send_telegram(
        self,
        config: "EmailAlertConfig",
        events: List[Dict[str, Any]],
        subject: str,
    ) -> bool:
        """Legacy plain-text Telegram sender (used for signal alerts, not for briefs)."""
        if not (
            config.telegram_enabled
            and config.telegram_bot_token
            and config.telegram_chat_id
        ):
            return False

        lines = [f"<b>{self._tg_esc(subject)}</b>", ""]
        current_section = ""
        for event in events[:30]:
            line = (event.get("line") or "").strip()
            if not line:
                continue
            if self._is_section_heading(line):
                current_section = line.rstrip(":")
                lines.extend([f"<b>{self._tg_esc(current_section)}</b>", ""])
                continue
            if event.get("category") == "macro_alert":
                lines.append(self._render_telegram_macro_alert(event))
                lines.append("")
                continue
            if event.get("category") == "paper_learning":
                lines.append(self._render_telegram_paper_learning_alert(event))
                lines.append("")
                continue
            if event.get("category") == "paper_trade_opened":
                lines.append(self._render_telegram_paper_trade_opened_alert(event))
                lines.append("")
                continue
            if event.get("category") == "paper_trade_management":
                lines.append(self._render_telegram_paper_trade_management_alert(event))
                lines.append("")
                continue
            if event.get("category") == "paper_account_status":
                lines.append(self._render_telegram_paper_account_status_alert(event))
                lines.append("")
                continue
            if event.get("category") == "paper_trade_closed":
                lines.append(self._render_telegram_paper_trade_closed_alert(event))
                lines.append("")
                continue

            prefix = self._telegram_prefix_for_event(event)
            rendered_line = f"{prefix} {self._tg_esc(line)}".strip()
            if event.get("conviction_score") is not None:
                rendered_line += f" | score {self._tg_esc(str(event['conviction_score']))}"
            if event.get("source_label"):
                rendered_line += f" | {self._tg_esc(str(event['source_label']))}"
            # Add clickable link if available
            source_url = (event.get("source_url") or "").strip()
            if source_url:
                rendered_line += f' <a href="{source_url}">→</a>'
            lines.append(rendered_line)

        self._tg_post(config.telegram_bot_token, config.telegram_chat_id, "\n".join(lines))
        return True

    def _paper_label(self, value: Any, fallback: str = "n/a") -> str:
        key = str(value or "").strip().lower()
        labels = {
            "action_required": "Aktion nötig",
            "ahead": "im Plus",
            "behind": "im Minus",
            "close_review": "Schließung prüfen",
            "collect_first_trade": "erste Paper-Trades sammeln",
            "continue_learning": "weiter lernen",
            "exit": "Exit",
            "flat": "neutral",
            "hold": "halten",
            "hold_with_plan": "mit Plan halten",
            "holding_period_expired": "maximale Haltedauer erreicht",
            "news_reaction_failed": "News-Reaktion gebrochen",
            "news_momentum_stalled": "News-Momentum stockt",
            "news_source_invalidated": "News-Quelle invalidiert",
            "correction_detected": "Korrektur erkannt",
            "retracted_or_withdrawn": "widerrufen/zurückgezogen",
            "source_unavailable": "Quelle nicht mehr erreichbar",
            "learning": "lernen",
            "loser": "Verlierer",
            "manual_review": "manuelle Prüfung",
            "manual_review_ready": "manuelle Prüfung bereit",
            "monitor": "überwachen",
            "monitor_open_trade": "offenen Trade beobachten",
            "near_stop": "nahe am Stop",
            "near_target": "nahe am Ziel",
            "not_started": "noch nicht gestartet",
            "pending_data": "wartet auf Daten",
            "paper_exit": "Paper-Exit",
            "price_and_close_review": "Preis erfassen und schließen",
            "pause_and_review": "pausieren und prüfen",
            "protect": "schützen",
            "protect_profit": "Gewinn schützen",
            "protect_profit_review": "Gewinnschutz prüfen",
            "reduce_or_close_review": "Reduzieren/Schließen prüfen",
            "review": "prüfen",
            "risk_review": "Risiko prüfen",
            "stop_hit": "Stop getroffen",
            "take_profit_review": "Gewinnmitnahme prüfen",
            "target_hit": "Ziel getroffen",
            "target_or_profit_taken": "Ziel/Gewinnmitnahme",
            "thesis_check": "These prüfen",
            "wait": "warten",
            "weak_follow_through": "schwache Anschlussbewegung",
            "winner": "Gewinner",
            "working": "funktioniert",
        }
        return labels.get(key, key.replace("_", " ") if key else fallback)

    def _render_telegram_paper_trade_opened_alert(self, event: Dict[str, Any]) -> str:
        ticket = event.get("trade_ticket") if isinstance(event.get("trade_ticket"), dict) else {}
        ticker = self._tg_esc(str(event.get("ticker") or "n/a"))
        direction = self._tg_esc(str(event.get("direction") or "n/a").upper())
        asset_class = self._tg_esc(str(event.get("asset_class") or "asset"))
        setup = self._tg_esc(str(event.get("setup_type") or "setup"))
        entry = self._tg_price(event.get("entry_price"))
        stop = self._tg_price(event.get("stop_price"))
        target = self._tg_price(event.get("target_price"))
        qty = self._tg_esc(str(event.get("quantity") if event.get("quantity") is not None else "n/a"))
        leverage = float(event.get("leverage") or ticket.get("leverage") or 1)
        invested = self._tg_money(event.get("invested_value"))
        current_value = self._tg_money(event.get("current_value"))
        result_delta = self._tg_signed_money(event.get("result_value_delta"))
        result_label = self._tg_esc(self._paper_label(event.get("result_label"), "neutral"))
        max_loss = self._tg_money(event.get("suggested_max_loss_value"))
        confidence = self._tg_esc(
            str(event.get("confidence_score") if event.get("confidence_score") is not None else "n/a")
        )
        trigger = self._tg_esc(str(event.get("trigger") or "Anschlussbewegung muss bestätigt bleiben."))[:520]
        invalidation = self._tg_esc(str(event.get("invalidation") or "Schließen/prüfen, wenn die These scheitert."))[:520]
        action = self._tg_esc(self._paper_label(event.get("management_action"), "halten und prüfen"))[:260]
        next_check = self._tg_esc(
            str(event.get("management_next_check") or "Trigger, Stop und Ziel nach der nächsten Marktbewegung erneut prüfen.")
        )[:520]
        management_summary = self._tg_esc(
            str(event.get("management_summary") or "Paper-Trade nur weiterlaufen lassen, solange Trigger und Risiko intakt bleiben.")
        )[:520]
        rr = self._tg_esc(str(event.get("risk_reward") or "n/a"))
        ticket_status = self._tg_esc(str(ticket.get("status") or "paper_open"))
        horizon = self._tg_esc(str(ticket.get("horizon") or "nicht klassifiziert"))
        source_label = self._tg_esc(str(event.get("source_label") or "Paper-Autopilot"))
        source = self._tg_esc(str(ticket.get("source_label") or "nicht dokumentiert"))
        data_as_of = self._tg_esc(str(ticket.get("data_as_of") or "Zeitstempel fehlt"))
        market_data = ticket.get("market_data") if isinstance(ticket.get("market_data"), dict) else {}
        freshness = self._tg_esc(str(market_data.get("freshness") or "unbekannt"))
        liquidity = self._tg_esc(str(market_data.get("liquidity_status") or "unbekannt"))
        age_hours = market_data.get("age_hours")
        age_text = self._tg_esc(f"{float(age_hours):.1f}h" if age_hours is not None else "Alter unbekannt")
        try:
            notional_value = float(market_data.get("average_dollar_volume_5d") or 0)
        except (TypeError, ValueError):
            notional_value = 0
        notional_text = (
            f"{notional_value / 1_000_000_000:.1f} Mrd."
            if notional_value >= 1_000_000_000
            else f"{notional_value / 1_000_000:.1f} Mio."
            if notional_value >= 1_000_000
            else f"{notional_value:,.0f}".replace(",", ".")
            if notional_value > 0
            else "unbekannt"
        )
        notional_text = self._tg_esc(notional_text)
        validation = ticket.get("validation") if isinstance(ticket.get("validation"), dict) else {}
        execution_model = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        entry_execution = execution_model.get("entry") if isinstance(execution_model.get("entry"), dict) else {}
        execution_line = (
            f"<b>Fill-Modell:</b> Referenz {self._tg_price(entry_execution.get('reference_price'))} → "
            f"Fill {self._tg_price(entry_execution.get('fill_price'))} | "
            f"{self._tg_esc(str(entry_execution.get('cost_bps')))} bps gesamt | "
            f"Slippage {self._tg_esc(str(entry_execution.get('slippage_bps')))} bps | "
            f"Gebühren {self._tg_esc(str(entry_execution.get('fee_equivalent_bps')))} bps | Kosten {self._tg_money(entry_execution.get('estimated_cost_value'))}"
            if entry_execution
            else ""
        )
        news_evidence = ticket.get("news_evidence") if isinstance(ticket.get("news_evidence"), dict) else {}
        news_lines = self._paper_news_evidence_lines(news_evidence)
        warning_text = ", ".join(self._tg_esc(str(item)) for item in (validation.get("warnings") or [])[:3]) or "keine"
        account_after = self._paper_account_after_line(event)
        strategy_line = self._paper_strategy_context_line(event.get("strategy_context"))
        regime_lines = self._paper_entry_regime_lines(ticket)
        option_lines = self._paper_option_contract_lines(event)
        opened_at = self._paper_trade_time(event.get("opened_at"))
        return "\n".join(
            [
                f"<b>[PAPER GEÖFFNET] <code>{ticker}</code> {direction}</b>",
                *([f"<b>Eröffnet:</b> {opened_at}"] if opened_at else []),
                f"<b>Ausloeser:</b> {source_label}",
                *news_lines,
                f"<b>Asset:</b> {asset_class} | <b>Setup:</b> {setup} | <b>Score:</b> {confidence}",
                *option_lines,
                *([strategy_line] if strategy_line else []),
                *regime_lines,
                f"<b>Einstieg:</b> {entry} | <b>Menge:</b> {qty} | <b>Paper-Hebel:</b> {leverage:.1f}x",
                *([execution_line] if execution_line else []),
                f"<b>Demo-Geld:</b> investiert {invested} | aktueller Wert {current_value}",
                f"<b>Offenes Ergebnis:</b> {result_delta} ({result_label})",
                f"<b>Stop:</b> {stop} | <b>Ziel:</b> {target} | <b>CRV:</b> {rr}",
                f"<b>Ticket:</b> {ticket_status} | <b>Horizont:</b> {horizon}",
                f"<b>Max. Demo-Verlust:</b> {max_loss}",
                f"<b>Trigger:</b> {trigger}",
                f"<b>Invalidierung:</b> {invalidation}",
                f"<b>Jetzt tun:</b> {action} | {management_summary}",
                f"<b>Nächste Prüfung:</b> {next_check}",
                f"<b>Daten:</b> {source} | {data_as_of}",
                f"<b>Marktcheck:</b> {freshness} ({age_text}) | Liquidität {liquidity} | 5T-Notional {notional_text}",
                f"<b>Offene Checks:</b> {warning_text}",
                *([account_after] if account_after else []),
                "<b>Modus:</b> Nur 500k-Demo-Lernen. Keine automatische Echtgeld-Ausführung.",
            ]
        )

    def _paper_entry_regime_lines(self, ticket: Dict[str, Any]) -> List[str]:
        regime = ticket.get("entry_market_regime") if isinstance(ticket.get("entry_market_regime"), dict) else {}
        if not regime:
            return []
        state = lambda key: regime.get(key) if isinstance(regime.get(key), dict) else {}
        trend = self._tg_esc(str(state("trend").get("label") or "unavailable"))
        volatility = self._tg_esc(str(state("volatility").get("label") or "unavailable"))
        appetite = self._tg_esc(str(state("risk_appetite").get("label") or "unavailable"))
        breadth = self._tg_esc(str(state("breadth").get("label") or "unavailable"))
        rates = self._tg_esc(str(state("rates").get("label") or "unavailable"))
        dollar = self._tg_esc(str(state("dollar").get("label") or "unavailable"))
        quality = self._tg_esc(str(state("quality").get("status") or (regime.get("quality") or {}).get("status") or "partial"))
        data_as_of = self._paper_trade_time(regime.get("data_as_of"))
        lines = [
            f"<b>Entry-Regime:</b> {appetite} | Trend {trend} | Volatilität {volatility} (Proxy) | Breite {breadth} (Proxy)",
            f"<b>Makro am Entry:</b> US10Y {rates} | Dollar {dollar} | Qualität {quality}",
        ]
        if data_as_of:
            lines.append(f"<i>Regime-Datenstand {self._tg_esc(data_as_of)} · unveränderlich im Trade-Ticket</i>")
        return lines

    def _paper_option_contract_lines(self, event: Dict[str, Any]) -> List[str]:
        ticket = event.get("trade_ticket") if isinstance(event.get("trade_ticket"), dict) else {}
        contract = event.get("option_contract") if isinstance(event.get("option_contract"), dict) else {}
        if not contract and isinstance(ticket.get("option_contract"), dict):
            contract = ticket.get("option_contract") or {}
        decision = event.get("option_decision") if isinstance(event.get("option_decision"), dict) else {}
        if not decision and isinstance(ticket.get("option_decision"), dict):
            decision = ticket.get("option_decision") or {}
        if str(event.get("asset_class") or ticket.get("asset_class") or "").lower() != "option":
            return []

        lines: List[str] = []
        identity = ticket.get("option_contract_identity") if isinstance(ticket.get("option_contract_identity"), dict) else {}
        product = ticket.get("leveraged_product") if isinstance(ticket.get("leveraged_product"), dict) else {}
        if identity.get("identity_source") == "manually_validated_provider_product" and product:
            product_type = self._tg_esc(str(product.get("product_type") or "provider product"))
            issuer = self._tg_esc(str(product.get("issuer") or "n/a"))
            expiry = self._tg_esc(str(product.get("expiry") or "n/a"))
            spread = self._tg_pct(product.get("spread_pct")).lstrip("+")
            leverage = self._tg_esc(str(product.get("offered_leverage") or "n/a"))
            lines.extend(
                [
                    f"<b>Validiertes Produkt:</b> {product_type} | Emittent {issuer} | Strike/KO {self._tg_price(product.get('strike_or_knockout_level'))} | Verfall {expiry}",
                    f"<b>Produktquote:</b> Bid {self._tg_price(product.get('bid'))} / Ask {self._tg_price(product.get('ask'))} | Spread {spread} | angebotener Hebel {leverage}x | Multiplikator {self._tg_esc(str(product.get('contract_multiplier') or 'n/a'))}",
                    "<b>Produktidentität:</b> Beim Paper-Einstieg gesperrt; Wechsel von Emittent, Strike/KO oder Verfall ist nicht erlaubt.",
                ]
            )
        elif contract.get("status") == "available":
            symbol = self._tg_esc(str(contract.get("contract_symbol") or "n/a"))
            option_type = self._tg_esc(str(contract.get("option_type") or event.get("direction") or "n/a").upper())
            expiry = self._tg_esc(str(contract.get("expiry") or "n/a"))
            dte = self._tg_esc(str(contract.get("days_to_expiry") if contract.get("days_to_expiry") is not None else "n/a"))
            spread = self._tg_pct(contract.get("spread_pct")).lstrip("+")
            iv = self._tg_pct(contract.get("implied_volatility_pct")).lstrip("+")
            moneyness = self._tg_pct(contract.get("moneyness_pct"))
            break_even_distance = self._tg_pct(contract.get("distance_to_break_even_pct"))
            lines.extend(
                [
                    f"<b>Kontrakt:</b> <code>{symbol}</code> | {option_type} | Strike {self._tg_price(contract.get('strike'))} | Verfall {expiry} ({dte} Tage)",
                    f"<b>Optionsquote:</b> Bid {self._tg_price(contract.get('bid'))} / Ask {self._tg_price(contract.get('ask'))} | Spread {spread} | IV {iv}",
                    f"<b>Optionsliquidität:</b> Volumen {self._tg_esc(str(contract.get('volume') or 0))} | Open Interest {self._tg_esc(str(contract.get('open_interest') or 0))} | Moneyness {moneyness}",
                    f"<b>Break-even:</b> {self._tg_price(contract.get('break_even'))} ({break_even_distance} zum Underlying) | max. Prämienverlust/Kontrakt {self._tg_money(contract.get('max_loss_per_contract'))}",
                ]
            )
            source_label = self._tg_esc(str(contract.get("source_label") or contract.get("source") or "unbekannt"))
            quality = self._tg_esc(str(contract.get("quote_quality") or "unbekannt").replace("_", " "))
            lines.append(f"<b>Optionsdaten:</b> {source_label} | {quality} | Fill nicht garantiert")
            greeks = contract.get("greeks") if isinstance(contract.get("greeks"), dict) else {}
            if greeks:
                lines.append(
                    f"<b>Greeks:</b> Delta {self._tg_esc(str(greeks.get('delta') if greeks.get('delta') is not None else 'n/a'))} | "
                    f"Gamma {self._tg_esc(str(greeks.get('gamma') if greeks.get('gamma') is not None else 'n/a'))} | "
                    f"Theta {self._tg_esc(str(greeks.get('theta') if greeks.get('theta') is not None else 'n/a'))} | "
                    f"Vega {self._tg_esc(str(greeks.get('vega') if greeks.get('vega') is not None else 'n/a'))} | "
                    f"Quelle {self._tg_esc(str(contract.get('greeks_source') or 'Anbieter'))}"
                )
        else:
            reason = self._tg_esc(str(contract.get("reason") or "Optionskette nicht verfügbar"))[:260]
            lines.append(f"<b>Optionsdaten:</b> Kein verifizierbarer Kontrakt-Snapshot ({reason}); Prämie ist nur eine Schätzung.")

        thesis = self._tg_esc(str(decision.get("thesis") or ""))[:520]
        drivers = [self._tg_esc(str(item)) for item in (decision.get("event_drivers") or [])[:5]]
        data_limit = self._tg_esc(str(decision.get("data_limit") or ""))[:360]
        if thesis:
            lines.append(f"<b>Options-These:</b> {thesis}")
        if drivers:
            lines.append(f"<b>Entscheidende Treiber:</b> {' / '.join(drivers)}")
        if data_limit:
            lines.append(f"<b>Datenlimit:</b> {data_limit}")
        return lines

    def _paper_news_evidence_lines(self, evidence: Dict[str, Any]) -> List[str]:
        if not isinstance(evidence, dict) or not evidence:
            return []
        reporting = evidence.get("reporting_source") if isinstance(evidence.get("reporting_source"), dict) else {}
        primary = evidence.get("primary_source") if isinstance(evidence.get("primary_source"), dict) else {}
        facts = evidence.get("facts") if isinstance(evidence.get("facts"), dict) else {}
        interpretation = evidence.get("interpretation") if isinstance(evidence.get("interpretation"), dict) else {}
        comparison = evidence.get("source_comparison") if isinstance(evidence.get("source_comparison"), dict) else {}
        correction = evidence.get("correction_status") if isinstance(evidence.get("correction_status"), dict) else {}
        market = evidence.get("market_confirmation") if isinstance(evidence.get("market_confirmation"), dict) else {}

        reporting_url = self._tg_esc(str(reporting.get("url") or evidence.get("source_url") or ""))
        reporting_publisher = self._tg_esc(str(reporting.get("publisher") or evidence.get("publisher") or "Tier-1-Quelle"))
        title = self._tg_esc(str(evidence.get("title") or "Verifizierter News-Trigger"))[:320]
        lines: List[str] = []
        if reporting_url:
            lines.append(f"<b>Berichtende Quelle:</b> <a href=\"{reporting_url}\">{reporting_publisher}</a> | {title}")
        else:
            lines.append(f"<b>Berichtende Quelle:</b> {reporting_publisher} | {title}")

        primary_url = self._tg_esc(str(primary.get("url") or ""))
        primary_label = self._tg_esc(
            " · ".join(
                part
                for part in [str(primary.get("authority") or ""), str(primary.get("form") or "")]
                if part
            )
            or (
                "verifiziert, Link im Legacy-Ticket nicht gespeichert"
                if evidence.get("original_document_verified") is True
                else "nicht verifiziert"
            )
        )
        if primary_url:
            lines.append(f"<b>Primärquelle:</b> <a href=\"{primary_url}\">{primary_label}</a>")
        else:
            lines.append(f"<b>Primärquelle:</b> {primary_label}")

        fact_summary = self._tg_esc(str(facts.get("summary") or evidence.get("fact_summary") or evidence.get("title") or ""))[:620]
        fact_basis = self._tg_esc(str(facts.get("basis") or evidence.get("fact_basis") or "offen"))
        if fact_summary:
            lines.append(f"<b>Bestätigter Faktenstand ({fact_basis}):</b> {fact_summary}")

        meaning = self._tg_esc(str(interpretation.get("meaning") or ""))[:420]
        assessment = self._tg_esc(str(interpretation.get("assessment") or ""))[:360]
        if meaning or assessment:
            lines.append(f"<b>Unsere Interpretation – kein Quellenfakt:</b> {meaning or assessment}")
            if meaning and assessment:
                lines.append(f"<b>Einschätzung:</b> {assessment}")

        publisher_count = int(comparison.get("publisher_count") or 1)
        agreement = self._tg_esc(str(comparison.get("source_agreement") or evidence.get("source_agreement") or "single_headline_signal"))
        lines.append(
            f"<b>Quellenabgleich:</b> {publisher_count} Publisher | {agreement} | Unabhängigkeit nicht technisch bewiesen"
        )
        correction_status = str(correction.get("status") or "not_checked_legacy_context")
        correction_label = {
            "not_detected_at_capture": "bei Erfassung keine Korrektur erkannt",
            "not_checked_legacy_context": "bei Legacy-Daten nicht geprüft",
            "correction_detected": "KORREKTUR ERKANNT – Trade-Gate blockiert",
            "retracted_or_withdrawn": "WIDERRUF/RÜCKZUG ERKANNT – Trade-Gate blockiert",
        }.get(correction_status, correction_status)
        lines.append(f"<b>Korrekturstatus:</b> {self._tg_esc(correction_label)}")

        if market:
            lines.append(
                f"<b>Marktbestätigung:</b> {self._tg_esc(str(market.get('status') or 'offen'))} | "
                f"relative Reaktion {self._tg_pct(market.get('relative_move_since_publication')).lstrip('+')} | "
                f"Fenster {'ausgerichtet' if market.get('event_window_aligned') else 'nicht ausgerichtet'}"
            )
        lines.append("<i>Zeitliche Marktbestätigung beweist keine Kausalität; laufende Quellenkorrekturen sind nicht garantiert.</i>")
        return lines

    def _paper_strategy_context_line(self, context: Any) -> str:
        if not isinstance(context, dict) or not context:
            return ""
        label = self._tg_esc(str(context.get("label") or context.get("id") or "Strategie"))
        status = self._tg_esc(self._paper_label(context.get("status"), "lernen"))
        recommendation = self._tg_esc(self._paper_label(context.get("recommendation"), "weiter lernen"))
        ready = "bereit zur manuellen Prüfung" if context.get("real_world_ready") else "nur Paper-Lernen"
        sample = f"{self._tg_esc(str(context.get('sample_size') or 0))}/{self._tg_esc(str(context.get('minimum_usable_sample') or 30))}"
        profit_factor = context.get("profit_factor")
        pf_text = "offen" if profit_factor is None else self._tg_esc(f"{float(profit_factor):.2f}")
        expectancy = self._tg_signed_money(context.get("expectancy_value"))
        hit_rate = self._tg_pct(context.get("hit_rate")).lstrip("+")
        gaps = [self._tg_esc(str(item)) for item in (context.get("readiness_gaps") or [])[:2]]
        next_step = self._tg_esc(str(context.get("next_step") or "Paper-Beweise sammeln."))[:260]
        line = (
            f"<b>Strategie:</b> {label} | {status} / {recommendation} | {ready}"
            f"\n<b>Strategie-Beweise:</b> {sample} Trades | Treffer {hit_rate} | PF {pf_text} | Erwartung {expectancy}/Trade"
            f"\n<b>Nächster Strategie-Check:</b> {next_step}"
        )
        if gaps:
            line += f"\n<b>Blocker:</b> {' / '.join(gaps)}"
        return line

    def _render_telegram_paper_trade_closed_alert(self, event: Dict[str, Any]) -> str:
        ticket = event.get("trade_ticket") if isinstance(event.get("trade_ticket"), dict) else {}
        execution_model = ticket.get("execution_model") if isinstance(ticket.get("execution_model"), dict) else {}
        exit_execution = execution_model.get("exit") if isinstance(execution_model.get("exit"), dict) else {}
        ticker = self._tg_esc(str(event.get("ticker") or "n/a"))
        direction = self._tg_esc(str(event.get("direction") or "n/a").upper())
        asset_class = self._tg_esc(str(event.get("asset_class") or "asset"))
        setup = self._tg_esc(str(event.get("setup_type") or "setup"))
        entry_source = self._tg_esc(str(ticket.get("entry_source_label") or "Paper-Autopilot"))
        entry = self._tg_price(event.get("entry_price"))
        exit_price = self._tg_price(event.get("closed_price"))
        invested = self._tg_money(event.get("invested_value"))
        final_value = self._tg_money(event.get("final_value"))
        quantity = self._tg_esc(str(event.get("quantity") if event.get("quantity") is not None else "n/a"))
        leverage = float(event.get("leverage") or ticket.get("leverage") or 1)
        result_label = self._tg_esc(self._paper_label(event.get("result_label"), "neutral"))
        pnl_pct = self._tg_pct(event.get("realized_pnl_pct"))
        pnl_value = self._tg_signed_money(event.get("realized_pnl_value"))
        try:
            realized_value = float(event.get("realized_pnl_value") or 0)
        except (TypeError, ValueError):
            realized_value = 0
        outcome = "GEWINN" if realized_value > 0 else "VERLUST" if realized_value < 0 else "NEUTRAL"
        exit_reason = self._tg_esc(self._paper_label(event.get("exit_reason"), "Paper-Exit"))
        lesson = self._tg_esc(str(event.get("lessons_learned") or "Journal prüfen, bevor dieses Setup wieder genutzt wird."))[:620]
        rr = self._tg_esc(str(event.get("risk_reward") or "n/a"))
        option_lines = self._paper_option_contract_lines(event)
        account_after = self._paper_account_after_line(event)
        opened_at = self._paper_trade_time(event.get("opened_at"))
        closed_at = self._paper_trade_time(event.get("closed_at"))
        holding_period = self._paper_trade_holding_period(event.get("opened_at"), event.get("closed_at"))
        timing_parts = [part for part in [opened_at, closed_at, holding_period] if part]
        execution_line = (
            f"<b>Exit-Fill:</b> Referenz {self._tg_price(exit_execution.get('reference_price'))} → "
            f"Fill {self._tg_price(exit_execution.get('fill_price'))} | "
            f"{self._tg_esc(str(exit_execution.get('cost_bps')))} bps gesamt | "
            f"Slippage {self._tg_esc(str(exit_execution.get('slippage_bps')))} bps | "
            f"Gebühren {self._tg_esc(str(exit_execution.get('fee_equivalent_bps')))} bps | Kosten {self._tg_money(exit_execution.get('estimated_cost_value'))}"
            if exit_execution
            else ""
        )
        return "\n".join(
            [
                f"<b>[PAPER GESCHLOSSEN - {outcome}] <code>{ticker}</code> {direction}</b>",
                *([f"<b>Zeitraum:</b> {' bis '.join(timing_parts[:2])} | gehalten {timing_parts[2]}"] if len(timing_parts) == 3 else []),
                f"<b>Entry-Quelle:</b> {entry_source}",
                f"<b>Asset:</b> {asset_class} | <b>Setup:</b> {setup} | <b>Menge:</b> {quantity} | <b>Paper-Hebel:</b> {leverage:.1f}x",
                *option_lines,
                f"<b>Exit-Grund:</b> {exit_reason}",
                f"<b>Einstieg:</b> {entry} | <b>Schluss:</b> {exit_price} | <b>CRV:</b> {rr}",
                *([execution_line] if execution_line else []),
                f"<b>Kapitalfluss Trade:</b> Einsatz {invested} | R\u00fcckfluss {final_value}",
                f"<b>Realisiertes Ergebnis:</b> {pnl_value} | {pnl_pct} | {result_label}",
                f"<b>Lektion:</b> {lesson}",
                *([account_after] if account_after else []),
                "<b>Modus:</b> Nur Demo-Lernen. Lektion nutzen, bevor Echtgeld geprüft wird.",
            ]
        )

    def _paper_account_after_line(self, event: Dict[str, Any]) -> str:
        capital_flow = event.get("account_capital_flow") if isinstance(event.get("account_capital_flow"), dict) else {}
        if not capital_flow and isinstance(event.get("capital_flow"), dict):
            capital_flow = event.get("capital_flow") or {}
        account_equity = capital_flow.get("equity_value", event.get("account_equity"))
        if account_equity is None:
            return ""
        equity = self._tg_money(account_equity)
        cash = self._tg_money(capital_flow.get("cash_available_value", event.get("account_cash_available")))
        exposure = self._tg_money(capital_flow.get("open_exposure_value", event.get("account_open_exposure")))
        realized = self._tg_signed_money(capital_flow.get("realized_pnl_value", event.get("account_realized_pnl_value")))
        unrealized = self._tg_signed_money(capital_flow.get("unrealized_pnl_value", event.get("account_unrealized_pnl_value")))
        net_pnl = self._tg_signed_money(capital_flow.get("net_pnl_value", event.get("account_net_pnl_value")))
        net_pnl_pct = self._tg_pct(capital_flow.get("net_pnl_pct", event.get("account_net_pnl_pct")))
        performance_line = self._paper_performance_line(event.get("account_performance"))
        allocation_line = self._paper_allocation_line(event)
        return (
            f"<b>Demo-Konto danach:</b> Equity {equity} | seit Start {net_pnl} ({net_pnl_pct})"
            f"\n<b>Verfügbar:</b> Cash {cash} | offen investiert {exposure}"
            f"\n<b>Geldfluss:</b> realisiert {realized} | offen {unrealized}"
            f"{allocation_line}"
            f"{performance_line}"
        )

    def _paper_allocation_line(self, event: Dict[str, Any]) -> str:
        limits = event.get("account_asset_class_limits") if isinstance(event.get("account_asset_class_limits"), dict) else {}
        if not limits:
            return ""
        parts: List[str] = []
        for key, label in (("equity", "Aktien"), ("etf", "ETF"), ("crypto", "Krypto"), ("option", "Optionen")):
            item = limits.get(key) if isinstance(limits.get(key), dict) else {}
            parts.append(
                f"{label} {float(item.get('used_pct') or 0):.1f}/{float(item.get('limit_pct') or 0):.0f}%"
            )
        reserve = self._tg_money(event.get("account_cash_reserve_target"))
        return f"\n<b>Allokation:</b> {' | '.join(parts)} | Cashreserve-Ziel {reserve}"

    def _paper_performance_line(self, performance: Any) -> str:
        if not isinstance(performance, dict) or not performance:
            return ""
        sample_size = performance.get("sample_size")
        minimum = performance.get("minimum_usable_sample") or 30
        expectancy = self._tg_signed_money(performance.get("expectancy_value"))
        profit_factor = performance.get("profit_factor")
        pf_text = "offen" if profit_factor is None else self._tg_esc(f"{float(profit_factor):.2f}")
        win_rate = self._tg_pct(performance.get("win_rate")).lstrip("+")
        evidence = self._tg_esc(str(performance.get("evidence_label") or "zu wenig Daten"))
        return (
            f"\n<b>Lernqualität:</b> {self._tg_esc(str(sample_size or 0))}/{self._tg_esc(str(minimum))} Trades | "
            f"PF {pf_text} | Erwartung {expectancy}/Trade | Treffer {win_rate} | {evidence}"
        )

    def _paper_trade_datetime(self, value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        target_timezone = ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))
        if parsed.tzinfo is None:
            source_timezone = ZoneInfo("UTC") if os.getenv("APP_ENV", "").lower() == "production" else target_timezone
            parsed = parsed.replace(tzinfo=source_timezone)
        return parsed.astimezone(target_timezone)

    def _paper_trade_time(self, value: Any) -> str:
        parsed = self._paper_trade_datetime(value)
        return parsed.strftime("%d.%m.%Y, %H:%M %Z") if parsed else ""

    def _paper_trade_holding_period(self, opened_at: Any, closed_at: Any) -> str:
        opened = self._paper_trade_datetime(opened_at)
        closed = self._paper_trade_datetime(closed_at)
        if not opened or not closed or closed < opened:
            return ""
        total_minutes = int((closed - opened).total_seconds() // 60)
        days, remaining_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(remaining_minutes, 60)
        parts = []
        if days:
            parts.append(f"{days}T")
        if hours:
            parts.append(f"{hours}Std")
        if minutes or not parts:
            parts.append(f"{minutes}Min")
        return " ".join(parts)

    def _render_telegram_paper_trade_management_alert(self, event: Dict[str, Any]) -> str:
        ticker = self._tg_esc(str(event.get("ticker") or "n/a"))
        direction = self._tg_esc(str(event.get("direction") or "n/a").upper())
        asset_class = self._tg_esc(str(event.get("asset_class") or "asset"))
        setup = self._tg_esc(str(event.get("setup_type") or "setup"))
        status = self._tg_esc(self._paper_label(event.get("management_status"), "überwachen").upper())
        action = self._tg_esc(self._paper_label(event.get("management_action"), "prüfen"))
        grade = self._tg_esc(self._paper_label(event.get("decision_grade"), "prüfen").upper())
        next_check = self._tg_esc(str(event.get("next_check") or "Trigger, Stop und Ziel erneut prüfen."))[:520]
        summary = self._tg_esc(str(event.get("management_summary") or "Paper-Trade prüfen."))[:520]
        entry = self._tg_price(event.get("entry_price"))
        current = self._tg_price(event.get("current_price"))
        stop = self._tg_price(event.get("stop_price"))
        target = self._tg_price(event.get("target_price"))
        pnl = self._tg_pct(event.get("unrealized_pnl_pct"))
        pnl_value = self._tg_signed_money(event.get("unrealized_pnl_value"))
        quantity = self._tg_esc(str(event.get("quantity") if event.get("quantity") is not None else "n/a"))
        invested = self._tg_money(event.get("invested_value"))
        current_value = self._tg_money(event.get("current_value"))
        opened_at = self._paper_trade_time(event.get("opened_at"))
        risk_distance = self._tg_pct(event.get("risk_distance_pct"))
        target_progress = self._tg_pct(event.get("target_progress_pct"))
        news_evidence = event.get("news_evidence") if isinstance(event.get("news_evidence"), dict) else {}
        news_url = self._tg_esc(str(news_evidence.get("source_url") or ""))
        news_publisher = self._tg_esc(str(news_evidence.get("publisher") or "Newsquelle"))
        elapsed_hours = event.get("elapsed_hours")
        max_holding_days = event.get("max_holding_days")
        source_status = self._tg_esc(self._paper_label(event.get("source_status"), ""))
        source_checked_at = self._paper_trade_time(event.get("source_checked_at"))
        affected_source_url = self._tg_esc(str(event.get("affected_source_url") or ""))
        source_warning = (
            f'<b>QUELLENWARNUNG:</b> {source_status} | geprüft {source_checked_at}'
            + (f' | <a href="{affected_source_url}">betroffene Quelle</a>' if affected_source_url else "")
            if event.get("management_status") == "news_source_invalidated"
            else ""
        )
        event_window_line = (
            f"<b>News-Lifecycle:</b> {float(elapsed_hours):.1f}h gelaufen | max. {self._tg_esc(str(max_holding_days))} Tage | "
            f"<a href=\"{news_url}\">{news_publisher}</a>"
            if news_evidence and news_url and elapsed_hours is not None and max_holding_days
            else ""
        )
        return "\n".join(
            [
                f"<b>[PAPER MANAGEN] <code>{ticker}</code> {direction} | {status}</b>",
                *([f"<b>Eröffnet:</b> {opened_at}"] if opened_at else []),
                f"<b>Aktion:</b> {action} | <b>Stufe:</b> {grade}",
                *([source_warning] if source_warning else []),
                *([event_window_line] if event_window_line else []),
                f"<b>Position:</b> {asset_class} | {setup} | Menge {quantity}",
                f"<b>Preis:</b> Einstieg {entry} | jetzt {current}",
                f"<b>Kapital:</b> Einsatz {invested} | aktueller Wert {current_value}",
                f"<b>Offenes Ergebnis:</b> {pnl_value} | {pnl}",
                f"<b>Plan:</b> Stop {stop} | Ziel {target}",
                f"<b>Abstand:</b> Stop {risk_distance} | Ziel-Fortschritt {target_progress}",
                f"<b>Warum:</b> {summary}",
                f"<b>Nächste Prüfung:</b> {next_check}",
                "<b>Modus:</b> Nur Demo-Lernen. Manuell prüfen; keine automatische Echtgeld-Ausführung.",
            ]
        )

    def _render_telegram_paper_account_status_alert(self, event: Dict[str, Any]) -> str:
        status = self._tg_esc(str(event.get("day_status") or "monitor").upper())
        action = self._tg_esc(str(event.get("day_action") or "Aktuellen Paper-Plan halten."))[:520]
        capital_flow = event.get("capital_flow") if isinstance(event.get("capital_flow"), dict) else {}
        capital_status = self._tg_esc(self._paper_label(capital_flow.get("capital_status", event.get("capital_status")), "neutral"))
        starting = self._tg_money(capital_flow.get("starting_capital_value", event.get("starting_capital")))
        equity = self._tg_money(capital_flow.get("equity_value", event.get("equity")))
        pnl_value = self._tg_signed_money(capital_flow.get("net_pnl_value", event.get("net_pnl_value")))
        pnl_pct = self._tg_pct(capital_flow.get("net_pnl_pct", event.get("net_pnl_pct")))
        realized = self._tg_signed_money(capital_flow.get("realized_pnl_value"))
        unrealized = self._tg_signed_money(capital_flow.get("unrealized_pnl_value"))
        invested = self._tg_money(capital_flow.get("open_exposure_value", event.get("open_exposure_value")))
        cash = self._tg_money(capital_flow.get("cash_available_value", event.get("cash_available_value")))
        open_count = self._tg_esc(str(capital_flow.get("open_trade_count", event.get("open_trade_count") if event.get("open_trade_count") is not None else "0")))
        closed_count = self._tg_esc(str(capital_flow.get("closed_trade_count", event.get("closed_trade_count") if event.get("closed_trade_count") is not None else "0")))
        counts = event.get("management_counts") if isinstance(event.get("management_counts"), dict) else {}
        count_text = ", ".join(f"{self._tg_esc(str(key))}: {self._tg_esc(str(value))}" for key, value in sorted(counts.items())) or "keine"
        circuit = event.get("risk_circuit") if isinstance(event.get("risk_circuit"), dict) else {}
        circuit_status = self._tg_esc(str(circuit.get("status") or "ready").upper())
        circuit_reasons = [self._tg_esc(str(item)) for item in (circuit.get("display_reasons") or circuit.get("reasons") or [])[:2]]
        cooldown_until = self._paper_trade_time(circuit.get("cooldown_until"))
        performance_line = self._paper_performance_line(event.get("performance"))
        evidence_campaign = event.get("evidence_campaign") if isinstance(event.get("evidence_campaign"), dict) else {}
        strategy_candidate_coverage = event.get("strategy_candidate_coverage") if isinstance(event.get("strategy_candidate_coverage"), list) else []

        lines = [
            f"<b>[PAPER KONTO] {status}</b>",
            f"<b>Aktion heute:</b> {action}",
            f"<b>Kapital:</b> Start {starting} | Equity {equity} | {capital_status}",
            f"<b>Netto-Ergebnis:</b> {pnl_value} ({pnl_pct})",
            f"<b>Geldfluss:</b> realisiert {realized} | offen {unrealized}",
            f"<b>Geld:</b> investiert {invested} | freies Cash {cash}",
            f"<b>Trades:</b> offen {open_count} | geschlossen {closed_count} | Stufen {count_text}",
            f"<b>Risk Circuit:</b> {circuit_status} | Drawdown {self._tg_pct(circuit.get('current_drawdown_pct')).lstrip('+')} / Limit {self._tg_pct(circuit.get('drawdown_limit_pct')).lstrip('+')}",
            f"<b>Heute:</b> {self._tg_signed_money(circuit.get('daily_realized_pnl_value'))} | Verlustserie {self._tg_esc(str(circuit.get('consecutive_losses') or 0))}",
        ]
        if performance_line:
            lines.append(performance_line.lstrip())
        if evidence_campaign:
            next_priority = evidence_campaign.get("next_priority") if isinstance(evidence_campaign.get("next_priority"), dict) else {}
            lines.append(
                f"<b>Evidenzkampagne:</b> {self._tg_esc(str(evidence_campaign.get('strategies_ready') or 0))}/"
                f"{self._tg_esc(str(evidence_campaign.get('strategy_count') or 0))} Strategien reif | "
                f"geschlossen {self._tg_esc(str(evidence_campaign.get('closed_trades_total') or 0))}/"
                f"{self._tg_esc(str(evidence_campaign.get('required_closed_trades_total') or 0))} | "
                f"Outcomes {self._tg_esc(str(evidence_campaign.get('decisive_outcomes_total') or 0))}/"
                f"{self._tg_esc(str(evidence_campaign.get('global_outcome_target') or 100))}"
            )
            if next_priority:
                lines.append(
                    f"<b>Nächster Evidenz-Fokus:</b> {self._tg_esc(str(next_priority.get('label') or next_priority.get('id') or 'Strategie'))} "
                    f"({self._tg_esc(str(next_priority.get('progress_pct') or 0))}%)"
                )
            zero_rows = evidence_campaign.get("zero_evidence_strategies") if isinstance(evidence_campaign.get("zero_evidence_strategies"), list) else []
            zero_labels = [
                self._tg_esc(str(item.get("label") or item.get("id") or "Strategie"))
                for item in zero_rows[:4]
                if isinstance(item, dict)
            ]
            if zero_labels:
                lines.append(f"<b>Noch ohne Evidenz:</b> {' · '.join(zero_labels)}")
        if strategy_candidate_coverage:
            with_candidates = sum(1 for item in strategy_candidate_coverage if int(item.get("candidate_count") or 0) > 0)
            qualified = sum(
                1
                for item in strategy_candidate_coverage
                if any(
                    int(value or 0) > 0
                    for value in (item.get("qualified_counts") or {}).values()
                )
            )
            source_gaps = [
                self._tg_esc(str(item.get("strategy_label") or item.get("strategy_id") or "Strategie"))
                for item in strategy_candidate_coverage
                if item.get("status") == "source_gap"
            ]
            lines.append(
                f"<b>Strategie-Scanner:</b> Kandidaten für {with_candidates}/{len(strategy_candidate_coverage)} Strategien | "
                f"qualifiziert {qualified}/{len(strategy_candidate_coverage)}"
            )
            if source_gaps:
                lines.append(f"<b>Aktuelle Quellenlücken:</b> {' · '.join(source_gaps[:4])}")
        if circuit_reasons:
            lines.append(f"<b>Warum pausiert:</b> {' / '.join(circuit_reasons)}")
        if cooldown_until:
            lines.append(f"<b>Cooldown bis:</b> {cooldown_until}")
        action_queue = event.get("trade_action_queue") if isinstance(event.get("trade_action_queue"), dict) else {}
        queue_items = action_queue.get("items") if isinstance(action_queue.get("items"), list) else []
        if queue_items:
            queue_message = self._tg_esc(str(action_queue.get("message") or "Top-Paper-Pruefung offen."))[:360]
            lines.append(f"<b>Jetzt zuerst:</b> {queue_message}")
            lines.append("<b>Top-Pruefungen:</b>")
            for trade in queue_items[:3]:
                ticker = self._tg_esc(str(trade.get("ticker") or "n/a"))
                direction = self._tg_esc(str(trade.get("direction") or "n/a").upper())
                grade = self._tg_esc(self._paper_label(trade.get("decision_grade"), "halten").upper())
                priority = self._tg_esc(str(trade.get("priority_label") or "Plan pruefen"))
                result = self._tg_signed_money(trade.get("unrealized_pnl_value"))
                summary = self._tg_esc(str(trade.get("summary") or "Plan pruefen."))[:260]
                next_check = self._tg_esc(str(trade.get("next_check") or "Trigger, Stop und Ziel erneut pruefen."))[:260]
                lines.append(f"- <code>{ticker}</code> {direction} | {priority} | {grade} | P/L {result}")
                lines.append(f"  Warum: {summary}")
                lines.append(f"  Naechste Pruefung: {next_check}")
        top_trades = event.get("top_trades") if isinstance(event.get("top_trades"), list) else []
        if top_trades and not queue_items:
            lines.append("<b>Top-Prüfungen:</b>")
            for trade in top_trades[:3]:
                ticker = self._tg_esc(str(trade.get("ticker") or "n/a"))
                direction = self._tg_esc(str(trade.get("direction") or "n/a").upper())
                grade = self._tg_esc(self._paper_label(trade.get("grade"), "halten").upper())
                result = self._tg_signed_money(trade.get("result_value_delta"))
                summary = self._tg_esc(str(trade.get("summary") or "Plan prüfen."))[:260]
                next_check = self._tg_esc(str(trade.get("next_check") or "Trigger, Stop und Ziel erneut prüfen."))[:260]
                lines.append(f"- <code>{ticker}</code> {direction} | {grade} | P/L {result}")
                lines.append(f"  Warum: {summary}")
                lines.append(f"  Nächste Prüfung: {next_check}")
        lines.append("<b>Modus:</b> Nur 500k-Demo-Lernen. Keine automatische Echtgeld-Ausführung.")
        return "\n".join(lines)

    def _render_telegram_paper_learning_alert(self, event: Dict[str, Any]) -> str:
        severity = str(event.get("severity") or "learning").upper()
        setup = self._tg_esc(str(event.get("setup_type") or "setup"))
        title = self._tg_esc(str(event.get("title") or "Paper-Learning-Alert"))
        hit_rate = self._tg_esc(str(event.get("hit_rate") if event.get("hit_rate") is not None else "n/a"))
        decisive = self._tg_esc(str(event.get("decisive") if event.get("decisive") is not None else "n/a"))
        score_delta = event.get("score_delta")
        reason = self._tg_esc(str(event.get("reason") or event.get("line") or ""))[:620]
        action = self._tg_esc(str(event.get("action") or "Manuell prüfen"))
        critical_check = self._tg_esc(
            str(event.get("critical_check") or "Nicht auf Echtgeld übertragen, bevor Paper-Beweise dokumentiert sind.")
        )[:520]
        review_focus = [self._tg_esc(str(item))[:260] for item in (event.get("review_focus") or [])[:3]]
        checklist = [self._tg_esc(str(item))[:220] for item in (event.get("manual_review_checklist") or [])[:5]]
        source = self._tg_esc(str(event.get("source_label") or "Paper-Outcome-Lernen"))
        lines = [
            f"<b>[LEARNING {severity}] {title}</b>",
            f"<b>Setup:</b> {setup}",
            f"<b>Beweise:</b> {decisive} klare Prüfungen / {hit_rate}% Trefferquote",
        ]
        if score_delta is not None:
            lines.append(f"<b>Score-Effekt:</b> {self._tg_esc(str(score_delta))}")
        if reason:
            lines.append(f"<b>Warum wichtig:</b> {reason}")
        if review_focus:
            lines.append("<b>Prüf-Fokus:</b>")
            lines.extend(f"- {item}" for item in review_focus)
        if checklist:
            lines.append("<b>Manuelles Echtgeld-Gate:</b>")
            lines.extend(f"- {item}" for item in checklist)
        lines.extend(
            [
                f"<b>Kritischer Check:</b> {critical_check}",
                f"<b>Aktion:</b> {action}",
                f"<b>Quelle:</b> {source}",
            ]
        )
        return "\n".join(lines)

    def _render_telegram_macro_alert(self, event: Dict[str, Any]) -> str:
        severity = str(event.get("severity") or "high").lower()
        marker = "KRITISCH" if severity == "critical" else "HOCH"
        country = self._tg_esc(str(event.get("country") or event.get("region") or "Global"))
        event_type = self._tg_esc(self._macro_event_type_label(str(event.get("event_type") or "Macro")))
        title = self._tg_esc(str(event.get("title") or "Macro alert"))
        impact = self._tg_esc(str(event.get("impact_score") or "n/a"))
        assets = ", ".join(self._tg_esc(str(asset)) for asset in (event.get("affected_assets") or [])[:8]) or "n/a"
        trigger = self._tg_esc(str(event.get("trigger") or "Confirmation abwarten."))
        invalidation = self._tg_esc(str(event.get("invalidation") or "Invalid wenn keine Preisreaktion folgt."))
        action = self._tg_esc(self._macro_action_label(str(event.get("action") or "watch")))
        source = self._tg_esc(str(event.get("source_label") or "Market radar"))
        source_quality = self._tg_esc(self._macro_source_quality_label(str(event.get("source_quality") or "")))
        why = self._tg_esc(str(event.get("why_it_matters") or ""))[:520]
        meaning = self._tg_esc(str(event.get("meaning") or ""))[:520]
        read_through = self._tg_esc(str(event.get("read_through") or ""))[:520]
        critical_check = self._tg_esc(str(event.get("critical_check") or ""))[:520]
        confidence = self._tg_esc(str(event.get("confidence_label") or "mittel - erst Marktreaktion bestaetigen"))
        signal_status = self._tg_esc(
            str(event.get("signal_status") or "NUR BEOBACHTEN - noch kein belastbares Trade-Setup")
        )
        fact_status = self._tg_esc(str(event.get("fact_status") or "Einordnung offen"))
        horizon = self._tg_esc(str(event.get("horizon") or "intraday bis mittelfristig"))
        mechanism = self._tg_esc(str(event.get("market_mechanism") or "Marktreaktion muss bestaetigen."))[:520]
        base_case = self._tg_esc(str(event.get("base_case") or "Neutral bis zur Bestaetigung."))[:520]
        next_check = self._tg_esc(str(event.get("next_check") or "Quelle, Preis und Volumen pruefen."))[:520]
        edge_question = self._tg_esc(str(event.get("edge_question") or ""))[:520]
        link = str(event.get("source_url") or "").strip()
        lines = [
            f"<b>[{marker}] Macro Alert: {country} / {event_type}</b>",
            f"<b>Signalstatus:</b> {signal_status}",
            f"<b>Meldung:</b> {title}",
            f"<b>Impact:</b> {impact}/100",
            f"<b>Faktenstatus:</b> {fact_status}",
            f"<b>Quellenqualitaet:</b> {source_quality}",
            f"<b>Sicherheit:</b> {confidence}",
            f"<b>Zeithorizont:</b> {horizon}",
            f"<b>Betroffen:</b> {assets}",
            f"<b>Trigger:</b> {trigger}",
            f"<b>Invalidierung:</b> {invalidation}",
        ]
        if why:
            lines.append(f"<b>Warum wichtig:</b> {why}")
        if meaning:
            lines.append(f"<b>Was es aussagt:</b> {meaning}")
        lines.append(f"<b>Marktmechanismus:</b> {mechanism}")
        lines.append(f"<b>Basisszenario (bedingt):</b> {base_case}")
        if read_through:
            lines.append(f"<b>Read-through:</b> {read_through}")
        if edge_question:
            lines.append(f"<b>Edge-Frage:</b> {edge_question}")
        lines.extend([
            f"<b>Kritischer Check:</b> {critical_check or 'Nicht handeln, bevor Quelle, Preisreaktion und Volumen zusammenpassen.'}",
            f"<b>Als Naechstes pruefen:</b> {next_check}",
            f"<b>Aktion:</b> {action}",
            f"<b>Quelle:</b> {source}",
        ])
        if link:
            lines.append(f'<a href="{escape(link, quote=True)}">Quelle oeffnen</a>')
        return "\n".join(lines)

    def _build_html_email(self, subject: str, events: List[Dict[str, Any]]) -> str:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cards: List[str] = []
        current_section = "Overview"

        for event in events:
            line = (event.get("line") or "").strip()
            if not line:
                continue
            if self._is_section_heading(line):
                current_section = line.rstrip(":")
                continue

            tone = self._tone_for_event(event)
            meta_parts = [escape(current_section)]
            if event.get("conviction_score") is not None:
                meta_parts.append(f"Score {escape(str(event['conviction_score']))}")
            if event.get("source_label"):
                meta_parts.append(escape(str(event["source_label"])))

            link_html = ""
            if event.get("source_url"):
                safe_url = escape(str(event["source_url"]), quote=True)
                link_html = (
                    f'<a href="{safe_url}" '
                    'style="display:inline-block;margin-top:12px;color:#0f766e;'
                    'font-weight:700;text-decoration:none;">Open source</a>'
                )

            cards.append(
                f"""
                <div style="border:1px solid rgba(15,23,42,0.08);border-radius:20px;padding:18px 18px 16px;background:{tone['background']};box-shadow:0 10px 28px rgba(15,23,42,0.05);">
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                    <div style="font-size:11px;font-weight:800;letter-spacing:0.18em;text-transform:uppercase;color:#64748b;">{escape(current_section)}</div>
                    <div style="display:inline-flex;align-items:center;border-radius:999px;padding:6px 10px;background:{tone['pill_bg']};color:{tone['pill_fg']};font-size:10px;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;">{escape(tone['label'])}</div>
                  </div>
                  <div style="margin-top:12px;font-size:15px;line-height:1.65;color:#0f172a;font-weight:600;">{escape(line)}</div>
                  <div style="margin-top:12px;font-size:12px;line-height:1.6;color:#64748b;">{' | '.join(meta_parts)}</div>
                  {link_html}
                </div>
                """
            )

        cards_html = "".join(cards) or """
            <div style="border:1px solid rgba(15,23,42,0.08);border-radius:20px;padding:18px;background:#ffffff;">
              <div style="font-size:15px;line-height:1.65;color:#0f172a;font-weight:600;">No fresh items in this run.</div>
            </div>
        """

        return f"""
        <!doctype html>
        <html lang="en">
          <body style="margin:0;background:#f5f2ea;font-family:Inter,Segoe UI,Arial,sans-serif;color:#0f172a;">
            <div style="padding:28px 14px;background:radial-gradient(circle at top left,rgba(15,118,110,0.12),transparent 38%),#f5f2ea;">
              <div style="max-width:760px;margin:0 auto;">
                <div style="border:1px solid rgba(15,23,42,0.08);border-radius:28px;padding:24px 24px 22px;background:rgba(255,255,255,0.88);backdrop-filter:blur(18px);box-shadow:0 24px 60px rgba(15,23,42,0.10);">
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap;">
                    <div>
                      <div style="font-size:11px;font-weight:800;letter-spacing:0.22em;text-transform:uppercase;color:#64748b;">Broker Freund</div>
                      <div style="margin-top:6px;font-size:28px;line-height:1.15;font-weight:800;color:#0f172a;">{escape(subject)}</div>
                      <div style="margin-top:10px;font-size:14px;line-height:1.7;color:#475569;">Signals, macro, portfolio context and actionable setups in the style of your desk.</div>
                    </div>
                    <div style="display:flex;gap:10px;flex-wrap:wrap;">
                      <div style="border:1px solid rgba(15,23,42,0.08);border-radius:999px;padding:8px 12px;background:#f8fafc;font-size:11px;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:#0f766e;">Live journal</div>
                      <div style="border:1px solid rgba(15,23,42,0.08);border-radius:999px;padding:8px 12px;background:#ffffff;font-size:11px;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:#475569;">{escape(generated_at)}</div>
                    </div>
                  </div>
                </div>
                <div style="margin-top:18px;display:grid;gap:14px;">
                  {cards_html}
                </div>
              </div>
            </div>
          </body>
        </html>
        """

    def _is_section_heading(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.endswith(":") and "|" not in stripped and len(stripped) < 50

    def _tone_for_event(self, event: Dict[str, Any]) -> Dict[str, str]:
        category = (event.get("category") or "").lower()
        conviction = float(event.get("conviction_score") or 0)
        line = (event.get("line") or "").lower()

        if "hedge" in line or "risk" in line or "avoid" in line:
            return {
                "label": "Risk",
                "background": "linear-gradient(180deg,rgba(254,242,242,0.96),rgba(255,255,255,0.96))",
                "pill_bg": "rgba(239,68,68,0.12)",
                "pill_fg": "#dc2626",
            }
        if conviction >= 85 or "buy" in line or category in {"a_setup", "ticker"}:
            return {
                "label": "Setup",
                "background": "linear-gradient(180deg,rgba(236,253,245,0.96),rgba(255,255,255,0.96))",
                "pill_bg": "rgba(16,185,129,0.12)",
                "pill_fg": "#047857",
            }
        if category in {"morning_brief", "scheduled_brief", "session_list"}:
            return {
                "label": "Brief",
                "background": "linear-gradient(180deg,rgba(239,246,255,0.96),rgba(255,255,255,0.96))",
                "pill_bg": "rgba(14,165,233,0.12)",
                "pill_fg": "#0369a1",
            }
        return {
            "label": "Note",
            "background": "linear-gradient(180deg,rgba(248,250,252,0.98),rgba(255,255,255,0.96))",
            "pill_bg": "rgba(15,23,42,0.08)",
            "pill_fg": "#475569",
        }

    def _telegram_prefix_for_event(self, event: Dict[str, Any]) -> str:
        line = (event.get("line") or "").lower()
        category = (event.get("category") or "").lower()
        conviction = float(event.get("conviction_score") or 0)
        if "risk" in line or "avoid" in line or "hedge" in line:
            return "[RISK]"
        if conviction >= 85 or category in {"a_setup", "ticker"}:
            return "[SETUP]"
        if category in {"scheduled_brief", "morning_brief", "session_list"}:
            return "[BRIEF]"
        if category == "daily_overview":
            return "[UEBERSICHT]"
        return "[INFO]"

    def _escape_markdown(self, text: str) -> str:
        escaped = text or ""
        for char in ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]:
            escaped = escaped.replace(char, f"\\{char}")
        return escaped

    def _build_daily_brief_lines(self, snapshot: Dict[str, Any]) -> List[str]:
        ticker_signals = snapshot.get("ticker_signals", [])
        politician_signals = snapshot.get("politician_signals", [])
        lines = [
            f"Watchlist: {len(snapshot.get('items', []))} aktive Beobachtungen",
            f"Ticker-Radar: {sum(len(item.get('events', [])) for item in ticker_signals)} juengste Insider-Events",
            f"Congress-Watch: {sum(len(item.get('trades', [])) for item in politician_signals)} juengste PTR-Trades",
            "",
            "Top Ticker-Signale:",
        ]

        top_ticker_events = []
        for signal in ticker_signals:
            for event in signal.get("events", [])[:2]:
                top_ticker_events.append(
                    f"{signal.get('ticker')}: {event.get('action')} by {event.get('owner_name')} "
                    f"on {event.get('trade_date')}"
                )
        if top_ticker_events:
            lines.extend(f"- {line}" for line in top_ticker_events[:5])
        else:
            lines.append("- Keine Ticker-Events im Brief.")

        lines.extend(["", "Top Congress-Signale:"])
        top_political_events = []
        for signal in politician_signals:
            for trade in signal.get("trades", [])[:2]:
                top_political_events.append(
                    f"{signal.get('name')}: {trade.get('action')} {trade.get('ticker') or trade.get('asset')} "
                    f"on {trade.get('trade_date')}"
                )
        if top_political_events:
            lines.extend(f"- {line}" for line in top_political_events[:5])
        else:
            lines.append("- Keine Congress-Events im Brief.")

        return lines

    def _validate_config(self, config: EmailAlertConfig) -> None:
        telegram_ready = bool(
            config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id
        )
        if telegram_ready:
            return
        raise ValueError(
            "Missing Telegram notification config: set TELEGRAM_ALERTS_ENABLED=true, TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )

    def _normalize_telegram_bot_token(self, token: str) -> str:
        token = (token or "").strip()
        if token.lower().startswith("bot") and ":" in token[3:]:
            return token[3:].strip()
        return token

    def _validate_telegram_config(self, config: EmailAlertConfig) -> None:
        missing = []
        if not config.telegram_enabled:
            missing.append("TELEGRAM_ALERTS_ENABLED=true")
        if not config.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not config.telegram_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            raise ValueError(
                "Missing Telegram notification config: set "
                + ", ".join(missing)
                + " in Railway environment variables."
            )
        if not re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", config.telegram_bot_token):
            raise ValueError(
                "Invalid TELEGRAM_BOT_TOKEN format. Use the raw BotFather token, for example "
                "123456789:ABCDEF..., not https://api.telegram.org/bot.../sendMessage."
            )
