import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.email_alert_service import EmailAlertConfig, EmailAlertService


ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/Berlin")


class MemoryManager:
    def __init__(self):
        self.sent = set()
        self.settings = {}

    def get_sent_signal_event_keys(self):
        return set(self.sent)

    def mark_signal_events_sent(self, events):
        self.sent.update(str(item["event_key"]) for item in events)

    def get_app_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_app_setting(self, key, value):
        self.settings[key] = value


def config():
    return EmailAlertConfig(
        enabled=True,
        smtp_host="",
        smtp_port=0,
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
        smtp_starttls=False,
        telegram_enabled=True,
        telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz",
        telegram_chat_id="123",
        scheduled_briefs_enabled=True,
        daily_overview_enabled=False,
    )


def report_builder():
    base = {
        "status": "ready",
        "equity_change_value": 1_250,
        "return_pct": 0.25,
        "realized_pnl_value": 900,
        "opened_trade_count": 3,
        "closed_trade_count": 2,
        "winner_count": 1,
        "loser_count": 1,
        "best_trade": {"ticker": "AAPL", "pnl_value": 1_200},
        "worst_trade": {"ticker": "JPM", "pnl_value": -300},
    }
    return {
        "equity": 501_250,
        "currency": "EUR",
        "period_performance": {
            "schema": "paper-period-performance.v1",
            "snapshot_count": 30,
            "history_started_at": "2026-01-01T00:00:00+00:00",
            "periods": [
                {**base, "key": "week", "label": "7 Tage"},
                {**base, "key": "month", "label": "Monat"},
                {**base, "key": "year", "label": "Jahr"},
            ],
        },
    }


def build_service():
    service = EmailAlertService.__new__(EmailAlertService)
    service.portfolio_manager = MemoryManager()
    service.get_config = config
    service._validate_config = lambda current: None
    service.deliveries = []

    def deliver(current, events, subject):
        service.deliveries.append({"subject": subject, "events": events})
        return True

    service._send_notifications = deliver
    return service


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main() -> int:
    previous = {key: os.environ.get(key) for key in ["PAPER_PERIOD_UPDATES_ENABLED", "PAPER_PERIOD_UPDATE_TIME"]}
    os.environ["PAPER_PERIOD_UPDATES_ENABLED"] = "true"
    os.environ["PAPER_PERIOD_UPDATE_TIME"] = "22:30"
    try:
        weekly = build_service()
        friday = datetime(2026, 8, 28, 22, 35, tzinfo=TZ)
        first = weekly.send_scheduled_paper_period_update(report_builder, now=friday)
        second = weekly.send_scheduled_paper_period_update(report_builder, now=friday)
        require(first["status"] == "sent" and first["periods"] == ["week"], "Friday must send weekly update")
        require(second["status"] == "deduplicated", "same weekly period must not repeat")
        require(len(weekly.deliveries) == 1, "deduplicated period reached Telegram")
        event = weekly.deliveries[0]["events"][0]
        rendered = weekly._render_telegram_paper_period_update(event)
        require("2026-W35" in rendered and "7 Tage" in rendered, "weekly Telegram identity missing")
        require("W/L 1/1" in rendered and "AAPL" in rendered and "JPM" in rendered, "Telegram evidence detail missing")

        monthly = build_service()
        month_end = datetime(2026, 8, 31, 22, 35, tzinfo=TZ)
        result = monthly.send_scheduled_paper_period_update(report_builder, now=month_end)
        require(result["status"] == "sent" and result["periods"] == ["month"], "month-end update mismatch")

        yearly = build_service()
        year_end = datetime(2026, 12, 31, 22, 35, tzinfo=TZ)
        result = yearly.send_scheduled_paper_period_update(report_builder, now=year_end)
        require(result["status"] == "sent" and result["periods"] == ["month", "year"], "year-end combined update mismatch")

        retry = build_service()
        attempts = {"count": 0}

        def fail_once(current, events, subject):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("Telegram unavailable")
            return True

        retry._send_notifications = fail_once
        failed = retry.send_scheduled_paper_period_update(report_builder, now=friday)
        sent = retry.send_scheduled_paper_period_update(report_builder, now=friday)
        require(failed["status"] == "failed" and sent["status"] == "sent", "failed period update must retry")

        api_source = (ROOT / "api.py").read_text(encoding="utf-8")
        require('"Paper portfolio period update"' in api_source, "period update missing from scheduler")
        require(api_source.index('"Critical market alert scan"') < api_source.index('"Paper portfolio period update"'), "risk scan must precede summary")
        env_source = (ROOT / ".env.example").read_text(encoding="utf-8")
        require("PAPER_PERIOD_UPDATES_ENABLED=true" in env_source, "period update production default missing")
        ui_source = (ROOT / "frontend/src/components/NotificationSettingsPanel.tsx").read_text(encoding="utf-8")
        require("Portfolio-Periodenupdates" in ui_source, "period schedule missing from notification settings")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print("paper period update scheduler QA ok (weekly, monthly, yearly, dedupe, retry, Telegram)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
