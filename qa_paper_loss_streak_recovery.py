from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_paper_demo_account import FakePortfolioManager, build_service
from src.email_alert_service import EmailAlertService


def _closed_trade(trade_id: str, closed_at: datetime, pnl: float) -> dict:
    return {
        "id": trade_id,
        "status": "closed",
        "closed_at": closed_at.isoformat(),
        "realized_pnl_value": pnl,
    }


def test_loss_streak_pauses_then_restarts_at_reduced_risk() -> None:
    service = build_service(FakePortfolioManager())
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    config = {
        **service._demo_account_config(),
        "max_consecutive_losses": 3,
        "loss_streak_cooldown_hours": 24,
        "post_loss_streak_risk_multiplier": 0.25,
        "daily_loss_limit_pct": 10,
        "max_drawdown_pct": 12,
    }
    losses = [
        _closed_trade("loss-1", now - timedelta(hours=75), -100),
        _closed_trade("loss-2", now - timedelta(hours=74), -100),
        _closed_trade("loss-3", now - timedelta(hours=73), -100),
        _closed_trade("loss-4", now - timedelta(hours=1), -100),
    ]

    paused = service._build_paper_risk_circuit(losses, 499_600, 500_000, config, now=now)
    assert paused["active"] is True
    assert paused["status"] == "paused"
    assert paused["streak_recovery_active"] is True
    assert paused["risk_multiplier"] == 0.25
    assert paused["cooldown_until"] is not None
    assert paused["cooldown_until"].endswith("+00:00")

    old_losses = [
        {**trade, "closed_at": (now - timedelta(hours=50 - index)).isoformat()}
        for index, trade in enumerate(losses)
    ]
    recovery = service._build_paper_risk_circuit(old_losses, 499_600, 500_000, config, now=now)
    assert recovery["active"] is False
    assert recovery["status"] == "reduced_risk"
    assert recovery["streak_recovery_active"] is True
    assert recovery["risk_multiplier"] == 0.25
    assert recovery["recovery_condition"] == "one_profitable_closed_trade"
    assert "profitabel geschlossener Paper-Trade" in recovery["recovery_message"]

    sizing = service._suggest_demo_sizing(
        {
            "ticker": "AAPL",
            "asset_class": "equity",
            "reference_price": 100,
            "risk_buffer_pct": 10,
            "tradeable": True,
        },
        {
            "equity": 500_000,
            "risk_budget_per_trade_value": 1_000,
            "remaining_risk_value": 10_000,
            "max_position_value": 100_000,
            "cash_available_value": 500_000,
            "remaining_gross_exposure_value": 500_000,
            "max_ticker_exposure_value": 125_000,
            "asset_class_limits": {"equity": {"remaining_value": 225_000}},
            "open_trade_slots": 10,
            "risk_circuit": recovery,
            "learning_feedback": {"missing_journal_count": 0},
        },
    )
    assert sizing["risk_multiplier"] == 0.25
    assert sizing["suggested_max_loss_value"] == 250.0

    recovered = service._build_paper_risk_circuit(
        [*old_losses, _closed_trade("winner", now - timedelta(minutes=5), 50)],
        499_650,
        500_000,
        config,
        now=now,
    )
    assert recovered["consecutive_losses"] == 0
    assert recovered["streak_recovery_active"] is False
    assert recovered["status"] == "ready"
    assert recovered["risk_multiplier"] == 1.0


def test_recovery_is_explicit_in_telegram() -> None:
    service = EmailAlertService.__new__(EmailAlertService)
    rendered = service._render_telegram_paper_account_status_alert(
        {
            "day_status": "controlled_restart",
            "day_action": "Nur kontrollierte Paper-Entries.",
            "risk_circuit": {
                "status": "reduced_risk",
                "current_drawdown_pct": 1.4,
                "drawdown_limit_pct": 12,
                "daily_realized_pnl_value": 0,
                "consecutive_losses": 8,
                "streak_recovery_active": True,
                "risk_multiplier": 0.25,
                "recovery_message": "Kontrollierter Wiederanlauf mit 25% Risiko, bis ein profitabel geschlossener Paper-Trade die Verlustserie beendet.",
            },
        }
    )
    assert "Kontrollierter Wiederanlauf" in rendered
    assert "Risiko 25.00%" in rendered
    assert "profitabel geschlossener Paper-Trade" in rendered


if __name__ == "__main__":
    test_loss_streak_pauses_then_restarts_at_reduced_risk()
    test_recovery_is_explicit_in_telegram()
    print("qa_paper_loss_streak_recovery: ok")
