from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.paper_trading_service import PaperTradingService


ROOT = Path(__file__).resolve().parent


def test_policy_floor_is_split_without_double_charging():
    service = PaperTradingService.__new__(PaperTradingService)
    execution = service._simulate_execution_fill(
        reference_price=100,
        direction="long",
        phase="entry",
        asset_class="equity",
        market_data={"liquidity_status": "strong", "source": "qa_quote"},
        quantity=1000,
    )
    assert execution["cost_bps"] == 8.0
    assert execution["slippage_bps"] == 7.0
    assert execution["fee_equivalent_bps"] == 1.0
    assert execution["fill_price"] == 100.08
    assert execution["estimated_slippage_value"] == 70.0
    assert execution["estimated_fee_value"] == 10.0
    assert execution["estimated_cost_value"] == 80.0


def test_observed_half_spread_sets_minimum_slippage():
    service = PaperTradingService.__new__(PaperTradingService)
    execution = service._simulate_execution_fill(
        reference_price=100,
        direction="long",
        phase="entry",
        asset_class="equity",
        market_data={
            "liquidity_status": "strong",
            "spread_pct": 0.4,
            "source": "observed_two_sided_quote",
            "data_as_of": datetime.now(timezone.utc).isoformat(),
        },
        quantity=100,
    )
    assert execution["slippage_bps"] == 20.0
    assert execution["fee_equivalent_bps"] == 1.0
    assert execution["cost_bps"] == 21.0
    assert execution["fill_price"] == 100.21
    assert execution["calibration"]["calibration_source"] == "observed_bid_ask_spread"
    assert execution["calibration"]["observed_half_spread_bps"] == 20.0


def test_option_contract_fee_is_included_once():
    service = PaperTradingService.__new__(PaperTradingService)
    execution = service._simulate_execution_fill(
        reference_price=5,
        direction="call",
        phase="entry",
        asset_class="option",
        market_data={"liquidity_status": "strong", "spread_pct": 8.0, "source": "tradier_brokerage_options"},
        quantity=2,
        contract_multiplier=100,
    )
    assert execution["slippage_bps"] == 400.0
    assert execution["estimated_fee_value"] == 1.8  # 5 bps variable fee + 2 x 0.65
    assert execution["estimated_cost_value"] == 41.8
    assert execution["fill_price"] == 5.209
    assert execution["calibration"]["option_fee_per_contract"] == 0.65


def test_rolling_asset_class_calibration_requires_spread_sample():
    service = PaperTradingService.__new__(PaperTradingService)
    trades = []
    for index in range(5):
        trades.append(
            {
                "asset_class": "etf",
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "trade_ticket": {
                    "execution_model": {
                        "entry": {
                            "spread_pct": 0.1 + index * 0.02,
                            "cost_bps": 8 + index,
                            "calibration": {
                                "observed_spread_pct": 0.1 + index * 0.02,
                                "slippage_bps": 6 + index,
                                "fee_equivalent_bps": 1,
                                "total_cost_bps": 7 + index,
                            },
                        }
                    }
                },
            }
        )
    result = service._build_execution_cost_calibration(trades)
    etf = next(row for row in result["rows"] if row["asset_class"] == "etf")
    equity = next(row for row in result["rows"] if row["asset_class"] == "equity")
    assert result["lookback_days"] == 90
    assert etf["status"] == "calibrated"
    assert etf["spread_samples"] == 5
    assert etf["median_observed_spread_pct"] == 0.14
    assert equity["status"] == "provisional"
    assert equity["policy_fallback_bps"] == 8.0


def test_app_and_telegram_expose_cost_components():
    panel = (ROOT / "frontend/src/components/PaperTradingPanel.tsx").read_text(encoding="utf-8")
    telegram = (ROOT / "src/email_alert_service.py").read_text(encoding="utf-8")
    for marker in (
        'data-testid="execution-cost-calibration"',
        "Spread-, Slippage- und Gebührenkalibrierung",
        "median_observed_spread_pct",
        "spread_samples",
        "entryExecution.slippage_bps",
        "entryExecution.fee_equivalent_bps",
    ):
        assert marker in panel
    for marker in ("Slippage", "Gebühren", "slippage_bps", "fee_equivalent_bps"):
        assert marker in telegram


if __name__ == "__main__":
    tests = [
        test_policy_floor_is_split_without_double_charging,
        test_observed_half_spread_sets_minimum_slippage,
        test_option_contract_fee_is_included_once,
        test_rolling_asset_class_calibration_requires_spread_sample,
        test_app_and_telegram_expose_cost_components,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"execution cost calibration QA ok: {len(tests)} contracts")
