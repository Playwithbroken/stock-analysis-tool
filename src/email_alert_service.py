"""
Email alert service for signal watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from html import escape
import json
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


DEFAULT_MORNING_BRIEF_TIME = "08:30"
DEFAULT_EUROPE_OPEN_BRIEF_TIME = "08:40"
DEFAULT_MIDDAY_BRIEF_TIME = "12:30"
DEFAULT_US_OPEN_BRIEF_TIME = "15:10"
DEFAULT_EUROPE_CLOSE_BRIEF_TIME = "17:30"
DEFAULT_CLOSE_RECAP_TIME = "21:45"
DEFAULT_US_CLOSE_BRIEF_TIME = "22:15"


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
                "enabled": config.scheduled_briefs_enabled,
                "timezone": os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"),
                "weekdays": os.getenv("BRIEF_SCHEDULE_WEEKDAYS", "mon,tue,wed,thu,fri"),
                "morning": os.getenv("MORNING_BRIEF_TIME", DEFAULT_MORNING_BRIEF_TIME),
                "europe_open": os.getenv("EUROPE_OPEN_BRIEF_TIME", DEFAULT_EUROPE_OPEN_BRIEF_TIME),
                "midday": os.getenv("MIDDAY_BRIEF_TIME", DEFAULT_MIDDAY_BRIEF_TIME),
                "us_open": os.getenv("US_OPEN_BRIEF_TIME", DEFAULT_US_OPEN_BRIEF_TIME),
                "close_recap": os.getenv("CLOSE_RECAP_TIME", DEFAULT_CLOSE_RECAP_TIME),
                "delivery_grace_minutes": self._brief_delivery_grace_minutes(),
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
        try:
            self.morning_brief_service.get_brief_fast(snapshot, True)
        except Exception as exc:
            print(f"Brief warm-cache failed before manual {session}: {exc}")
        brief = dict(self.morning_brief_service.get_brief(snapshot))
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
        max_jobs_per_run = self._safe_int_env("BRIEF_MAX_JOBS_PER_RUN", 3, minimum=1)
        sent_this_run = 0
        due_jobs: List[Dict[str, Any]] = []

        for job in jobs:
            event_key = f"{job['job_key']}:{now.date().isoformat()}"
            if event_key in sent_keys:
                continue
            scheduled_at = self._scheduled_datetime(now, str(job["scheduled_time"]))
            if scheduled_at is None:
                continue
            if include_missed:
                if now < scheduled_at:
                    continue
            elif not self._time_window_matches(now, str(job["scheduled_time"])):
                grace_minutes = self._brief_delivery_grace_minutes()
                if now >= scheduled_at + timedelta(minutes=grace_minutes):
                    missed = {
                        "job": job["job_key"],
                        "status": "missed",
                        "event_key": event_key,
                        "scheduled_at": scheduled_at.isoformat(),
                        "minutes_late": int((now - scheduled_at).total_seconds() / 60),
                        "message": "Brief missed its delivery grace window.",
                    }
                    self._set_brief_job_status(str(job["job_key"]), missed)
                continue
            due_jobs.append(
                {
                    **job,
                    "event_key": event_key,
                    "scheduled_at": scheduled_at,
                    "minutes_late": max(0, int((now - scheduled_at).total_seconds() // 60)),
                }
            )

        # Prioritize the current/recent slot first. This prevents an unsent
        # morning brief from blocking the midday or US-open brief after a restart.
        due_jobs.sort(key=lambda item: (item["minutes_late"], item["scheduled_at"]), reverse=False)

        for job in due_jobs:
            if sent_this_run >= max_jobs_per_run:
                break
            event_key = str(job["event_key"])

            self._validate_config(config)
            self._set_brief_job_status(
                str(job["job_key"]),
                {
                    "status": "running",
                    "event_key": event_key,
                    "scheduled_at": job["scheduled_at"].isoformat(),
                    "started_at": datetime.now(ZoneInfo(os.getenv("BRIEF_SCHEDULE_TIMEZONE", "Europe/Berlin"))).isoformat(),
                    "message": "Building and warming scheduled brief.",
                },
            )
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
                }
                self._set_brief_job_status(str(job["job_key"]), failure)
                results.append(failure)
                continue
            delivered = False
            brief = None

            # For scheduled briefs: send rich multi-part Telegram message + email
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
                    }
                    self._set_brief_job_status(str(job["job_key"]), failure)
                    results.append(failure)
                    continue
                # Trading edge is decoupled from the cached brief — fetch
                # fresh here so scheduled briefs always include MSG 5.
                try:
                    brief = dict(brief)
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
                # Browser push notification
                if self.push_service:
                    try:
                        headline = brief.get("headline") or brief.get("opening_bias") or "Neues Briefing"
                        self.push_service.notify_brief(str(job["session_label"]), headline)
                    except Exception as exc:
                        print(f"Scheduled push brief failed for {job['job_key']}: {exc}")
                # Still send email via the normal path (events → HTML email)
                delivered = (
                    self._send_notifications(config, events, subject=str(job["subject"]), telegram=False)
                    or delivered
                )
                if telegram_required and not telegram_delivered:
                    failure = {
                        "job": job["job_key"],
                        "status": "failed",
                        "event_key": event_key,
                        "scheduled_at": job["scheduled_at"].isoformat(),
                        "minutes_late": job["minutes_late"],
                        "error": telegram_error or "telegram_not_delivered",
                        "email_delivered": delivered,
                        "message": "Telegram delivery failed; job will retry within the grace window.",
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
                    "message": "No notification channel delivered; will retry within the grace window.",
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
                "catchup": job["minutes_late"] > 5,
                "forecasts_recorded": learning.get("recorded", 0),
            }
            self._set_brief_job_status(str(job["job_key"]), success)
            results.append(success)
            sent_this_run += 1

        if not results:
            results.append(
                {
                    "status": "idle",
                    "message": "No scheduled brief is due inside the current grace window.",
                    "checked_at": now.isoformat(),
                }
            )
        self.portfolio_manager.set_app_setting("brief_scheduler_last_result", json.dumps(results[-5:]))
        return results

    def get_brief_job_status(self, job_key: str) -> Dict[str, Any]:
        raw = self.portfolio_manager.get_app_setting(self._brief_status_key(job_key), "{}")
        try:
            payload = json.loads(raw or "{}")
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

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
        elif status == "failed":
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
        grace_minutes = self._brief_delivery_grace_minutes()
        delta_minutes = (now - scheduled).total_seconds() / 60
        return 0 <= delta_minutes < grace_minutes

    def _brief_delivery_grace_minutes(self) -> int:
        loop_minutes = self._safe_int_env("SIGNAL_ALERTS_INTERVAL_MINUTES", 15, minimum=2)
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
                amount = self._tg_esc(str(item.get("amount_range") or "amount n/a"))
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
    ) -> bool:
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

        # Merge top_news + google_news_extra, deduplicate
        seen_titles: set = set()
        all_news: List[Dict[str, Any]] = []
        for item in brief.get("top_news", []) + brief.get("google_news_extra", []):
            t = item.get("title") or ""
            identity = self._brief_line_identity(t)
            if t and identity and identity not in seen_titles:
                seen_titles.add(identity)
                all_news.append(item)
        for item in all_news[:7]:
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

        market_movers = brief.get("market_movers") or {}
        gainers = market_movers.get("gainers") or []
        losers = market_movers.get("losers") or []
        if gainers or losers:
            lines2.extend(["", "<b>Biggest Winners / Losers</b>"])
            for label, rows in (("WIN", gainers[:4]), ("LOSE", losers[:4])):
                for item in rows:
                    ticker = self._tg_esc(item.get("ticker") or "")
                    name = self._tg_esc((item.get("name") or ticker)[:28])
                    chg = item.get("change_1d")
                    if not isinstance(chg, (int, float)):
                        chg = item.get("change_1w")
                    chg_str = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "n/a"
                    price = item.get("price")
                    price_str = f" ${price:,.2f}" if isinstance(price, (int, float)) else ""
                    lines2.append(f"{label} <code>{ticker}</code> {name} {chg_str}{price_str}")

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
                surprise_str = f"{surprise:+.1f}%" if isinstance(surprise, (int, float)) else "n/a"
                reported = item.get("reported_eps")
                estimate = item.get("eps_estimate")
                reported_str = f"{reported:.2f}" if isinstance(reported, (int, float)) else "n/a"
                estimate_str = f"{estimate:.2f}" if isinstance(estimate, (int, float)) else "n/a"
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
                    transition = f"{frm or 'n/a'} → <b>{to}</b>" if to else action
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
