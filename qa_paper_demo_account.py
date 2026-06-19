from __future__ import annotations

from typing import Any, Dict, List

from src.paper_trading_service import PaperTradingService


class FakePortfolioManager:
    def __init__(self, trades: List[Dict[str, Any]] | None = None) -> None:
        self.trades = trades or []
        self.created: List[Dict[str, Any]] = []
        self.outcomes: List[Dict[str, Any]] = []

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

    def upsert_paper_trade_outcomes(self, trade_id: str, outcomes: List[Dict[str, Any]]) -> int:
        inserted = 0
        existing = {(item["trade_id"], item["horizon_hours"]) for item in self.outcomes}
        for outcome in outcomes:
            key = (trade_id, outcome["horizon_hours"])
            if key in existing:
                continue
            self.outcomes.append({**outcome, "trade_id": trade_id})
            inserted += 1
        return inserted

    def list_paper_trade_outcomes(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self.outcomes[:limit]

    def list_due_paper_trade_outcomes(self, limit: int = 80) -> List[Dict[str, Any]]:
        due = []
        for item in self.outcomes:
            if item.get("status") not in {"pending", "pending_data"}:
                continue
            trade = next((row for row in self.trades if row.get("id") == item.get("trade_id")), {})
            due.append({**trade, **item, "trade_status": trade.get("status")})
        return due[:limit]

    def update_paper_trade_outcome(self, outcome_id: str, updates: Dict[str, Any]) -> None:
        for item in self.outcomes:
            if item.get("id") == outcome_id:
                item.update(updates)
                return


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
    assert demo["risk_budget_per_option_trade_value"] == 250.0
    assert demo["max_position_value"] == 6_000.0
    assert demo["max_option_premium_value"] == 500.0

    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert aapl["demo_tradeable"] is True
    assert aapl["suggested_quantity"] == 60
    assert aapl["suggested_notional_value"] == 6_000.0
    assert aapl["suggested_max_loss_value"] <= 250.0
    assert aapl["suggested_account_pct"] <= 12.0
    assert aapl["suggested_risk_pct"] <= 0.5

    aapl_call = next(item for item in dashboard["playbooks"] if item["id"] == "option-AAPL-call")
    assert aapl_call["asset_class"] == "option"
    assert aapl_call["direction"] == "call"
    assert aapl_call["demo_tradeable"] is True
    assert aapl_call["suggested_quantity"] == 1
    assert aapl_call["suggested_notional_value"] == 250.0
    assert aapl_call["suggested_max_loss_value"] == 250.0
    assert aapl_call["suggested_risk_pct"] == 0.5

    created = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created["ticker"] == "AAPL"
    assert created["quantity"] == 60
    assert created["stop_price"] < created["entry_price"] < created["target_price"]
    assert len([item for item in manager.outcomes if item["trade_id"] == created["id"]]) == 4

    created_call = service.create_trade_from_playbook(
        {"playbook_id": "option-AAPL-call", "direction": "call", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created_call["ticker"] == "AAPL"
    assert created_call["asset_class"] == "option"
    assert created_call["direction"] == "call"
    assert created_call["quantity"] == 1
    assert created_call["entry_price"] == 2.5
    assert created_call["stop_price"] == 1.25
    assert created_call["target_price"] == 5.0
    call_outcomes = [item for item in manager.outcomes if item["trade_id"] == created_call["id"]]
    assert {item["horizon_hours"] for item in call_outcomes} == {1, 24, 72, 168, 240}

    result = service.evaluate_due_outcomes()
    assert result["evaluated"] >= 1
    assert any(item.get("status") == "evaluated" for item in manager.outcomes)


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


def test_outcome_learning_penalizes_weak_setups() -> None:
    manager = FakePortfolioManager()
    for index in range(8):
        manager.outcomes.append(
            {
                "id": f"bad-{index}",
                "trade_id": f"trade-{index}",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "insider_follow",
                "horizon_hours": 24,
                "due_at": "2026-06-19T09:00:00",
                "status": "evaluated",
                "result": "miss",
                "performance_pct": -1.8,
                "error_tag": "weak_follow_through",
            }
        )
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())
    aapl = next(item for item in dashboard["playbooks"] if item["id"] == "equity-AAPL-long")
    assert aapl["raw_score"] == 95
    assert aapl["score"] == 81
    assert aapl["learning_blocked"] is True
    assert aapl["tradeable"] is False
    assert any("outcome learning" in reason.lower() for reason in aapl["do_not_trade_reasons"])
    assert dashboard["outcome_learning"]["setup_adjustments"]["insider_follow"]["block"] is True
    learning = dashboard["outcome_learning"]["learning_summary"]
    assert learning["blocked_setups"] == 1
    assert learning["real_money_policy"] == "Decision support only: no automatic real-money execution."
    assert any("blocked setup" in item.lower() for item in learning["review_focus"])
    option = dashboard["outcome_learning"]["option_readiness"]
    assert option["status"] == "paper_only"
    assert option["required_decisive"] == 20
    assert option["required_hit_rate"] == 55


if __name__ == "__main__":
    test_demo_account_sizing()
    test_demo_account_blocks_when_open_risk_is_exhausted()
    test_outcome_learning_penalizes_weak_setups()
    print("qa_paper_demo_account: ok")
