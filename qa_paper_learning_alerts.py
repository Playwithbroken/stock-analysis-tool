from __future__ import annotations

from src.email_alert_service import EmailAlertService


def test_paper_learning_alert_extraction() -> None:
    service = EmailAlertService.__new__(EmailAlertService)
    learning = {
        "setup_adjustments": {
            "insider_follow": {
                "setup_type": "insider_follow",
                "decisive": 8,
                "hit_rate": 0.0,
                "score_delta": -14,
                "block": True,
                "reason": "Setup insider_follow is blocked by paper outcomes.",
            }
        },
        "option_readiness": {
            "decisive": 10,
            "hit_rate": 40.0,
            "real_money_ready": False,
            "reason": "Options remain paper-only until 20 decisive checks and >=55% hit rate.",
        },
    }
    events = service._extract_paper_learning_events(learning, set())
    assert len(events) == 2
    assert events[0]["category"] == "paper_learning"
    assert "BLOCK" in events[0]["line"]
    assert "CALL/PUT" in events[1]["line"]

    sent = {event["event_key"] for event in events}
    assert service._extract_paper_learning_events(learning, sent) == []


if __name__ == "__main__":
    test_paper_learning_alert_extraction()
    print("qa_paper_learning_alerts: ok")
