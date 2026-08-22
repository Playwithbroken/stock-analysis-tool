import json
from datetime import datetime, timezone
from pathlib import Path

from src.paper_trading_service import PaperTradingService


class FakeManager:
    def __init__(self, snapshots=None):
        self.settings = {
            PaperTradingService.ACCOUNT_SNAPSHOT_SETTING_KEY: json.dumps(snapshots or [])
        }

    def get_app_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_app_setting(self, key, value):
        self.settings[key] = value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def account(equity: float):
    return {
        "equity": equity,
        "capital_flow": {
            "equity_value": equity,
            "realized_pnl_value": 3_000,
            "unrealized_pnl_value": 2_000,
            "cash_available_value": 20_000,
            "open_exposure_value": 85_000,
            "open_trade_count": 2,
            "closed_trade_count": 2,
        },
        "exposure_by_asset_class": {"equity": 45_000, "etf": 40_000},
    }


def main() -> int:
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    first_manager = FakeManager()
    first_service = PaperTradingService(first_manager)
    first_account = account(105_000)
    first_service._attach_period_performance(first_account, [], now=now)
    first_report = first_account["period_performance"]
    require(first_report["snapshot_count"] == 1, "first daily snapshot missing")
    require(all(row["status"] == "collecting" for row in first_report["periods"]), "missing baselines must collect")

    changed_account = account(110_000)
    first_service._attach_period_performance(changed_account, [], now=now)
    stored = json.loads(first_manager.settings[PaperTradingService.ACCOUNT_SNAPSHOT_SETTING_KEY])
    require(len(stored) == 1, "same local day must not create duplicate snapshots")
    require(stored[0]["equity_value"] == 105_000, "first daily baseline must remain immutable")

    snapshots = [
        {"captured_at": "2026-01-01T00:00:00+00:00", "local_date": "2026-01-01", "equity_value": 90_000},
        {"captured_at": "2026-08-01T00:00:00+00:00", "local_date": "2026-08-01", "equity_value": 98_000},
        {"captured_at": "2026-08-15T00:00:00+00:00", "local_date": "2026-08-15", "equity_value": 100_000},
    ]
    manager = FakeManager(snapshots)
    service = PaperTradingService(manager)
    trades = [
        {
            "ticker": "AAPL",
            "status": "closed",
            "opened_at": "2026-08-18T10:00:00+00:00",
            "closed_at": "2026-08-20T10:00:00+00:00",
            "realized_pnl_value": 1_500,
        },
        {
            "ticker": "JPM",
            "status": "closed",
            "opened_at": "2026-08-05T10:00:00+00:00",
            "closed_at": "2026-08-10T10:00:00+00:00",
            "realized_pnl_value": -500,
        },
    ]
    demo = account(105_000)
    service._attach_period_performance(demo, trades, now=now)
    report = demo["period_performance"]
    rows = {row["key"]: row for row in report["periods"]}
    require(all(row["status"] == "ready" for row in rows.values()), "real baselines must unlock all periods")
    require(rows["week"]["equity_change_value"] == 5_000, "weekly equity delta mismatch")
    require(rows["week"]["return_pct"] == 5.0, "weekly return mismatch")
    require(rows["week"]["realized_pnl_value"] == 1_500, "weekly realized PnL mismatch")
    require(rows["month"]["realized_pnl_value"] == 1_000, "monthly realized PnL mismatch")
    require(rows["year"]["return_pct"] == 16.67, "yearly return mismatch")
    require(rows["week"]["best_trade"]["ticker"] == "AAPL", "weekly best trade mismatch")

    stale = service._build_period_performance(
        account(105_000),
        trades,
        [{"captured_at": "2025-12-01T00:00:00+00:00", "equity_value": 80_000}],
        now=now,
    )
    require(all(row["status"] == "collecting" for row in stale["periods"]), "stale baseline must never unlock returns")

    frontend = Path("frontend/src/components/PaperTradingPanel.tsx").read_text(encoding="utf-8")
    telegram = Path("src/email_alert_service.py").read_text(encoding="utf-8")
    require('data-testid="paper-period-performance"' in frontend, "period report missing in app")
    require("Keine Rendite wird rückwirkend geschätzt" in frontend, "app precision warning missing")
    require('"period_performance": demo_account.get("period_performance")' in telegram, "Telegram event lacks period data")
    require("Historie wird gesammelt; keine Rendite rückwirkend geschätzt" in telegram, "Telegram fallback missing")
    print("paper period performance QA ok (daily baselines, 7d, MTD, YTD, app and Telegram)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
