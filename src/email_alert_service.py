"""
Email alert service for signal watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import asyncio
from html import escape
import os
import re
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
        push_service: "Any | None" = None,
    ) -> None:
        self.portfolio_manager = portfolio_manager
        self.public_signal_service = public_signal_service
        self.morning_brief_service = morning_brief_service or MorningBriefService()
        self.session_list_service = session_list_service or SessionListService()
        self.signal_score_service = signal_score_service or SignalScoreService()
        self.push_service = push_service

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
                "delivery_grace_minutes": int(os.getenv("BRIEF_DELIVERY_GRACE_MINUTES", "120")),
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
        brief = dict(self.morning_brief_service.get_brief(snapshot))
        try:
            brief["trading_edge"] = self.morning_brief_service.get_trading_edge(snapshot)
        except Exception:
            brief["trading_edge"] = {}
        try:
            self._send_telegram_rich_brief(config, brief, session)
        except Exception as e:
            raise RuntimeError(f"Telegram send failed: {e}") from e
        return {"status": "ok", "message": f"Session brief '{session}' sent to Telegram."}

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
                "session_label": "global",
                "build_events": lambda: self._build_open_brief_events("global"),
                "is_brief": True,
            },
            {
                "job_key": "open-brief:europe",
                "scheduled_time": os.getenv("EUROPE_OPEN_BRIEF_TIME", "08:40"),
                "subject": "Europe Open Brief: Market opening setup",
                "title": "Europe Open Brief",
                "category": "open_brief",
                "session_label": "europe",
                "build_events": lambda: self._build_open_brief_events("europe"),
                "is_brief": True,
            },
            {
                "job_key": "midday-brief",
                "scheduled_time": os.getenv("MIDDAY_BRIEF_TIME", "12:30"),
                "subject": "Midday Update: What changed since the open",
                "title": "Midday Update",
                "category": "scheduled_brief",
                "session_label": "midday",
                "build_events": self._build_midday_update_events,
                "is_brief": True,
            },
            {
                "job_key": "open-brief:usa",
                "scheduled_time": os.getenv("US_OPEN_BRIEF_TIME", "15:10"),
                "subject": "US Open Brief: Market opening setup",
                "title": "US Open Brief",
                "category": "open_brief",
                "session_label": "usa",
                "build_events": lambda: self._build_open_brief_events("usa"),
                "is_brief": True,
            },
            {
                "job_key": "close-brief:europe",
                "scheduled_time": os.getenv("EUROPE_CLOSE_BRIEF_TIME", "17:30"),
                "subject": "Europe Close Brief: Session wrap + US watch",
                "title": "Europe Close Brief",
                "category": "close_brief",
                "session_label": "europe_close",
                "build_events": lambda: self._build_close_brief_events("europe"),
                "is_brief": True,
            },
            {
                "job_key": "close-brief:usa",
                "scheduled_time": os.getenv("US_CLOSE_BRIEF_TIME", "22:15"),
                "subject": "US Close Brief: Session wrap + overnight watch",
                "title": "US Close Brief",
                "category": "close_brief",
                "session_label": "usa_close",
                "build_events": lambda: self._build_close_brief_events("usa"),
                "is_brief": True,
            },
            {
                "job_key": "close-recap",
                "scheduled_time": os.getenv("CLOSE_RECAP_TIME", "21:45"),
                "subject": "End of Day Recap: Stocks, macro and next risks",
                "title": "End of Day Recap",
                "category": "scheduled_brief",
                "session_label": "close",
                "build_events": self._build_close_recap_events,
                "is_brief": True,
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

            # For scheduled briefs: send rich multi-part Telegram message + email
            if job.get("is_brief"):
                items = self.portfolio_manager.get_signal_watch_items()
                snapshot = self.public_signal_service.build_watchlist_snapshot(items)
                brief = self.morning_brief_service.get_brief(snapshot)
                # Trading edge is decoupled from the cached brief — fetch
                # fresh here so scheduled briefs always include MSG 5.
                try:
                    brief = dict(brief)
                    brief["trading_edge"] = self.morning_brief_service.get_trading_edge(snapshot)
                except Exception:
                    pass
                try:
                    self._send_telegram_rich_brief(config, brief, str(job["session_label"]))
                except Exception as exc:
                    print(f"Scheduled Telegram brief failed for {job['job_key']}: {exc}")
                # Browser push notification
                if self.push_service:
                    try:
                        headline = brief.get("headline") or brief.get("opening_bias") or "Neues Briefing"
                        self.push_service.notify_brief(str(job["session_label"]), headline)
                    except Exception as exc:
                        print(f"Scheduled push brief failed for {job['job_key']}: {exc}")
                # Still send email via the normal path (events → HTML email)
                self._send_notifications(config, events, subject=str(job["subject"]), telegram=False)
            else:
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
        grace_minutes = max(loop_minutes, int(os.getenv("BRIEF_DELIVERY_GRACE_MINUTES", "120")))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta_minutes = (now - scheduled).total_seconds() / 60
        return 0 <= delta_minutes < grace_minutes

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
        config: "EmailAlertConfig",
        events: List[Dict[str, Any]],
        subject: str,
        telegram: bool = True,
    ) -> None:
        errors: List[str] = []
        delivered = False

        try:
            delivered = self._send_email(config, events, subject) or delivered
        except Exception as exc:
            errors.append(f"email failed: {exc}")

        if telegram:
            try:
                delivered = self._send_telegram(config, events, subject) or delivered
            except Exception as exc:
                errors.append(f"telegram failed: {exc}")

        if not delivered and errors:
            raise RuntimeError("; ".join(errors))

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
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                    "disable_web_page_preview": disable_preview,
                },
                timeout=20,
            ).raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 404:
                raise RuntimeError(
                    "Telegram rejected the bot token with 404. Check TELEGRAM_BOT_TOKEN in Railway; "
                    "use the raw token from BotFather, for example 123456:ABC..., not the API URL."
                ) from exc
            if status == 400:
                raise RuntimeError(
                    "Telegram rejected the message with 400. Check TELEGRAM_CHAT_ID and whether the bot "
                    "has been started in that chat."
                ) from exc
            if status == 403:
                raise RuntimeError(
                    "Telegram rejected the bot with 403. The bot is not allowed to send to this chat. "
                    "Open Telegram, start the bot with /start, and if this is a group/channel add the bot "
                    "as a member/admin; then verify TELEGRAM_CHAT_ID points to that chat."
                ) from exc
            raise

    def _tg_esc(self, text: str) -> str:
        """Escape text for Telegram HTML mode."""
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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

        # Merge top_news + google_news_extra, deduplicate
        seen_titles: set = set()
        all_news: List[Dict[str, Any]] = []
        for item in brief.get("top_news", []) + brief.get("google_news_extra", []):
            t = item.get("title") or ""
            if t and t not in seen_titles:
                seen_titles.add(t)
                all_news.append(item)
        for item in all_news[:10]:
            title = self._tg_esc(item.get("title") or "")
            link = (item.get("link") or "").strip()
            publisher = self._tg_esc(item.get("publisher") or "")
            ticker = (item.get("ticker") or "").strip()
            tag = f"<code>{self._tg_esc(ticker)}</code> " if ticker else ""
            line = f"• {tag}<a href=\"{link}\">{title}</a>" if link else f"• {tag}{title}"
            if publisher:
                line += f" <i>({publisher})</i>"
            lines2.append(line)

        if not all_news:
            lines2.append("<i>Keine aktuellen Meldungen.</i>")

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
        earnings = brief.get("broad_earnings") or brief.get("earnings_calendar", [])
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
        if reddit:
            lines3.append("🤖 <b>Reddit Hot Posts</b>")
            for post in reddit[:5]:
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
            for item in stocktwits:
                t = self._tg_esc(item.get("ticker") or "")
                bull = item.get("bull_ratio") or 0
                label = item.get("sentiment_label") or "neutral"
                icon_s = "🐂" if label == "bullish" else "🐻" if label == "bearish" else "➡️"
                msgs = item.get("message_count") or 0
                bar_filled = round(bull / 10)
                bar = "█" * bar_filled + "░" * (10 - bar_filled)
                lines3.append(f"{icon_s} <code>{t}</code> {bar} {bull}% bullish · {msgs} msgs")
                # Show top message
                tops = item.get("top_messages") or []
                if tops:
                    top_txt = self._tg_esc((tops[0].get("text") or "")[:100])
                    lines3.append(f'   <i>"{top_txt}"</i>')

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
        action_board = brief.get("action_board", [])
        if action_board:
            lines4.append("⚡ <b>Action Board</b>")
            for item in action_board[:5]:
                ticker = self._tg_esc(item.get("ticker") or "Macro")
                setup = self._tg_esc(item.get("setup") or "watch")
                trigger = self._tg_esc(item.get("trigger") or "")
                tag = f"<code>{ticker}</code> " if ticker != "Macro" else ""
                lines4.append(f"• {tag}<b>{setup}</b> — {trigger}")

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
            if analyst:
                lines5.append("")
                lines5.append("🏦 <b>Analyst Actions (14d)</b>")
                for a in analyst[:5]:
                    tk = a["ticker"]
                    latest = a["actions"][-3:]
                    for act in latest:
                        firm = self._tg_esc(act.get("firm", ""))[:28]
                        to = self._tg_esc(act.get("to", ""))
                        frm = self._tg_esc(act.get("from", ""))
                        action = self._tg_esc(act.get("action", ""))
                        lines5.append(f"• <code>{tk}</code> {firm}: {frm} → <b>{to}</b> ({action})")

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
        email_ready = bool(config.smtp_host and config.smtp_from and config.smtp_to)
        telegram_ready = bool(
            config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id
        )
        if email_ready or telegram_ready:
            return
        raise ValueError(
            "Missing notification config: set SMTP_* / ALERT_EMAIL_TO or Telegram bot settings."
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
