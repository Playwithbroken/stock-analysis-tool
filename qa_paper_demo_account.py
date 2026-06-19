from __future__ import annotations

from typing import Any, Dict, List

from src.paper_trading_service import PaperTradingService


class FakePortfolioManager:
    def __init__(self, trades: List[Dict[str, Any]] | None = None) -> None:
        self.trades = trades or []
        self.created: List[Dict[str, Any]] = []

    def list_paper_trades(self, limit: int = 150) -> List[Dict[str, Any]]:
        return self.trades[:limit]

    def create_paper_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade = {
            "id": f"qa-{len(self.created) + 1}",
            "status": "open",
            "opened_at": "2026-06-19T08:00:00",
            **payload,
        }
        self.created.append(trade)
        self.trades.append(trade)
        return trade


def build_service(manager: FakePortfolioManager) -> PaperTradingService:
    service = PaperTradingService(manager)  # type: ignore[arg-type]
    prices = {
        "AAPL": 100.0,
        "JEPI": 50.0,
        "BTC-USD": 50_000.0,
    }
    service._get_last_price = lambda ticker: prices.get(ticker or "")  # type: ignore[method-assign]
    return service


def sample_scoreboard() -> Dict[str, Any]:
    return {
        "equities": [
            {
                "ticker": "AAPL",
                "action": "buy",
                "total_score": 95,
                "headline": "Strong quality follow-through",
                "source_label": "QA",
                "delay_days": 1,
            }
        ],
        "etfs": [
            {
                "ticker": "JEPI",
                "total_score": 88,
                "headline": "Dividend ETF quality setup",
            }
        ],
        "crypto": [
            {
                "ticker": "BTC-USD",
                "total_score": 90,
                "headline": "Crypto flow setup",
            }
        ],
        "politics": [],
    }


def sample_settings() -> Dict[str, Any]:
    return {
        "do_not_trade": {
            "min_score_for_new_trade": 78,
            "min_score_for_leverage": 88,
            "block_crypto_leverage": True,
        }
    }


def test_demo_account_sizing() -> None:
    manager = FakePortfolioManager()
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())

    demo = dashboard["demo_account"]
    assert demo["starting_capital"] == 50_000.0
    assert demo["equity"] == 50_000.0
    assert demo["risk_budget_per_trade_value"] == 250.0
    assert demo["max_position_value"] == 6_000.0

    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert aapl["demo_tradeable"] is True
    assert aapl["suggested_quantity"] == 60
    assert aapl["suggested_notional_value"] == 6_000.0
    assert aapl["suggested_max_loss_value"] <= 250.0
    assert aapl["suggested_account_pct"] <= 12.0
    assert aapl["suggested_risk_pct"] <= 0.5

    created = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created["ticker"] == "AAPL"
    assert created["quantity"] == 60
    assert created["stop_price"] < created["entry_price"] < created["target_price"]


def test_demo_account_blocks_when_open_risk_is_exhausted() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "risk-full",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa",
                "status": "open",
                "opened_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "stop_price": 95.0,
                "target_price": 110.0,
                "quantity": 400,
                "confidence_score": 95,
                "leverage": 1,
            }
        ]
    )
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())
    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert dashboard["demo_account"]["remaining_risk_value"] == 0
    assert aapl["demo_tradeable"] is False
    assert "Open risk budget is exhausted." in aapl["demo_block_reasons"]

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "risk gate" in str(exc)
    else:
        raise AssertionError("Risk-gated playbook should not open a demo trade.")


if __name__ == "__main__":
    test_demo_account_sizing()
    test_demo_account_blocks_when_open_risk_is_exhausted()
    print("qa_paper_demo_account: ok")
