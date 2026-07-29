from __future__ import annotations

import os
import json
from datetime import datetime, timedelta

from src.email_alert_service import EmailAlertService


class _SettingsStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_app_setting(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def set_app_setting(self, key: str, value: str) -> None:
        self.values[key] = value


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
            "account_capital_flow": {
                "equity_value": 501250.5,
                "cash_available_value": 488904.83,
                "open_exposure_value": 12345.67,
                "realized_pnl_value": 1206.05,
                "unrealized_pnl_value": 44.45,
                "net_pnl_value": 1250.5,
                "net_pnl_pct": 0.25,
            },
            "account_performance": {
                "sample_size": 12,
                "minimum_usable_sample": 30,
                "profit_factor": 1.42,
                "expectancy_value": 85.25,
                "win_rate": 58.3,
                "evidence_label": "Stichprobe im Aufbau",
            },
            "strategy_context": {
                "id": "momentum_follow_through",
                "label": "Momentum Follow-Through",
                "status": "learning",
                "recommendation": "continue_learning",
                "real_world_ready": False,
                "sample_size": 12,
                "minimum_usable_sample": 30,
                "hit_rate": 58.3,
                "profit_factor": 1.42,
                "expectancy_value": 85.25,
                "readiness_gaps": ["8 weitere klare Paper-Prüfungen nötig."],
                "next_step": "8 weitere klare Paper-Prüfungen nötig.",
            },
            "risk_reward": 2.4,
            "confidence_score": 91,
            "trigger": "Breakout mit Volumen bestätigt.",
            "invalidation": "Schließen, wenn Breakout scheitert.",
            "management_action": "hold_with_plan",
            "management_summary": "Position halten, solange Volumen und Trend intakt bleiben.",
            "management_next_check": "Nach US-Eröffnung Preis, Volumen und Stop-Abstand erneut prüfen.",
            "trade_ticket": {
                "status": "paper_ready",
                "horizon": "days-weeks",
                "source_label": "official filing",
                "data_as_of": "2026-07-11T12:00:00",
                "market_data": {
                    "freshness": "fresh",
                    "age_hours": 1.5,
                    "liquidity_status": "strong",
                    "average_dollar_volume_5d": 125_000_000,
                },
                "execution_model": {
                    "entry": {
                        "reference_price": 201.0,
                        "fill_price": 201.125,
                        "cost_bps": 6.2,
                        "estimated_cost_value": 7.67,
                    }
                },
                "validation": {"warnings": ["manual_market_check"]},
            },
            "source_label": "Paper-Playbook manuell",
        }
    )
    assert "investiert 12.345,67 EUR" in opened
    assert "Referenz 201.00 → Fill 201.12" in opened
    assert "6.2 bps" in opened
    assert "Kosten 7,67 EUR" in opened
    assert "Eröffnet:</b> 11.07.2026, 14:00 CEST" in opened
    assert "aktueller Wert 12.390,12 EUR" in opened
    assert "Offenes Ergebnis:</b> +44,45 EUR" in opened
    assert "Max. Demo-Verlust:</b> 450,00 EUR" in opened
    assert "Ticket:</b> paper_ready" in opened
    assert "Horizont:</b> days-weeks" in opened
    assert "official filing" in opened
    assert "Jetzt tun:</b> mit Plan halten | Position halten, solange Volumen und Trend intakt bleiben." in opened
    assert "Nächste Prüfung:</b> Nach US-Eröffnung Preis, Volumen und Stop-Abstand erneut prüfen." in opened
    assert "Paper-Playbook manuell" in opened
    assert "fresh (1.5h)" in opened
    assert "Liquidität strong" in opened
    assert "5T-Notional 125.0 Mio." in opened
    assert "manual_market_check" in opened
    assert "Demo-Konto danach:</b> Equity 501.250,50 EUR" in opened
    assert "seit Start +1.250,50 EUR (+0.25%)" in opened
    assert "Verfügbar:</b> Cash 488.904,83 EUR" in opened
    assert "offen investiert 12.345,67 EUR" in opened
    assert "Geldfluss:</b> realisiert +1.206,05 EUR | offen +44,45 EUR" in opened
    assert "Lernqualität:</b> 12/30 Trades | PF 1.42 | Erwartung +85,25 EUR/Trade" in opened
    assert "Treffer 58.30% | Stichprobe im Aufbau" in opened
    assert "Strategie:</b> Momentum Follow-Through | lernen / weiter lernen | nur Paper-Lernen" in opened
    assert "Strategie-Beweise:</b> 12/30 Trades | Treffer 58.30% | PF 1.42 | Erwartung +85,25 EUR/Trade" in opened
    assert "Nächster Strategie-Check:</b> 8 weitere klare Paper-Prüfungen nötig." in opened
    assert "Blocker:</b> 8 weitere klare Paper-Prüfungen nötig." in opened

    closed = service._render_telegram_paper_trade_closed_alert(
        {
            "ticker": "AAPL",
            "direction": "long",
            "asset_class": "equity",
            "setup_type": "breakout",
            "opened_at": "2026-07-11T12:00:00+00:00",
            "closed_at": "2026-07-13T15:30:00+00:00",
            "entry_price": 201.125,
            "closed_price": 218.5,
            "quantity": 61.38,
            "invested_value": 12345.67,
            "final_value": 13412.33,
            "realized_pnl_value": 1066.66,
            "account_equity": 502317.16,
            "account_cash_available": 502317.16,
            "account_open_exposure": 0,
            "account_net_pnl_value": 2317.16,
            "account_net_pnl_pct": 0.46,
            "account_capital_flow": {
                "equity_value": 502317.16,
                "cash_available_value": 502317.16,
                "open_exposure_value": 0,
                "realized_pnl_value": 2317.16,
                "unrealized_pnl_value": 0,
                "net_pnl_value": 2317.16,
                "net_pnl_pct": 0.46,
            },
            "account_performance": {
                "sample_size": 30,
                "minimum_usable_sample": 30,
                "profit_factor": 1.81,
                "expectancy_value": 77.24,
                "win_rate": 60.0,
                "evidence_label": "belastbare Stichprobe",
            },
            "realized_pnl_pct": 8.64,
            "result_label": "winner",
            "exit_reason": "target_or_profit_taken",
            "lessons_learned": "Volume confirmation mattered.",
            "risk_reward": 2.4,
            "trade_ticket": {
                "entry_source_label": "Paper-Playbook manuell",
                "execution_model": {
                    "exit": {
                        "reference_price": 218.7,
                        "fill_price": 218.5,
                        "cost_bps": 9.1,
                        "estimated_cost_value": 12.28,
                    }
                }
            },
        }
    )
    assert "[PAPER GESCHLOSSEN - GEWINN]" in closed
    assert "Asset:</b> equity | <b>Setup:</b> breakout | <b>Menge:</b> 61.38" in closed
    assert "11.07.2026, 14:00 CEST bis 13.07.2026, 17:30 CEST | gehalten 2T 3Std 30Min" in closed
    assert "Kapitalfluss Trade:</b> Einsatz 12.345,67 EUR | R\u00fcckfluss 13.412,33 EUR" in closed
    assert "Realisiertes Ergebnis:</b> +1.066,66 EUR | +8.64%" in closed
    assert "Exit-Grund:</b> Ziel/Gewinnmitnahme" in closed
    assert "Entry-Quelle:</b> Paper-Playbook manuell" in closed
    assert "Referenz 218.70 → Fill 218.50" in closed
    assert "9.1 bps" in closed
    assert "Demo-Konto danach:</b> Equity 502.317,16 EUR" in closed
    assert "seit Start +2.317,16 EUR (+0.46%)" in closed
    assert "Verfügbar:</b> Cash 502.317,16 EUR" in closed
    assert "offen investiert 0,00 EUR" in closed
    assert "Geldfluss:</b> realisiert +2.317,16 EUR | offen 0,00 EUR" in closed
    assert "Lernqualität:</b> 30/30 Trades | PF 1.81 | Erwartung +77,24 EUR/Trade" in closed
    assert "belastbare Stichprobe" in closed

    loss = service._render_telegram_paper_trade_closed_alert(
        {
            "ticker": "TSLA",
            "direction": "short",
            "asset_class": "equity",
            "setup_type": "failed_breakout",
            "entry_price": 320.0,
            "closed_price": 326.4,
            "quantity": 10,
            "invested_value": 3200.0,
            "final_value": 3136.0,
            "realized_pnl_value": -64.0,
            "realized_pnl_pct": -2.0,
            "result_label": "loser",
            "exit_reason": "stop_hit",
        }
    )
    assert "[PAPER GESCHLOSSEN - VERLUST]" in loss
    assert "<code>TSLA</code> SHORT" in loss
    assert "Realisiertes Ergebnis:</b> -64,00 EUR | -2.00% | Verlierer" in loss

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
    assert "Geldfluss:</b> realisiert n/a | offen n/a" in behind

    assert service._paper_trade_open_subject([{"source_label": "Paper-Autopilot"}]) == "Paper Autopilot: Demo-Trade geöffnet"
    assert service._paper_trade_open_subject([{"source_label": "Paper-Playbook manuell"}]) == "Paper Playbook: Demo-Trade geöffnet"
    assert (
        service._paper_trade_open_subject(
            [{"source_label": "Paper-Autopilot"}, {"source_label": "Paper-Playbook manuell"}]
        )
        == "Paper Trading: Demo-Trade geöffnet"
    )

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
            "asset_class": "equity",
            "setup_type": "breakout",
            "opened_at": "2026-07-11T12:00:00+00:00",
            "management_status": "near_target",
            "management_action": "protect_profit",
            "decision_grade": "protect",
            "entry_price": 201.125,
            "current_price": 214.4,
            "stop_price": 194.0,
            "target_price": 218.5,
            "quantity": 61.38,
            "invested_value": 12345.67,
            "current_value": 13160.72,
            "unrealized_pnl_pct": 6.6,
            "unrealized_pnl_value": 815.05,
            "risk_distance_pct": 9.95,
            "target_progress_pct": 76.4,
            "management_summary": "Trade ist nahe am Ziel.",
            "next_check": "Gewinnschutz prüfen.",
        }
    )
    assert "<code>AAPL</code> LONG" in management
    assert "Position:</b> equity | breakout | Menge 61.38" in management
    assert "Kapital:</b> Einsatz 12.345,67 EUR | aktueller Wert 13.160,72 EUR" in management
    assert "Offenes Ergebnis:</b> +815,05 EUR | +6.60%" in management
    assert "Stop +9.95%" in management
    assert "Ziel-Fortschritt +76.40%" in management

    management_loss = service._render_telegram_paper_trade_management_alert(
        {
            "ticker": "TSLA",
            "direction": "short",
            "asset_class": "equity",
            "setup_type": "failed_breakout",
            "management_status": "near_stop",
            "management_action": "reduce_or_close_review",
            "decision_grade": "review",
            "entry_price": 320.0,
            "current_price": 326.4,
            "stop_price": 328.0,
            "target_price": 295.0,
            "quantity": 10,
            "invested_value": 3200.0,
            "current_value": 3136.0,
            "unrealized_pnl_pct": -2.0,
            "unrealized_pnl_value": -64.0,
        }
    )
    assert "<code>TSLA</code> SHORT" in management_loss
    assert "Offenes Ergebnis:</b> -64,00 EUR | -2.00%" in management_loss

    account = service._render_telegram_paper_account_status_alert(
        {
            "day_status": "risk_halt",
            "day_action": "Keine neuen Paper-Entries.",
            "capital_status": "ahead",
            "starting_capital": 500000,
            "equity": 501250.5,
            "net_pnl_value": 1250.5,
            "net_pnl_pct": 0.25,
            "open_exposure_value": 42000,
            "cash_available_value": 459250.5,
            "open_trade_count": 2,
            "closed_trade_count": 4,
            "capital_flow": {
                "starting_capital_value": 500000,
                "equity_value": 501250.5,
                "cash_available_value": 459250.5,
                "open_exposure_value": 42000,
                "realized_pnl_value": 900.25,
                "unrealized_pnl_value": 350.25,
                "net_pnl_value": 1250.5,
                "net_pnl_pct": 0.25,
                "capital_status": "ahead",
                "open_trade_count": 2,
                "closed_trade_count": 4,
            },
            "management_counts": {"hold": 2},
            "performance": {
                "sample_size": 9,
                "minimum_usable_sample": 30,
                "profit_factor": None,
                "expectancy_value": 138.94,
                "win_rate": 66.7,
                "evidence_label": "zu wenig Daten",
            },
            "risk_circuit": {
                "status": "paused",
                "display_reasons": ["Drei Verluste in Folge; der Paper-Cooldown ist aktiv."],
                "daily_realized_pnl_value": -3000,
                "current_drawdown_pct": 1.2,
                "drawdown_limit_pct": 8.0,
                "consecutive_losses": 3,
                "cooldown_until": "2026-07-11T18:00:00+00:00",
            },
            "trade_action_queue": {
                "status": "exit",
                "message": "Zuerst AAPL LONG pruefen: jetzt pruefen.",
                "top_priority": {
                    "ticker": "AAPL",
                    "direction": "long",
                    "decision_grade": "exit",
                    "management_status": "target_hit",
                },
                "items": [
                    {
                        "ticker": "AAPL",
                        "direction": "long",
                        "decision_grade": "exit",
                        "management_status": "target_hit",
                        "priority_label": "jetzt pruefen",
                        "unrealized_pnl_value": 650.25,
                        "summary": "Zielzone erreicht.",
                        "next_check": "Schliessen oder Trailing-Plan festhalten.",
                    }
                ],
            },
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
    assert "Geldfluss:</b> realisiert +900,25 EUR | offen +350,25 EUR" in account
    assert "investiert 42.000,00 EUR" in account
    assert "Jetzt zuerst:</b> Zuerst AAPL LONG pruefen" in account
    assert "jetzt pruefen | EXIT" in account
    assert "P/L +650,25 EUR" in account
    assert "Risk Circuit:</b> PAUSED" in account
    assert "Drawdown 1.20% / Limit 8.00%" in account
    assert "Heute:</b> -3.000,00 EUR | Verlustserie 3" in account
    assert "Lernqualität:</b> 9/30 Trades | PF offen | Erwartung +138,94 EUR/Trade" in account
    assert "Treffer 66.70% | zu wenig Daten" in account
    assert "Drei Verluste in Folge" in account
    assert "Cooldown bis:" in account


def test_paper_trade_management_alert_cooldown() -> None:
    service = EmailAlertService.__new__(EmailAlertService)
    service.portfolio_manager = _SettingsStore()
    trade = {"id": 42, "unrealized_pnl_pct": -1.0}
    management = {"status": "near_stop", "decision_grade": "review"}

    assert service._paper_trade_management_can_send(trade, management) is True
    service._record_paper_trade_management_deliveries(
        [
            {
                "trade_id": 42,
                "management_status": "near_stop",
                "decision_grade": "review",
                "unrealized_pnl_pct": -1.0,
            }
        ]
    )
    assert service._paper_trade_management_can_send(trade, management) is False
    assert service._paper_trade_management_can_send(trade, {**management, "status": "stop_hit"}) is True
    assert service._paper_trade_management_can_send(trade, {**management, "decision_grade": "exit"}) is True
    assert service._paper_trade_management_can_send({**trade, "unrealized_pnl_pct": -4.0}, management) is True

    state_key = service._paper_trade_management_state_key(42)
    previous = json.loads(service.portfolio_manager.values[state_key])
    previous["sent_at"] = (datetime.now().astimezone() - timedelta(hours=5)).isoformat()
    service.portfolio_manager.values[state_key] = json.dumps(previous)
    assert service._paper_trade_management_can_send(trade, management) is True


def test_paper_account_status_alert_tracks_action_queue_change() -> None:
    service = EmailAlertService.__new__(EmailAlertService)
    service.portfolio_manager = _SettingsStore()
    base_account = {
        "day_status": "risk_review",
        "management_counts": {"review": 1},
        "risk_circuit": {"status": "ready", "reasons": []},
        "trade_action_queue": {
            "status": "review",
            "top_priority": {
                "ticker": "AAPL",
                "direction": "long",
                "decision_grade": "review",
                "management_status": "near_stop",
            },
        },
    }

    assert service._paper_account_status_can_send(base_account) is True
    service._record_paper_account_status_delivery(base_account)
    assert service._paper_account_status_can_send(base_account) is False
    changed_top = {
        **base_account,
        "trade_action_queue": {
            "status": "review",
            "top_priority": {
                "ticker": "MSFT",
                "direction": "short",
                "decision_grade": "review",
                "management_status": "near_stop",
            },
        },
    }
    assert service._paper_account_status_can_send(changed_top) is True


if __name__ == "__main__":
    test_paper_learning_alert_extraction()
    test_paper_trade_telegram_money_formatting()
    test_paper_trade_management_alert_cooldown()
    test_paper_account_status_alert_tracks_action_queue_change()
    print("qa_paper_learning_alerts: ok")
