"""
Email alert service for signal watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import asyncio
import os
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from typing import Any, Dict, List
import requests

from src.public_signal_service import PublicSignalService
from src.session_list_service import SessionListService
from src.signal_score_service import SignalScoreService
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
        session_list_service: SessionListService | None = None,
        signal_score_service: SignalScoreService | None = None,
    ) -> None:
        self.portfolio_manager = portfolio_manager
        self.public_signal_service = public_signal_service
        self.morning_brief_service = morning_brief_service or MorningBriefService()
        self.session_list_service = session_list_service or SessionListService()
        self.signal_score_service = signal_score_service or SignalScoreService()

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
                "weekdays": os.getenv("BRIEF_SCHEDULE_WEEKDAYS", "mon,tue,wed,thu,fri"),
                "morning": os.getenv("MORNING_BRIEF_TIME", "07:15"),
                "europe_open": os.getenv("EUROPE_OPEN_BRIEF_TIME", "08:40"),
                "midday": os.getenv("MIDDAY_BRIEF_TIME", "12:30"),
                "us_open": os.getenv("US_OPEN_BRIEF_TIME", "15:10"),
                "close_recap": os.getenv("CLOSE_RECAP_TIME", "21:45"),
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

    def send_scheduled_open_briefs(self) -> List[Dict[str, Any]]:
        config = self.get_config()
        if not config.enabled:
            return []
        self._validate_config(config)

        now = datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin")))
        if not self._schedule_day_matches(now):
            return []

        sent_keys = self.portfolio_manager.get_sent_signal_event_keys()
        jobs = [
            {
                "job_key": "morning-brief",
                "scheduled_time": os.getenv("MORNING_BRIEF_TIME", "07:15"),
                "subject": "Morning Brief: Global macro, news and setup",
                "title": "Morning Brief",
                "category": "scheduled_brief",
                "build_events": lambda: self._build_open_brief_events("global"),
            },
            {
                "job_key": "open-brief:europe",
                "scheduled_time": os.getenv("EUROPE_OPEN_BRIEF_TIME", "08:40"),
                "subject": "Europe Open Brief: Market opening setup",
                "title": "Europe Open Brief",
                "category": "open_brief",
                "build_events": lambda: self._build_open_brief_events("europe"),
            },
            {
                "job_key": "midday-brief",
                "scheduled_time": os.getenv("MIDDAY_BRIEF_TIME", "12:30"),
                "subject": "Midday Update: What changed since the open",
                "title": "Midday Update",
                "category": "scheduled_brief",
                "build_events": self._build_midday_update_events,
            },
            {
                "job_key": "open-brief:usa",
                "scheduled_time": os.getenv("US_OPEN_BRIEF_TIME", "15:10"),
                "subject": "US Open Brief: Market opening setup",
                "title": "US Open Brief",
                "category": "open_brief",
                "build_events": lambda: self._build_open_brief_events("usa"),
            },
            {
                "job_key": "close-recap",
                "scheduled_time": os.getenv("CLOSE_RECAP_TIME", "21:45"),
                "subject": "End of Day Recap: Stocks, macro and next risks",
                "title": "End of Day Recap",
                "category": "scheduled_brief",
                "build_events": self._build_close_recap_events,
            },
        ]
        results: List[Dict[str, Any]] = []

        for job in jobs:
            event_key = f"{job['job_key']}:{now.date().isoformat()}"
            if event_key in sent_keys:
                continue
            if not self._time_window_matches(now, str(job["scheduled_time"])):
                continue

            events = job["build_events"]()
            self._send_notifications(config, events, subject=str(job["subject"]))
            self.portfolio_manager.mark_signal_events_sent(
                [
                    {
                        "event_key": event_key,
                        "category": str(job["category"]),
                        "title": str(job["title"]),
                    }
                ]
            )
            results.append({"job": job["job_key"], "status": "sent"})

        return results

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

    def _event_priority(self, event: Dict[str, Any]) -> tuple[int, str]:
        category = event.get("category")
        line = (event.get("line") or "").lower()
        if category == "ticker" and " buy " in f" {line} ":
            return (0, line)
        if category == "politician" and " buy " in f" {line} ":
            return (1, line)
        if category == "ticker":
            return (2, line)
        if category == "politician":
            return (3, line)
        return (4, line)

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
            if event.get("conviction_score") is not None:
                lines.append(f"  A-Setup Score: {event['conviction_score']}")
            if event.get("source_label"):
                lines.append(f"  Quelle: {event['source_label']}")
            if event.get("source_url"):
                lines.append(f"  Link: {event['source_url']}")
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
            suffix = f" | score {event['conviction_score']}" if event.get("conviction_score") is not None else ""
            lines.append(f"- {event['line']}{suffix}")
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
