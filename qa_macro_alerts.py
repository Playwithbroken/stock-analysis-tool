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


def test_macro_alert_bucket_dedupe_blocks_reworded_headline():
    service = build_service()
    first = {
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
    second = {
        "title": "Europe futures slip as Ukraine escalation keeps energy risk elevated",
        "event_type": "conflict",
        "impact": "high",
        "geo": {"country": "Ukraine"},
        "event_intelligence": {
            "impact_score": 89,
            "affected_assets": ["DAX", "XLE", "GLD"],
            "trigger": "Confirmed official escalation and follow-through after Europe open.",
            "invalidation": "Invalid if officials deny escalation and futures reverse.",
            "action": "hedge",
        },
        "publisher": "Reuters",
    }
    normalized_first = service._normalize_macro_alert_event(first, 82)
    normalized_second = service._normalize_macro_alert_event(second, 82)
    assert normalized_first is not None
    assert normalized_second is not None
    assert normalized_first["macro_identity"] != normalized_second["macro_identity"]
    assert normalized_first["macro_bucket_identity"] == normalized_second["macro_bucket_identity"]
    assert service._macro_alert_can_send(normalized_first) is True
    service._record_macro_alert_delivery([normalized_first])
    assert service._macro_alert_can_send(normalized_second) is False

    score_upgraded = dict(normalized_second)
    score_upgraded["impact_score"] = 97
    score_upgraded["severity"] = "high"
    assert service._macro_alert_can_send(score_upgraded) is True

    severity_upgraded = dict(normalized_second)
    severity_upgraded["impact_score"] = 89
    severity_upgraded["severity"] = "critical"
    assert service._macro_alert_can_send(severity_upgraded) is True


def test_incomplete_macro_alert_is_blocked():
    service = build_service()
    event = {
        "title": "Unconfirmed market rumour circulates online",
        "impact": "high",
        "region": "global",
    }
    assert service._normalize_macro_alert_event(event, 82) is None


def test_immediate_non_macro_alerts_require_combined_quality():
    service = build_service()
    brief = {
        "watchlist_impact": [
            {
                "ticker": "AAPL",
                "summary": "Routine watchlist movement without a high-impact catalyst.",
                "severity": "medium",
                "actionable": True,
            },
            {
                "ticker": "NVDA",
                "summary": "Confirmed guidance cut creates immediate portfolio risk.",
                "severity": "high",
            },
        ],
        "future_stars": [
            {"ticker": "RISK", "score": 95, "quality_gate": "watch"},
            {"ticker": "LOW", "score": 60, "quality_gate": "passed"},
            {"ticker": "GOOD", "score": 80, "quality_gate": "passed"},
        ],
    }
    events = service._extract_critical_market_events(brief, set())
    keys = {event["event_key"] for event in events}
    assert any(key.startswith("critical-watchlist:") and ":NVDA:" in key for key in keys)
    assert not any(":AAPL:" in key for key in keys)
    assert any(key.endswith(":GOOD") for key in keys)
    assert not any(key.endswith(":RISK") or key.endswith(":LOW") for key in keys)


if __name__ == "__main__":
    test_macro_alert_gate()
    test_macro_alert_bucket_dedupe_blocks_reworded_headline()
    test_incomplete_macro_alert_is_blocked()
    test_immediate_non_macro_alerts_require_combined_quality()
    print("macro alert QA ok")
