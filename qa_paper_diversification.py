from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

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


def test_strategy_concentration_rotates_new_capital() -> None:
    service = build_service(FakePortfolioManager())
    demo_account = {
        "equity": 500_000.0,
        "risk_budget_per_trade_value": 1_750.0,
        "remaining_risk_value": 15_000.0,
        "max_position_value": 50_000.0,
        "open_trade_slots": 4,
        "day_status": "ok",
        "learning_feedback": {},
    }
    playbook = {
        "id": "etf-SCHD-long-concentration",
        "ticker": "SCHD",
        "asset_class": "etf",
        "direction": "long",
        "setup_type": "etf_momentum",
        "strategy": {"id": "core_quality_compounder", "label": "Core Quality Compounder"},
        "score": 90.0,
        "reference_price": 25.0,
        "risk_buffer_pct": 3.0,
        "tradeable": True,
        "do_not_trade_reasons": [],
        "thesis": "Qualified core candidate.",
        "decision_framework": {
            "entry_trigger": "Trend confirms.",
            "invalidation": "Trend breaks.",
        },
        "market_data": {
            "price": 25.0,
            "data_as_of": datetime.now(timezone.utc).isoformat(),
            "freshness": "fresh",
            "liquidity_status": "strong",
        },
        "data_as_of": datetime.now(timezone.utc).isoformat(),
    }
    sized = {**playbook, **service._suggest_demo_sizing(playbook, demo_account)}
    sized["trade_ticket"] = service._build_trade_ticket(sized, demo_account)
    existing = [
        {
            "id": f"core-{index}",
            "ticker": f"ETF{index}",
            "asset_class": "etf",
            "setup_type": "etf_momentum",
            "status": "open",
        }
        for index in range(4)
    ]
    selection = service._build_auto_selection([sized], existing, demo_account)
    assert selection["selected"] == []
    assert selection["exploration"] == []
    assert selection["aggressive_exploration"] == []
    assert selection["strategy_concentration"]["open_counts"]["core_quality_compounder"] == 4
    assert any(
        "Strategie-Konzentrationslimit" in reason
        for reason in selection["rejected"][0]["aggressive_learning_block_display_reasons"]
    )


def test_exit_first_capital_rotation_cycle() -> None:
    service = build_service(FakePortfolioManager())
    summary = service.build_capital_rotation_summary(
        {"closed": [{"ticker": "VTI"}, {"ticker": "VUG"}]},
        {
            "opened": [
                {
                    "ticker": "LUNR",
                    "trade_ticket": {"strategy_id": "small_cap_future_star"},
                }
            ]
        },
    )
    assert summary["status"] == "rotated"
    assert summary["freed_trade_count"] == 2
    assert summary["opened_trade_count"] == 1
    assert summary["opened_strategy_ids"] == ["small_cap_future_star"]

    alert_service = EmailAlertService.__new__(EmailAlertService)
    rendered = alert_service._render_telegram_paper_account_status_alert(
        {
            "day_status": "monitor",
            "risk_circuit": {},
            "open_exposure_pct": 91.1,
            "effective_max_gross_exposure_pct": 90.0,
            "cash_reserve_gap_value": 5_500.0,
            "capital_rotation": summary,
            "strategy_candidate_coverage": [
                {
                    "strategy_id": "small_cap_future_star",
                    "strategy_label": "Small-Cap Future Star",
                    "candidate_count": 2,
                    "evidence_progress_pct": 0,
                    "status": "capacity_blocked",
                    "top_candidate": {"ticker": "LUNR", "score": 58.6},
                    "blockers": ["maximale Gesamt-Exposure erreicht"],
                },
                {
                    "strategy_id": "defined_risk_options",
                    "strategy_label": "Defined-Risk Calls / Puts",
                    "candidate_count": 6,
                    "evidence_progress_pct": 0,
                    "status": "manual_review_required",
                    "top_candidate": {"ticker": "GLD", "score": 81.0},
                    "blockers": ["Optionskette manuell prüfen"],
                },
            ],
        }
    )
    assert "Kapitalrotation:</b> 2 planmäßige Exits → 1 neue Evidenzpositionen" in rendered
    assert "Freigegeben:</b> VTI · VUG" in rendered
    assert "Neu eingesetzt:</b> LUNR" in rendered
    assert "Exposure:</b> 91.10% / Limit 90.00%" in rendered
    assert "Cashreserve-Lücke:</b>" in rendered
    assert "5.500,00 EUR" in rendered
    assert "Nächste Evidenzkandidaten:</b>" in rendered
    assert "<code>LUNR</code> Small-Cap Future Star | Score 58.6" in rendered
    assert rendered.index("<code>LUNR</code>") < rendered.index("<code>GLD</code>")

    api_source = (Path(__file__).resolve().parent / "api.py").read_text(encoding="utf-8")
    loop_source = api_source.split("async def _forecast_learning_loop():", 1)[1].split(
        "def _run_paper_news_source_revalidation", 1
    )[0]
    assert loop_source.index("_run_paper_news_source_revalidation") < loop_source.index("_run_paper_managed_exits")
    assert loop_source.index("_run_paper_managed_exits") < loop_source.index("_run_scheduled_paper_learning_autopilot")
    assert loop_source.index("_run_scheduled_paper_learning_autopilot") < loop_source.index("_send_paper_account_status_alerts")
    assert 'bool(paper_managed_exits.get("closed"))' in loop_source
    autopilot_source = api_source.split("def _run_scheduled_paper_learning_autopilot(", 1)[1].split(
        "def _safe_int_env", 1
    )[0]
    assert "if now < next_allowed and not managed_exit_freed_capacity:" in autopilot_source
    assert '"managed_exit_freed_capacity"' in autopilot_source

    manual_status_source = api_source.split("async def send_paper_account_status_now():", 1)[1].split(
        "@app.", 1
    )[0]
    assert "service.build_dashboard(" in manual_status_source
    assert "strategy_candidate_coverage=strategy_candidate_coverage" in manual_status_source

    dashboard = service.build_dashboard({"stocks": [], "crypto": []})
    rotation_policy = dashboard.get("capital_rotation_policy") or {}
    assert rotation_policy.get("schema") == "paper-capital-rotation-policy.v1"
    assert rotation_policy.get("cycle_order") == [
        "source_revalidation",
        "managed_exits",
        "autopilot_selection",
        "management_alerts",
        "account_status",
    ]


if __name__ == "__main__":
    test_broad_equity_feed()
    test_asset_class_limits_and_cash_reserve()
    test_quantitative_correlation_gate()
    test_strategy_dimensions_and_telegram_allocation()
    test_strategy_concentration_rotates_new_capital()
    test_exit_first_capital_rotation_cycle()
    print("qa_paper_diversification: ok")
