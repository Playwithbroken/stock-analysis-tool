from datetime import datetime, timezone

from src.paper_trading_service import PaperTradingService


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    service = PaperTradingService.__new__(PaperTradingService)
    trades = [
        {
            "id": "etf-1",
            "ticker": "VT",
            "asset_class": "etf",
            "opened_at": "2026-08-10T10:00:00+00:00",
            "max_holding_days": 14,
            "current_value": 80_000,
            "trade_ticket": {"strategy_id": "core_quality_compounder", "strategy_label": "Core Quality"},
        },
        {
            "id": "equity-1",
            "ticker": "JPM",
            "asset_class": "equity",
            "opened_at": "2026-08-20T10:00:00+00:00",
            "max_holding_days": 15,
            "current_value": 30_000,
            "trade_ticket": {"strategy_id": "momentum_follow_through", "strategy_label": "Momentum"},
        },
        {"id": "manual", "ticker": "TEST", "current_value": 5_000},
    ]
    campaign = {"next_priority": {"id": "defined_risk_options", "label": "Defined-Risk Calls / Puts"}}
    forecast = service._build_capital_release_forecast(
        trades,
        campaign,
        now=datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc),
    )

    require(forecast["schema"] == "paper-capital-release-forecast.v1", "forecast schema mismatch")
    require(forecast["status"] == "scheduled", "forecast status mismatch")
    require(forecast["scheduled_trade_count"] == 2, "scheduled trade count mismatch")
    require(forecast["unscheduled_trade_count"] == 1, "unscheduled trade count mismatch")
    require(forecast["due_within_72h_count"] == 1, "72h trade count mismatch")
    require(forecast["potential_release_within_72h_value"] == 80_000, "72h release estimate mismatch")
    require(forecast["next_review_at"] == "2026-08-24T10:00:00+00:00", "next review mismatch")
    require(forecast["items"][0]["strategy_id"] == "core_quality_compounder", "strategy identity lost")
    require(forecast["next_evidence_priority"]["id"] == "defined_risk_options", "evidence priority lost")
    require("not guaranteed" in forecast["policy"], "forecast must not promise capital release")

    overdue = service._build_capital_release_forecast(
        trades[:1],
        campaign,
        now=datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc),
    )
    require(overdue["status"] == "due_now", "overdue review must be explicit")
    require(overdue["items"][0]["overdue"] is True, "overdue item flag missing")
    print("capital release forecast QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
