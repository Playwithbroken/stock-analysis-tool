from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.email_alert_service import EmailAlertConfig, EmailAlertService


ROOT = Path(__file__).resolve().parent


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

    def list_paper_trades(self, limit=1000):
        today = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
        return [
            {
                "id": "open-1",
                "ticker": "MSFT",
                "status": "open",
                "entry_price": 100,
                "quantity": 2,
                "direction": "long",
                "trade_ticket": {},
            },
            {
                "id": "closed-1",
                "ticker": "SAP.DE",
                "status": "closed",
                "entry_price": 100,
                "closed_price": 105,
                "quantity": 2,
                "contract_multiplier": 1,
                "leverage": 1,
                "direction": "long",
                "closed_at": f"{today}T18:00:00",
                "trade_ticket": {},
            },
        ]

    def list_paper_trade_outcomes(self, limit=2000):
        return [
            {"status": "evaluated", "result": "hit"},
            {"status": "evaluated", "result": "miss"},
            {"status": "pending", "result": None},
        ]

    def get_portfolios(self):
        return [{"id": "p1", "holdings": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]}]


def config(enabled=True):
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
        daily_overview_enabled=enabled,
    )


def build_service(enabled=True):
    service = EmailAlertService.__new__(EmailAlertService)
    service.portfolio_manager = MemoryManager()
    service.get_config = lambda: config(enabled)
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


def test_disabled_is_explicit():
    service = build_service(False)
    result = service.send_scheduled_daily_overview()
    require(result["status"] == "disabled", "overview must be opt-in")
    require(not service.deliveries and not service.portfolio_manager.sent, "disabled overview must not send")


def test_success_is_local_deduplicated_summary():
    service = build_service(True)
    first = service.send_scheduled_daily_overview(force=True)
    second = service.send_scheduled_daily_overview(force=True)
    require(first["status"] == "sent", "forced overview should send")
    require(second["status"] == "deduplicated", "same daily overview must not repeat")
    require(len(service.deliveries) == 1, "duplicate must not reach Telegram")
    lines = "\n".join(item["line"] for item in service.deliveries[0]["events"])
    require("1 offen" in lines and "heute 1 geschlossen" in lines, "paper lifecycle must be summarized")
    require("realisiert +10.00" in lines, "daily realized P&L must be calculated")
    require("2 entscheidend" in lines and "1 offen" in lines, "learning evidence must be summarized")
    require("sofort und unabhaengig" in lines, "summary must state immediate alert independence")


def test_failed_delivery_remains_retryable():
    service = build_service(True)
    attempts = {"count": 0}

    def fail_once(current, events, subject):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("Telegram unavailable")
        return True

    service._send_notifications = fail_once
    first = service.send_scheduled_daily_overview(force=True)
    require(first["status"] == "failed", "failed transport must be visible")
    require(not service.portfolio_manager.sent, "failure must not consume dedupe key")
    second = service.send_scheduled_daily_overview(force=True)
    require(second["status"] == "sent" and attempts["count"] == 2, "failed delivery must retry")


def test_scheduler_priority_and_surface_contract():
    api_source = (ROOT / "api.py").read_text(encoding="utf-8")
    signal = api_source.index('"Signal alert scan"')
    critical = api_source.index('"Critical market alert scan"')
    overview = api_source.index('"Daily overview delivery"')
    briefs = api_source.index('"Scheduled brief delivery"')
    require(signal < critical < overview < briefs, "immediate event scans must run before summaries")
    ui_source = (ROOT / "frontend/src/components/NotificationSettingsPanel.tsx").read_text(encoding="utf-8")
    require("Telegram-Tagesübersicht" in ui_source, "settings must show the optional schedule")
    env_source = (ROOT / ".env.example").read_text(encoding="utf-8")
    require("DAILY_OVERVIEW_ENABLED=false" in env_source, "feature must default to disabled")


if __name__ == "__main__":
    test_disabled_is_explicit()
    test_success_is_local_deduplicated_summary()
    test_failed_delivery_remains_retryable()
    test_scheduler_priority_and_surface_contract()
    print("daily overview scheduler QA passed")
