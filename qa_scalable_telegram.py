from src.email_alert_service import EmailAlertConfig, EmailAlertService
from src.scalable_decision_service import ScalableDecisionService


class MemoryManager:
    def __init__(self):
        self.keys = set()
        self.settings = {}

    def get_sent_signal_event_keys(self):
        return set(self.keys)

    def mark_signal_events_sent(self, events):
        self.keys.update(row["event_key"] for row in events)

    def set_app_setting(self, key, value):
        self.settings[key] = value


def main():
    manager = MemoryManager()
    service = EmailAlertService(manager, object(), object(), object(), object())
    service.get_config = lambda: EmailAlertConfig(
        enabled=True,
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
        smtp_starttls=True,
        telegram_enabled=True,
        telegram_bot_token="dummy_token_placeholder",
        telegram_chat_id="123",
        scheduled_briefs_enabled=True,
    )
    delivered = []
    service._send_notifications = lambda config, events, subject, telegram=True: delivered.append((events, subject)) or True
    report = ScalableDecisionService().build(
        {
            "holdings": [{
                "ticker": "AAA", "name": "AAA", "position_value": 1000,
                "gain_loss_pct": 5, "quote_timestamp_utc": "2026-08-28T10:00:00Z",
                "quote_is_outdated": False,
            }],
            "summary": {"as_of": "2026-08-28T10:00:00Z", "currency": "EUR", "total_value": 1000},
        },
        {"auto_selection": {"selected": [], "exploration": [], "aggressive_exploration": []}},
    )
    first = service.send_scalable_decision_report(report)
    second = service.send_scalable_decision_report(report)
    forced = service.send_scalable_decision_report(report, force=True)
    assert first["status"] == "ok" and first["sent"] == 1
    assert second["status"] == "deduplicated" and second["sent"] == 0
    assert forced["status"] == "ok" and len(delivered) == 2
    assert "Read-only" in delivered[0][0][0]["line"]
    assert "scalable_telegram_decision_state_v1" in manager.settings
    print("qa_scalable_telegram: ok")


if __name__ == "__main__":
    main()
