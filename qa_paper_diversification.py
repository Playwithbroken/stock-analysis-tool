from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pandas as pd

import src.paper_trading_service as paper_module
from qa_paper_demo_account import FakePortfolioManager, build_service, sample_settings
from src.email_alert_service import EmailAlertService
from src.signal_score_service import SignalScoreService


class FakeDiscovery:
    async def get_paper_equity_candidates(self):
        return [
            {
                "ticker": "AAPL",
                "name": "Apple",
                "sector": "Technology",
                "market_cap": 3_000_000_000_000,
                "price": 220.0,
                "change_1d": 1.0,
                "change_1m": 8.0,
                "change_3m": 14.0,
                "above_sma20": True,
                "above_sma50": True,
                "volume_ratio": 1.3,
                "volatility_annual_pct": 28.0,
                "revenue_growth_pct": 9.0,
                "earnings_growth_pct": 12.0,
                "profit_margin_pct": 25.0,
                "source_label": "QA market/fundamental snapshot",
                "data_as_of": datetime.now(timezone.utc).isoformat(),
            }
        ]

    async def get_etfs(self):
        return []

    async def get_cryptos(self):
        return []


def test_broad_equity_feed() -> None:
    service = SignalScoreService()
    service.discovery_service = FakeDiscovery()
    scoreboard = asyncio.run(service.build_scoreboard({}, {}))
    assert scoreboard["equities"]
    assert scoreboard["equities"][0]["ticker"] == "AAPL"
    assert scoreboard["equities"][0]["signal_type"] == "broad_equity_quality_momentum"
    assert scoreboard["equity_feed"]["broad_market_candidates"] == 1
    assert scoreboard["equity_feed"]["research_only"] is True


def test_asset_class_limits_and_cash_reserve() -> None:
    service = build_service(FakePortfolioManager())
    account = service._build_demo_account([], [])
    assert account["effective_max_gross_exposure_pct"] == 90.0
    assert account["cash_reserve_target_value"] == 50_000.0
    assert account["asset_class_limits"]["equity"]["limit_value"] == 225_000.0
    assert account["asset_class_limits"]["etf"]["limit_value"] == 225_000.0
    assert account["asset_class_limits"]["crypto"]["limit_value"] == 60_000.0

    sizing = service._suggest_demo_sizing(
        {
            "ticker": "BTC-USD",
            "asset_class": "crypto",
            "direction": "long",
            "reference_price": 50_000.0,
            "risk_buffer_pct": 5.0,
            "tradeable": True,
        },
        {
            **account,
            "asset_class_limits": {
                **account["asset_class_limits"],
                "crypto": {**account["asset_class_limits"]["crypto"], "remaining_value": 0.0},
            },
        },
    )
    assert sizing["demo_tradeable"] is False
    assert any("Asset-class exposure budget" in reason for reason in sizing["demo_block_reasons"])


def test_quantitative_correlation_gate() -> None:
    service = build_service(FakePortfolioManager())
    dates = pd.date_range("2026-01-01", periods=80, freq="B")
    aapl = [100.0 * (1.01**idx) for idx in range(80)]
    msft = [200.0 * (1.01**idx) for idx in range(80)]
    columns = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "MSFT")])
    frame = pd.DataFrame(list(zip(aapl, msft)), index=dates, columns=columns)
    original_download = paper_module.yf.download
    paper_module.yf.download = lambda **_kwargs: frame
    try:
        playbooks = [{"ticker": "MSFT", "asset_class": "equity", "direction": "long"}]
        open_trades = [{"ticker": "AAPL", "asset_class": "equity", "direction": "long", "status": "open"}]
        account = {}
        service._attach_quantitative_correlation(playbooks, open_trades, account)
    finally:
        paper_module.yf.download = original_download
    check = playbooks[0]["correlation_check"]
    assert check["blocked"] is True
    assert check["observations"] >= 40
    assert check["absolute_correlation"] >= 0.99
    assert account["correlation_analysis"]["status"] == "ready"


def test_strategy_dimensions_and_telegram_allocation() -> None:
    service = build_service(FakePortfolioManager())
    trade = {
        "ticker": "AAPL",
        "asset_class": "equity",
        "setup_type": "equity_quality_momentum",
        "direction": "long",
        "status": "closed",
        "confidence_score": 82,
        "realized_pnl_value": 100.0,
        "realized_pnl_pct": 1.0,
        "trade_ticket": {
            "entry_source_label": "Paper-Autopilot",
            "entry_market_regime": {"risk_appetite": {"label": "risk_on"}},
        },
    }
    performance = service._build_strategy_dimension_performance([trade])
    dimensions = {row["dimension"] for row in performance["rows"]}
    assert dimensions == {"setup", "market_regime", "source", "score_band", "risk_bucket"}

    alert_service = EmailAlertService.__new__(EmailAlertService)
    line = alert_service._paper_allocation_line(
        {
            "account_asset_class_limits": {
                "equity": {"used_pct": 20, "limit_pct": 45},
                "etf": {"used_pct": 40, "limit_pct": 45},
                "crypto": {"used_pct": 10, "limit_pct": 12},
                "option": {"used_pct": 0, "limit_pct": 8},
            },
            "account_cash_reserve_target": 50_000,
        }
    )
    assert "Aktien 20.0/45%" in line
    assert "Krypto 10.0/12%" in line
    assert "Cashreserve-Ziel" in line


if __name__ == "__main__":
    test_broad_equity_feed()
    test_asset_class_limits_and_cash_reserve()
    test_quantitative_correlation_gate()
    test_strategy_dimensions_and_telegram_allocation()
    print("qa_paper_diversification: ok")
