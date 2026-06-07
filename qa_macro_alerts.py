from src.email_alert_service import EmailAlertService


class FakePortfolioManager:
    def __init__(self):
        self.settings = {}

    def get_app_setting(self, key, default=""):
        return self.settings.get(key, default)

    def set_app_setting(self, key, value):
        self.settings[key] = value

    def get_signal_watch_items(self):
        return []

    def get_portfolios(self):
        return []


def build_service():
    return EmailAlertService(
        portfolio_manager=FakePortfolioManager(),
        public_signal_service=object(),
        morning_brief_service=object(),
    )


def test_macro_alert_gate():
    service = build_service()
    event = {
        "title": "Ukraine conflict escalation hits energy and European futures",
        "event_type": "conflict",
        "impact": "high",
        "geo": {"country": "Ukraine"},
        "event_intelligence": {
            "impact_score": 88,
            "affected_assets": ["GLD", "XLE", "DAX"],
            "trigger": "Confirmed official escalation and follow-through after Europe open.",
            "invalidation": "Invalid if officials deny escalation and futures reverse.",
            "action": "hedge",
        },
        "publisher": "Reuters",
    }
    normalized = service._normalize_macro_alert_event(event, 82)
    assert normalized is not None
    assert normalized["category"] == "macro_alert"
    assert normalized["event_type"] == "Conflict"
    assert normalized["country"] == "Ukraine"
    assert normalized["impact_score"] == 88
    assert "GLD" in normalized["affected_assets"]
    assert service._macro_alert_can_send(normalized) is True
    service._record_macro_alert_delivery([normalized])
    assert service._macro_alert_can_send(normalized) is False

    upgraded = dict(normalized)
    upgraded["impact_score"] = 97
    upgraded["severity"] = "critical"
    assert service._macro_alert_can_send(upgraded) is True


def test_incomplete_macro_alert_is_blocked():
    service = build_service()
    event = {
        "title": "Unconfirmed market rumour circulates online",
        "impact": "high",
        "region": "global",
    }
    assert service._normalize_macro_alert_event(event, 82) is None


if __name__ == "__main__":
    test_macro_alert_gate()
    test_incomplete_macro_alert_is_blocked()
    print("macro alert QA ok")
