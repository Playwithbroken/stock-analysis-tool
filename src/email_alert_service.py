"""
Email alert service for signal watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from typing import Any, Dict, List
import requests

from src.public_signal_service import PublicSignalService
from src.storage import PortfolioManager
from src.morning_brief_service import MorningBriefService


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


class EmailAlertService:
    def __init__(
        self,
        portfolio_manager: PortfolioManager,
        public_signal_service: PublicSignalService,
        morning_brief_service: MorningBriefService | None = None,
    ) -> None:
        self.portfolio_manager = portfolio_manager
        self.public_signal_service = public_signal_service
        self.morning_brief_service = morning_brief_service or MorningBriefService()

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
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        )

    def get_notification_status(self) -> Dict[str, Any]:
        config = self.get_config()
        return {
            "alerts_enabled": config.enabled,
            "email": {
                "configured": bool(config.smtp_host and config.smtp_from and config.smtp_to),
                "from": config.smtp_from,
                "to": config.smtp_to,
            },
            "telegram": {
                "enabled": config.telegram_enabled,
                "configured": bool(config.telegram_bot_token and config.telegram_chat_id),
            },
            "schedule": {
                "timezone": os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"),
                "europe_open": os.getenv("EUROPE_OPEN_BRIEF_TIME", "08:40"),
                "us_open": os.getenv("US_OPEN_BRIEF_TIME", "15:10"),
            },
        }

    def check_and_send_alerts(self, force: bool = False) -> Dict[str, Any]:
        config = self.get_config()
        if not force and not config.enabled:
            return {"status": "disabled", "message": "Signal alerts are disabled."}

        self._validate_config(config)
        items = self.portfolio_manager.get_signal_watch_items()
        snapshot = self.public_signal_service.build_watchlist_snapshot(items)
        new_events = self._extract_new_events(snapshot)

        if not new_events:
            return {"status": "ok", "sent": 0, "message": "No new events."}

        self._send_notifications(
            config,
            new_events,
            subject=f"Signal Alert: {len(new_events)} neue Watchlist-Signale",
        )
        self.portfolio_manager.mark_signal_events_sent(new_events)
        return {"status": "ok", "sent": len(new_events), "message": "Alert email sent."}

    def send_test_email(self) -> Dict[str, Any]:
        config = self.get_config()
        self._validate_config(config)
        sample_event = {
            "event_key": f"test:{datetime.now().isoformat()}",
            "category": "test",
            "title": "Test Alert",
            "line": "Das ist eine Test-Mail fuer dein Signal-Alert-System.",
            "source_url": "",
        }
        self._send_notifications(config, [sample_event], subject="Test Alert: Mailversand aktiv")
        return {"status": "ok", "message": "Test email sent."}

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

    def send_scheduled_open_briefs(self) -> List[Dict[str, Any]]:
        config = self.get_config()
        if not config.enabled:
            return []
        self._validate_config(config)

        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        jobs = [
            ("europe", os.getenv("EUROPE_OPEN_BRIEF_TIME", "08:40")),
            ("usa", os.getenv("US_OPEN_BRIEF_TIME", "15:10")),
        ]
        results: List[Dict[str, Any]] = []

        for session, scheduled_time in jobs:
            event_key = f"open-brief:{session}:{now.date().isoformat()}"
            if event_key in sent_keys:
                continue
            if not self._time_window_matches(now, scheduled_time):
                continue

            events = self._build_open_brief_events(session)
            self._send_notifications(
                config,
                events,
                subject=f"{session.title()} Open Brief: Market opening setup",
            )
            self.portfolio_manager.mark_signal_events_sent(
                [
                    {
                        "event_key": event_key,
                        "category": "open_brief",
                        "title": f"{session.title()} Open Brief",
                    }
                ]
            )
            results.append({"session": session, "status": "sent"})

        return results

    def _time_window_matches(self, now: datetime, scheduled_hhmm: str) -> bool:
        try:
            hour, minute = [int(part) for part in scheduled_hhmm.split(":", 1)]
        except Exception:
            return False
        loop_minutes = max(2, int(os.getenv("SIGNAL_ALERTS_INTERVAL_MINUTES", "15")))
        return now.hour == hour and minute <= now.minute < minute + loop_minutes

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

    def _extract_new_events(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        new_events: List[Dict[str, Any]] = []

        for signal in snapshot.get("ticker_signals", []):
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
                    f"on {event.get('trade_date')} • filed {event.get('filed_date')} • "
                    f"{event.get('shares')} shares"
                )
                if event.get("value_label"):
                    line += f" • {event.get('value_label')}"
                new_events.append(
                    {
                        "event_key": event_key,
                        "category": "ticker",
                        "title": signal.get("ticker") or "Ticker Signal",
                        "line": line,
                        "source_url": event.get("source_url") or signal.get("source_url") or "",
                    }
                )

        for signal in snapshot.get("politician_signals", []):
            for trade in signal.get("trades", []):
                event_key = (
                    f"politician:{signal.get('name')}:{trade.get('ticker') or trade.get('asset')}:"
                    f"{trade.get('trade_date')}:{trade.get('action')}:{trade.get('amount_range')}"
                )
                if event_key in sent_keys:
                    continue
                action = (trade.get("action") or "").upper()
                line = (
                    f"{signal.get('name')}: {action} {trade.get('ticker') or trade.get('asset')} "
                    f"on {trade.get('trade_date')} • filed {trade.get('notification_date')} • "
                    f"{trade.get('amount_range')}"
                )
                new_events.append(
                    {
                        "event_key": event_key,
                        "category": "politician",
                        "title": signal.get("name") or "Congress Signal",
                        "line": line,
                        "source_url": trade.get("source_url") or signal.get("source_url") or "",
                    }
                )

        return new_events

    def _send_notifications(
        self,
        config: EmailAlertConfig,
        events: List[Dict[str, Any]],
        subject: str,
    ) -> None:
        self._send_email(config, events, subject)
        self._send_telegram(config, events, subject)

    def _send_email(
        self,
        config: EmailAlertConfig,
        events: List[Dict[str, Any]],
        subject: str,
    ) -> None:
        if not (config.smtp_host and config.smtp_from and config.smtp_to):
            return
        msg = EmailMessage()
        msg["From"] = config.smtp_from
        msg["To"] = config.smtp_to
        msg["Subject"] = subject

        lines = ["",]
        for event in events:
            lines.append(f"- {event['line']}")
            if event.get("source_url"):
                lines.append(f"  Quelle: {event['source_url']}")
        lines.extend(["", f"Erstellt am {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
        msg.set_content("\n".join(lines))

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
            if config.smtp_starttls:
                server.starttls()
            if config.smtp_user:
                server.login(config.smtp_user, config.smtp_password)
            server.send_message(msg)

    def _send_telegram(
        self,
        config: EmailAlertConfig,
        events: List[Dict[str, Any]],
        subject: str,
    ) -> None:
        if not (
            config.telegram_enabled
            and config.telegram_bot_token
            and config.telegram_chat_id
        ):
            return

        lines = [f"*{subject}*", ""]
        for event in events[:20]:
            lines.append(f"• {event['line']}")
        text = "\n".join(lines)

        response = requests.post(
            f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
            json={
                "chat_id": config.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()

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
        email_ready = bool(config.smtp_host and config.smtp_from and config.smtp_to)
        telegram_ready = bool(
            config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id
        )
        if email_ready or telegram_ready:
            return
        raise ValueError(
            "Missing notification config: set SMTP_* / ALERT_EMAIL_TO or Telegram bot settings."
        )
