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
        "learning_summary": {
            "review_focus": [
                "Stop using blocked setup types: insider_follow.",
                "Main error to fix next: weak_follow_through.",
            ],
            "manual_review_checklist": [
                "Thesis is written before entry.",
                "Trigger, stop, target and invalidation are clear.",
            ],
        },
    }
    events = service._extract_paper_learning_events(learning, set())
    assert len(events) == 2
    assert events[0]["category"] == "paper_learning"
    assert events[0]["severity"] == "block"
    assert events[0]["action"] == "Block setup"
    assert events[0]["review_focus"]
    assert "BLOCK" in events[0]["line"]
    assert "CALL/PUT" in events[1]["line"]

    rendered = service._render_telegram_paper_learning_alert(events[0])
    assert "[LEARNING BLOCK]" in rendered
    assert "Manual money gate" in rendered
    assert "Critical check" in rendered
    assert "weak_follow_through" in rendered

    sent = {event["event_key"] for event in events}
    assert service._extract_paper_learning_events(learning, sent) == []


def test_paper_trade_telegram_money_formatting() -> None:
    service = EmailAlertService.__new__(EmailAlertService)

    opened = service._render_telegram_paper_trade_opened_alert(
        {
            "ticker": "AAPL",
            "direction": "long",
            "asset_class": "equity",
            "setup_type": "breakout",
            "entry_price": 201.125,
            "stop_price": 194.0,
            "target_price": 218.5,
            "quantity": 61.38,
            "invested_value": 12345.67,
            "current_value": 12390.12,
            "result_value_delta": 44.45,
            "result_label": "winner",
            "suggested_max_loss_value": 450.0,
            "risk_reward": 2.4,
            "confidence_score": 91,
            "trigger": "Breakout confirmed with volume.",
            "invalidation": "Close if breakout fails.",
        }
    )
    assert "investiert 12.345,67 EUR" in opened
    assert "aktueller Wert 12.390,12 EUR" in opened
    assert "Offenes Ergebnis:</b> +44,45 EUR" in opened
    assert "Max. Demo-Verlust:</b> 450,00 EUR" in opened

    closed = service._render_telegram_paper_trade_closed_alert(
        {
            "ticker": "AAPL",
            "direction": "long",
            "setup_type": "breakout",
            "entry_price": 201.125,
            "closed_price": 218.5,
            "invested_value": 12345.67,
            "final_value": 13412.33,
            "realized_pnl_value": 1066.66,
            "realized_pnl_pct": 8.64,
            "result_label": "winner",
            "exit_reason": "target_or_profit_taken",
            "lessons_learned": "Volume confirmation mattered.",
            "risk_reward": 2.4,
        }
    )
    assert "investiert 12.345,67 EUR" in closed
    assert "final 13.412,33 EUR" in closed
    assert "Result:</b> +1.066,66 EUR | +8.64%" in closed
    assert "target_or_profit_taken" in closed


if __name__ == "__main__":
    test_paper_learning_alert_extraction()
    test_paper_trade_telegram_money_formatting()
    print("qa_paper_learning_alerts: ok")
