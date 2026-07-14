from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from src.paper_trading_service import PaperTradingService


class FakePortfolioManager:
    def __init__(self, trades: List[Dict[str, Any]] | None = None) -> None:
        self.trades = trades or []
        self.created: List[Dict[str, Any]] = []
        self.outcomes: List[Dict[str, Any]] = []
        self.app_settings: Dict[str, str] = {}

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

    def close_paper_trade(
        self,
        trade_id: str,
        closed_price: float,
        notes: str | None = None,
        exit_reason: str | None = None,
        lessons_learned: str | None = None,
    ) -> Dict[str, Any] | None:
        for item in self.trades:
            if item.get("id") != trade_id:
                continue
            item.update(
                {
                    "status": "closed",
                    "closed_at": datetime.now().isoformat(),
                    "closed_price": closed_price,
                    "notes": item.get("notes") if notes is None else notes,
                    "exit_reason": item.get("exit_reason") if exit_reason is None else exit_reason,
                    "lessons_learned": item.get("lessons_learned") if lessons_learned is None else lessons_learned,
                }
            )
            return dict(item)
        return None

    def get_app_setting(self, key: str, default: str | None = None) -> str | None:
        return self.app_settings.get(key, default)

    def set_app_setting(self, key: str, value: str) -> None:
        self.app_settings[key] = value


def build_service(manager: FakePortfolioManager) -> PaperTradingService:
    service = PaperTradingService(manager)  # type: ignore[arg-type]
    prices = {
        "AAPL": 100.0,
        "MSFT": 100.0,
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
    assert demo["starting_capital"] == 500_000.0
    assert demo["equity"] == 500_000.0
    assert demo["risk_budget_per_trade_value"] == 1_750.0
    assert demo["risk_budget_per_option_trade_value"] == 1_250.0
    assert demo["max_position_value"] == 50_000.0
    assert demo["max_option_premium_value"] == 3_750.0

    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert aapl["demo_tradeable"] is True
    assert aapl["suggested_quantity"] == 500
    assert aapl["suggested_notional_value"] == 50_000.0
    assert aapl["suggested_max_loss_value"] <= 1_750.0
    assert aapl["suggested_account_pct"] <= 10.0
    assert aapl["suggested_risk_pct"] <= 0.35
    assert aapl["decision_framework"]["entry_trigger"]
    assert aapl["decision_framework"]["invalidation"]
    assert aapl["decision_framework"]["real_money_policy"].startswith("Nur Entscheidungsrahmen")
    ticket = aapl["trade_ticket"]
    assert ticket["schema_version"] == "1.0"
    assert ticket["status"] == "paper_ready"
    assert ticket["paper_ready"] is True
    assert ticket["real_money_ready"] is False
    assert ticket["entry_price"] == 100.0
    assert ticket["stop_price"] == 96.5
    assert ticket["target_1"] == 103.75
    assert ticket["target_2"] == 107.5
    assert ticket["risk_reward"] == 2.14
    assert ticket["account_risk_pct"] <= 0.35

    aapl_call = next(item for item in dashboard["playbooks"] if item["id"] == "option-AAPL-call")
    assert aapl_call["asset_class"] == "option"
    assert aapl_call["direction"] == "call"
    assert aapl_call["demo_tradeable"] is True
    assert aapl_call["suggested_quantity"] == 5
    assert aapl_call["suggested_notional_value"] == 1_250.0
    assert aapl_call["suggested_max_loss_value"] == 1_250.0
    assert aapl_call["suggested_risk_pct"] == 0.25
    assert aapl_call["decision_framework"]["evidence_level"] in {"paper_candidate", "high_quality_paper", "watch"}
    assert aapl_call["trade_ticket"]["status"] == "paper_only"
    assert "option_chain_not_validated" in aapl_call["trade_ticket"]["validation"]["warnings"]
    assert "prämie" in aapl_call["decision_framework"]["risk_plan"].lower()

    created = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created["ticker"] == "AAPL"
    assert created["quantity"] == 500
    assert created["stop_price"] < created["entry_price"] < created["target_price"]
    assert "Entscheidungs-Snapshot beim Paper-Einstieg" in created["notes"]
    assert "Trigger:" in created["notes"]
    assert "Invalidierung:" in created["notes"]
    assert created["trade_ticket"]["schema_version"] == "1.0"
    assert created["trade_ticket"]["real_money_ready"] is False
    assert len([item for item in manager.outcomes if item["trade_id"] == created["id"]]) == 4

    created_call = service.create_trade_from_playbook(
        {"playbook_id": "option-AAPL-call", "direction": "call", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created_call["ticker"] == "AAPL"
    assert created_call["asset_class"] == "option"
    assert created_call["direction"] == "call"
    assert created_call["quantity"] == 5
    assert created_call["entry_price"] == 2.5
    assert created_call["stop_price"] == 1.25
    assert created_call["target_price"] == 5.0
    assert "Options-Gate:" in created_call["notes"]
    assert "nur Paper-Premienmodell" in created_call["notes"]
    call_outcomes = [item for item in manager.outcomes if item["trade_id"] == created_call["id"]]
    assert {item["horizon_hours"] for item in call_outcomes} == {1, 24, 72, 168, 240}

    result = service.evaluate_due_outcomes()
    assert result["evaluated"] >= 1
    assert any(item.get("status") == "evaluated" for item in manager.outcomes)


def test_realized_return_uses_account_equity() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    stats = service._build_stats(
        [
            {"status": "closed", "realized_pnl_pct": 10.0, "realized_pnl_value": 100.0, "direction": "long"},
            {"status": "closed", "realized_pnl_pct": 90.0, "realized_pnl_value": 900.0, "direction": "long"},
        ],
        starting_capital=500_000.0,
    )
    assert stats["realized_pnl_value"] == 1000.0
    assert stats["realized_pnl_pct"] == 0.2
    assert stats["average_trade_pnl_pct"] == 50.0


def test_short_trade_money_flow_and_demo_equity() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "open-short-winner",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "short",
                "setup_type": "qa_short",
                "status": "open",
                "opened_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "stop_price": 104.0,
                "target_price": 92.0,
                "quantity": 50,
                "confidence_score": 90,
                "leverage": 1,
            },
            {
                "id": "closed-short-loser",
                "ticker": "MSFT",
                "asset_class": "equity",
                "direction": "short",
                "setup_type": "qa_short",
                "status": "closed",
                "opened_at": "2026-06-18T08:00:00",
                "closed_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "closed_price": 110.0,
                "stop_price": 104.0,
                "target_price": 92.0,
                "quantity": 50,
                "confidence_score": 90,
                "leverage": 1,
                "exit_reason": "stop_hit",
                "lessons_learned": "Short failed after price reclaimed trigger.",
            },
        ]
    )
    service = build_service(manager)
    service._get_last_price = lambda ticker: 90.0 if ticker == "AAPL" else 100.0  # type: ignore[method-assign]
    enriched = service._enrich_trades(manager.trades)

    open_short = next(item for item in enriched if item["id"] == "open-short-winner")
    assert open_short["invested_value"] == 5000.0
    assert open_short["current_price"] == 90.0
    assert open_short["unrealized_pnl_pct"] == 10.0
    assert open_short["unrealized_pnl_value"] == 500.0
    assert open_short["current_value"] == 5500.0
    assert open_short["result_value_delta"] == 500.0
    assert open_short["result_label"] == "more"

    closed_short = next(item for item in enriched if item["id"] == "closed-short-loser")
    assert closed_short["invested_value"] == 5000.0
    assert closed_short["realized_pnl_pct"] == -10.0
    assert closed_short["realized_pnl_value"] == -500.0
    assert closed_short["final_value"] == 4500.0
    assert closed_short["result_value_delta"] == -500.0
    assert closed_short["result_label"] == "less"

    demo = service._build_demo_account(enriched, [])
    assert demo["starting_capital"] == 500_000.0
    assert demo["realized_pnl_value"] == -500.0
    assert demo["unrealized_pnl_value"] == 500.0
    assert demo["net_pnl_value"] == 0.0
    assert demo["net_pnl_pct"] == 0.0
    assert demo["equity"] == 500_000.0
    assert demo["open_exposure_value"] == 5000.0
    assert demo["cash_available_value"] == 495_000.0
    assert demo["capital_status"] == "flat"


def test_put_learning_inverts_underlying_move() -> None:
    manager = FakePortfolioManager()
    service = build_service(manager)
    result = service._evaluate_outcome_item(
        {
            "asset_class": "option",
            "direction": "put",
            "ticker": "AAPL",
            "entry_price": 2.5,
            "underlying_entry_price": 100.0,
            "horizon_hours": 24,
        },
        "2026-06-19T12:00:00",
    )
    assert result["status"] == "evaluated"
    assert result["performance_pct"] == 0.0

    service._get_last_price = lambda ticker: 95.0  # type: ignore[method-assign]
    result = service._evaluate_outcome_item(
        {
            "asset_class": "option",
            "direction": "put",
            "ticker": "AAPL",
            "entry_price": 2.5,
            "underlying_entry_price": 100.0,
            "horizon_hours": 24,
        },
        "2026-06-19T12:00:00",
    )
    assert result["status"] == "evaluated"
    assert result["performance_pct"] == 5.0
    assert result["result"] == "hit"


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
                "quantity": 3000,
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
    assert "Offenes Risikobudget ist ausgeschöpft." in aapl["demo_block_reasons"]

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


def test_demo_account_blocks_new_trades_during_risk_review() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "near-stop",
                "ticker": "MSFT",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_review",
                "status": "open",
                "opened_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "stop_price": 99.5,
                "target_price": 110.0,
                "quantity": 10,
                "confidence_score": 95,
                "leverage": 1,
            }
        ]
    )
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())
    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert dashboard["demo_account"]["day_status"] == "risk_review"
    assert aapl["demo_tradeable"] is False
    assert "Paper-Konto ist im Risiko-Review; schwache oder stop-nahe Trades zuerst prüfen." in aapl["demo_block_reasons"]
    assert dashboard["auto_selection"]["selected"] == []
    blocker_summary = dashboard["auto_selection"]["blocker_summary"]
    assert blocker_summary["checked"] >= 1
    assert any("risiko-review" in item["reason"].lower() for item in blocker_summary["top_reasons"])
    assert all(item["reason"] != "Playbook is blocked by signal rules." for item in blocker_summary["top_reasons"])
    assert blocker_summary["next_best_rejected"]["ticker"]

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "risk gate" in str(exc)
    else:
        raise AssertionError("Risk-review gate should block opening new paper trades.")


def test_learning_feedback_tracks_missing_journals() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "closed-missing-lesson",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_loss",
                "status": "closed",
                "opened_at": "2026-06-18T08:00:00",
                "closed_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "closed_price": 97.0,
                "stop_price": 95.0,
                "target_price": 110.0,
                "quantity": 10,
                "confidence_score": 80,
                "leverage": 1,
                "exit_reason": "",
                "lessons_learned": "",
            },
            {
                "id": "closed-documented",
                "ticker": "MSFT",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_win",
                "status": "closed",
                "opened_at": "2026-06-18T08:00:00",
                "closed_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "closed_price": 104.0,
                "stop_price": 95.0,
                "target_price": 110.0,
                "quantity": 10,
                "confidence_score": 80,
                "leverage": 1,
                "exit_reason": "target_review",
                "lessons_learned": "Repeat only with same trigger quality.",
            },
        ]
    )
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())
    feedback = dashboard["demo_account"]["learning_feedback"]
    assert feedback["closed_trades"] == 2
    assert feedback["journal_complete"] is False
    assert feedback["journal_completion_rate"] == 50.0
    assert feedback["missing_journal_count"] == 1
    assert feedback["missing_journal_trades"][0]["ticker"] == "AAPL"
    assert "fehlende Paper-Journale" in feedback["next_rule"]
    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert aapl["demo_tradeable"] is False
    assert "1 fehlende Paper-Journale abschließen, bevor neue Exposure hinzukommt." in aapl["demo_block_reasons"]
    assert dashboard["auto_selection"]["selected"] == []
    blocker_summary = dashboard["auto_selection"]["blocker_summary"]
    assert any("fehlende paper-journale" in item["reason"].lower() for item in blocker_summary["top_reasons"])
    assert all(item["reason"] != "Playbook is blocked by signal rules." for item in blocker_summary["top_reasons"])
    preview = service.run_auto_selection(sample_scoreboard(), sample_settings(), execute=False)
    assert preview["selected"] == []
    assert "Nächster Kandidat" in preview["message"]
    assert "Paper-Journale" in preview["message"]
    assert "candidate(s)" not in preview["message"]
    assert "Kandidat(en)" not in preview["message"]
    assert ".." not in preview["message"]
    execute = service.run_auto_selection(sample_scoreboard(), sample_settings(), execute=True)
    assert execute["opened"] == []
    assert execute["demo_account_after"]["starting_capital"] == 500_000.0
    assert execute["demo_account_after"]["closed_trade_count"] == 2
    assert execute["demo_account_after"]["open_exposure_value"] == 0.0
    assert "Nächster Kandidat" in execute["message"]
    assert "candidate(s)" not in execute["message"]
    assert "Kandidat(en)" not in execute["message"]
    assert ".." not in execute["message"]
    qa_loss = next(item for item in dashboard["setup_performance"] if item["setup_type"] == "qa_loss")
    assert qa_loss["quality_status"] == "needs_journal"
    assert qa_loss["journal_completion_rate"] == 0.0
    assert "Exit-Grund" in qa_loss["next_action"]

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "risk gate" in str(exc)
    else:
        raise AssertionError("Missing journal gate should block opening new paper trades.")


def test_auto_rejection_summary_prefers_fixable_candidate() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    summary = service._summarize_auto_rejections(
        [
            {
                "ticker": "ETH-USD",
                "direction": "long",
                "setup_type": "crypto_flow",
                "score": 95,
                "reasons": ["same ticker/setup/direction already open"],
                "next_action": service._auto_rejection_next_action(["same ticker/setup/direction already open"]),
            },
            {
                "ticker": "AAPL",
                "direction": "long",
                "setup_type": "insider_follow",
                "score": 87,
                "auto_score_gap": 1.0,
                "learning_score_gap": 0.0,
                "reasons": ["score below auto minimum 88"],
                "learning_block_reasons": ["missing thesis, trigger or invalidation"],
                "learning_block_display_reasons": ["These, Trigger oder Invalidierung fehlt"],
                "next_action": service._auto_rejection_next_action(["score below auto minimum 88"]),
            },
        ]
    )
    assert summary["duplicate_blocked_count"] == 1
    assert summary["next_best_rejected"]["ticker"] == "AAPL"
    assert summary["next_best_rejected"]["source"] == "best_fixable"
    assert summary["next_best_rejected"]["display_reasons"][0] == "Score unter Auto-Minimum 88"
    assert summary["next_best_rejected"]["blocker_label"] == "Score zu niedrig"
    assert summary["next_best_rejected"]["auto_score_gap"] == 1.0
    assert summary["next_best_rejected"]["learning_score_gap"] == 0.0
    assert summary["next_best_rejected"]["learning_block_display_reasons"][0] == "These, Trigger oder Invalidierung fehlt"
    assert "Score 88+" in summary["next_best_rejected"]["missing_to_trade"]
    assert summary["blocker_groups"][0]["count"] >= 1
    assert summary["top_reasons"][0]["display_reason"]
    assert "Score 88+" in summary["next_best_rejected"]["next_action"]
    assert "Duplikat" in service._auto_rejection_next_action(["same ticker/setup/direction already open"])
    message = service._auto_selection_no_trade_message("strict", summary)
    assert "Score unter Auto-Minimum 88" in message
    assert "score below auto minimum" not in message


def test_strict_score_block_does_not_block_learning_candidate() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    demo_account = {
        "equity": 500_000.0,
        "risk_budget_per_trade_value": 1_750.0,
        "remaining_risk_value": 15_000.0,
        "max_position_value": 50_000.0,
        "open_trade_slots": 5,
        "day_status": "ok",
        "learning_feedback": {},
    }
    playbook = {
        "id": "equity-ETH-long",
        "ticker": "ETH-USD",
        "asset_class": "crypto",
        "direction": "long",
        "setup_type": "crypto_flow",
        "score": 75.4,
        "reference_price": 4000.0,
        "risk_buffer_pct": 3.5,
        "tradeable": False,
        "do_not_trade_reasons": ["Score below minimum trade score 78."],
        "thesis": "Crypto flow watch.",
        "decision_framework": {
            "entry_trigger": "ETH confirms flow with price and volume.",
            "invalidation": "ETH loses the trigger zone.",
        },
    }
    sized = {**playbook, **service._suggest_demo_sizing(playbook, demo_account)}
    assert sized["demo_block_reasons"][0].startswith("Strict-Signalregel:")
    selection = service._build_auto_selection([sized], [], demo_account)
    assert selection["selected"] == []
    assert selection["exploration"][0]["ticker"] == "ETH-USD"
    assert selection["rejected"][0]["learning_block_reasons"] == []
    capital = service._summarize_candidate_capital(selection["exploration"])
    assert capital["count"] == 1
    assert capital["notional_value"] > 0
    assert capital["max_loss_value"] > 0


def test_close_trade_auto_documents_profitable_exit() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "open-winner",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_win",
                "status": "open",
                "opened_at": "2026-06-18T08:00:00",
                "entry_price": 100.0,
                "stop_price": 95.0,
                "target_price": 104.0,
                "quantity": 10,
                "confidence_score": 90,
                "leverage": 1,
                "notes": "",
                "exit_reason": "",
                "lessons_learned": "",
            }
        ]
    )
    service = build_service(manager)
    closed = service.close_trade("open-winner", closed_price=105.0)
    assert closed["status"] == "closed"
    assert closed["exit_reason"] == "target_or_profit_taken"
    assert "Auto-classified win" in closed["lessons_learned"]
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())
    feedback = dashboard["demo_account"]["learning_feedback"]
    assert feedback["journal_complete"] is True
    assert feedback["missing_journal_count"] == 0


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
    assert any("paper-ergebnisse" in reason.lower() for reason in aapl["do_not_trade_reasons"])
    assert dashboard["outcome_learning"]["setup_adjustments"]["insider_follow"]["block"] is True
    learning = dashboard["outcome_learning"]["learning_summary"]
    assert learning["blocked_setups"] == 1
    assert learning["real_money_policy"] == "Nur Entscheidungsrahmen: keine automatische Echtgeld-Ausführung."
    assert any("geblockte setup" in item.lower() for item in learning["review_focus"])
    option = dashboard["outcome_learning"]["option_readiness"]
    assert option["status"] == "paper_only"
    assert option["required_decisive"] == 20
    assert option["required_hit_rate"] == 55


if __name__ == "__main__":
    test_demo_account_sizing()
    test_realized_return_uses_account_equity()
    test_short_trade_money_flow_and_demo_equity()
    test_put_learning_inverts_underlying_move()
    test_demo_account_blocks_when_open_risk_is_exhausted()
    test_demo_account_blocks_new_trades_during_risk_review()
    test_learning_feedback_tracks_missing_journals()
    test_auto_rejection_summary_prefers_fixable_candidate()
    test_strict_score_block_does_not_block_learning_candidate()
    test_close_trade_auto_documents_profitable_exit()
    test_outcome_learning_penalizes_weak_setups()
    print("qa_paper_demo_account: ok")
