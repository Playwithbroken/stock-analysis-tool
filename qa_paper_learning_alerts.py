from __future__ import annotations

import os

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
                "reason": "Setup insider_follow wird durch Paper-Ergebnisse geblockt.",
            }
        },
        "option_readiness": {
            "decisive": 10,
            "hit_rate": 40.0,
            "real_money_ready": False,
            "reason": "Optionen bleiben nur Paper, bis 20 klare Prüfungen und >=55% Trefferquote erreicht sind.",
        },
        "learning_summary": {
            "review_focus": [
                "Geblockte Setup-Typen nicht mehr nutzen: insider_follow.",
                "Nächster Hauptfehler zum Verbessern: weak_follow_through.",
            ],
            "manual_review_checklist": [
                "These wurde vor Einstieg schriftlich festgehalten.",
                "Trigger, Stop, Ziel und Invalidierung sind klar.",
            ],
        },
    }
    events = service._extract_paper_learning_events(learning, set())
    assert len(events) == 2
    assert events[0]["category"] == "paper_learning"
    assert events[0]["severity"] == "block"
    assert events[0]["action"] == "Setup blockieren"
    assert events[0]["review_focus"]
    assert "BLOCK" in events[0]["line"]
    assert "CALL/PUT-Lernen" in events[1]["line"]

    rendered = service._render_telegram_paper_learning_alert(events[0])
    assert "[LEARNING BLOCK]" in rendered
    assert "Manuelles Echtgeld-Gate" in rendered
    assert "Kritischer Check" in rendered
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
            "opened_at": "2026-07-11T12:00:00+00:00",
            "entry_price": 201.125,
            "stop_price": 194.0,
            "target_price": 218.5,
            "quantity": 61.38,
            "invested_value": 12345.67,
            "current_value": 12390.12,
            "result_value_delta": 44.45,
            "result_label": "winner",
            "suggested_max_loss_value": 450.0,
            "account_equity": 501250.5,
            "account_cash_available": 488904.83,
            "account_open_exposure": 12345.67,
            "account_net_pnl_value": 1250.5,
            "account_net_pnl_pct": 0.25,
            "risk_reward": 2.4,
            "confidence_score": 91,
            "trigger": "Breakout mit Volumen bestätigt.",
            "invalidation": "Schließen, wenn Breakout scheitert.",
            "trade_ticket": {
                "status": "paper_ready",
                "horizon": "days-weeks",
                "source_label": "official filing",
                "data_as_of": "2026-07-11T12:00:00",
                "validation": {"warnings": ["manual_market_check"]},
            },
        }
    )
    assert "investiert 12.345,67 EUR" in opened
    assert "Eröffnet:</b> 11.07.2026, 14:00 CEST" in opened
    assert "aktueller Wert 12.390,12 EUR" in opened
    assert "Offenes Ergebnis:</b> +44,45 EUR" in opened
    assert "Max. Demo-Verlust:</b> 450,00 EUR" in opened
    assert "Ticket:</b> paper_ready" in opened
    assert "Horizont:</b> days-weeks" in opened
    assert "official filing" in opened
    assert "manual_market_check" in opened
    assert "Demo-Konto danach:</b> Equity 501.250,50 EUR" in opened
    assert "seit Start +1.250,50 EUR (+0.25%)" in opened
    assert "Verfügbar:</b> Cash 488.904,83 EUR" in opened
    assert "offen investiert 12.345,67 EUR" in opened

    closed = service._render_telegram_paper_trade_closed_alert(
        {
            "ticker": "AAPL",
            "direction": "long",
            "setup_type": "breakout",
            "opened_at": "2026-07-11T12:00:00+00:00",
            "closed_at": "2026-07-13T15:30:00+00:00",
            "entry_price": 201.125,
            "closed_price": 218.5,
            "invested_value": 12345.67,
            "final_value": 13412.33,
            "realized_pnl_value": 1066.66,
            "account_equity": 502317.16,
            "account_cash_available": 502317.16,
            "account_open_exposure": 0,
            "account_net_pnl_value": 2317.16,
            "account_net_pnl_pct": 0.46,
            "realized_pnl_pct": 8.64,
            "result_label": "winner",
            "exit_reason": "target_or_profit_taken",
            "lessons_learned": "Volume confirmation mattered.",
            "risk_reward": 2.4,
        }
    )
    assert "investiert 12.345,67 EUR" in closed
    assert "11.07.2026, 14:00 CEST bis 13.07.2026, 17:30 CEST | gehalten 2T 3Std 30Min" in closed
    assert "final 13.412,33 EUR" in closed
    assert "Ergebnis:</b> +1.066,66 EUR | +8.64%" in closed
    assert "target_or_profit_taken" in closed
    assert "Demo-Konto danach:</b> Equity 502.317,16 EUR" in closed
    assert "seit Start +2.317,16 EUR (+0.46%)" in closed
    assert "Verfügbar:</b> Cash 502.317,16 EUR" in closed
    assert "offen investiert 0,00 EUR" in closed

    behind = service._paper_account_after_line(
        {
            "account_equity": 497500,
            "account_cash_available": 487500,
            "account_open_exposure": 10000,
            "account_net_pnl_value": -2500,
            "account_net_pnl_pct": -0.5,
        }
    )
    assert "seit Start -2.500,00 EUR (-0.50%)" in behind

    previous_env = os.environ.get("APP_ENV")
    os.environ["APP_ENV"] = "production"
    try:
        assert service._paper_trade_time("2026-01-12T08:15:00") == "12.01.2026, 09:15 CET"
    finally:
        if previous_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_env

    management = service._render_telegram_paper_trade_management_alert(
        {
            "ticker": "AAPL",
            "direction": "long",
            "management_status": "near_target",
            "management_action": "protect_profit",
            "decision_grade": "protect",
            "entry_price": 201.125,
            "current_price": 214.4,
            "stop_price": 194.0,
            "target_price": 218.5,
            "unrealized_pnl_pct": 6.6,
            "risk_distance_pct": 9.95,
            "target_progress_pct": 76.4,
            "management_summary": "Trade ist nahe am Ziel.",
            "next_check": "Gewinnschutz prüfen.",
        }
    )
    assert "PnL +6.60%" in management
    assert "Stop +9.95%" in management
    assert "Ziel-Fortschritt +76.40%" in management

    account = service._render_telegram_paper_account_status_alert(
        {
            "day_status": "monitor",
            "day_action": "Aktuellen Paper-Plan halten.",
            "capital_status": "ahead",
            "starting_capital": 500000,
            "equity": 501250.5,
            "net_pnl_value": 1250.5,
            "net_pnl_pct": 0.25,
            "open_exposure_value": 42000,
            "cash_available_value": 459250.5,
            "open_trade_count": 2,
            "closed_trade_count": 4,
            "management_counts": {"hold": 2},
            "top_trades": [
                {
                    "ticker": "AAPL",
                    "direction": "long",
                    "grade": "hold",
                    "result_value_delta": 650.25,
                    "summary": "Funktioniert.",
                    "next_check": "Stop gültig halten.",
                }
            ],
        }
    )
    assert "Equity 501.250,50 EUR" in account
    assert "Netto-Ergebnis:</b> +1.250,50 EUR (+0.25%)" in account
    assert "investiert 42.000,00 EUR" in account
    assert "P/L +650,25 EUR" in account


if __name__ == "__main__":
    test_paper_learning_alert_extraction()
    test_paper_trade_telegram_money_formatting()
    print("qa_paper_learning_alerts: ok")
