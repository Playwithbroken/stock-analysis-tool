from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pandas as pd

from src.paper_trading_service import PaperTradeAlreadyClosedError, PaperTradingService
from src.strategy_library import StrategyLibrary


class FakePortfolioManager:
    def __init__(self, trades: List[Dict[str, Any]] | None = None) -> None:
        self.trades = trades or []
        self.created: List[Dict[str, Any]] = []
        self.outcomes: List[Dict[str, Any]] = []
        self.signal_forecasts: List[Dict[str, Any]] = []
        self.signal_forecast_outcomes: List[Dict[str, Any]] = []
        self.app_settings: Dict[str, str] = {}

    def list_paper_trades(
        self,
        status: str | None = None,
        limit: int = 150,
    ) -> List[Dict[str, Any]]:
        rows = self.trades
        if status is not None:
            rows = [trade for trade in rows if trade.get("status") == status]
        return rows[:limit]

    def create_paper_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trade = {
            "id": f"qa-{len(self.created) + 1}",
            "status": "open",
            "opened_at": datetime.now().isoformat(),
            **payload,
        }
        self.created.append(trade)
        self.trades.append(trade)
        return trade

    def list_signal_forecasts(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self.signal_forecasts[:limit]

    def list_signal_forecast_outcomes(self, limit: int = 2200) -> List[Dict[str, Any]]:
        return self.signal_forecast_outcomes[:limit]

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

    def get_paper_autopilot_settings(self) -> Dict[str, Any]:
        return {
            "mode": "aggressive_learning",
            "max_trades": 3,
            "strict_min_score": 88,
            "learning_min_score": 60,
            "aggressive_min_score": 52,
            "learning_risk_multiplier": 0.10,
            "aggressive_risk_multiplier": 0.25,
            "show_interesting_now": True,
        }

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
        trade_ticket: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        for item in self.trades:
            if item.get("id") != trade_id:
                continue
            if item.get("status") != "open":
                return None
            item.update(
                {
                    "status": "closed",
                    "closed_at": datetime.now().isoformat(),
                    "closed_price": closed_price,
                    "notes": item.get("notes") if notes is None else notes,
                    "exit_reason": item.get("exit_reason") if exit_reason is None else exit_reason,
                    "lessons_learned": item.get("lessons_learned") if lessons_learned is None else lessons_learned,
                    "trade_ticket": item.get("trade_ticket") if trade_ticket is None else trade_ticket,
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
        "GLD": 220.0,
        "USO": 80.0,
        "XLE": 95.0,
    }
    service._get_market_snapshot = lambda ticker, since=None, **kwargs: (  # type: ignore[method-assign]
        {
            "price": prices[ticker or ""],
            "data_as_of": "2026-06-19T08:00:00+00:00",
            "source": "qa_snapshot",
            "interval": "1d",
            "age_hours": 1.0,
            "freshness": "fresh",
            "average_volume_5d": 1_000_000,
            "average_dollar_volume_5d": prices[ticker or ""] * 1_000_000,
            "volume_basis": "qa_notional",
            "liquidity_status": "strong",
            "minimum_dollar_volume": 2_000_000,
        }
        if (ticker or "") in prices
        else {}
    )
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


def test_equity_paper_leverage_is_quality_gated_and_risk_neutral() -> None:
    manager = FakePortfolioManager()
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())
    aapl = next(item for item in dashboard["playbooks"] if item["id"] == "equity-AAPL-long")
    assessment = aapl["leverage_assessment"]
    assert assessment["eligible"] is True
    assert assessment["recommended_leverage"] == 2.0
    assert assessment["real_money_ready"] is False
    leveraged_sizing = assessment["recommended_sizing"]
    assert leveraged_sizing["suggested_quantity"] == 500.0
    assert leveraged_sizing["suggested_notional_value"] == 100_000.0
    assert leveraged_sizing["suggested_max_loss_value"] == 3_500.0
    assert leveraged_sizing["suggested_max_loss_value"] == aapl["suggested_max_loss_value"]
    jepi = next(item for item in dashboard["playbooks"] if item["id"] == "etf-JEPI-long")
    assert jepi["leverage_assessment"]["eligible"] is True
    assert jepi["leverage_assessment"]["recommended_leverage"] == 1.5
    aggressive_aapl = next(
        item for item in dashboard["auto_selection"]["aggressive_exploration"] if item["ticker"] == "AAPL"
    )
    assert aggressive_aapl["risk_multiplier"] == 0.25
    assert aggressive_aapl["score"] == 95

    opened = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 2},
        sample_scoreboard(),
        sample_settings(),
    )
    assert opened["leverage"] == 2
    assert opened["quantity"] < aapl["suggested_quantity"]
    assert opened["trade_ticket"]["leverage"] == 2
    assert opened["trade_ticket"]["real_money_ready"] is False
    assert opened["trade_ticket"]["max_loss_value"] <= 3_750.0
    assert "Paper-Hebel: 2.0x" in opened["notes"]

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 3},
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "exceeds the evidence-based paper leverage cap" in str(exc)
    else:
        raise AssertionError("Paper leverage above 2x was not rejected.")

    crypto_dashboard = build_service(FakePortfolioManager()).build_dashboard(
        sample_scoreboard(),
        sample_settings(),
    )
    crypto = next(item for item in crypto_dashboard["playbooks"] if item.get("asset_class") == "crypto")
    assert crypto["leverage_assessment"]["eligible"] is False
    assert any("Crypto-Hebel" in reason or "Krypto" in reason for reason in crypto["leverage_assessment"]["blockers"])

    auto_service = build_service(FakePortfolioManager())
    strict_run = auto_service.run_auto_selection(
        sample_scoreboard(),
        sample_settings(),
        max_trades=1,
        execute=True,
        mode="strict",
    )
    assert strict_run["opened"]
    assert strict_run["opened"][0]["leverage"] == 2.0

    try:
        build_service(FakePortfolioManager()).create_trade_from_playbook(
            {
                "playbook_id": "equity-AAPL-long",
                "direction": "long",
                "quantity": 0,
                "leverage": 2,
                "learning_mode": True,
            },
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "disabled in learning" in str(exc)
    else:
        raise AssertionError("Learning mode incorrectly accepted paper leverage.")


def test_confirmed_news_requires_full_evidence_chain() -> None:
    service = build_service(FakePortfolioManager())
    valid = {
        "title": "Microsoft raises guidance after cloud demand accelerates",
        "publisher": "Reuters",
        "source_url": "https://www.reuters.com/technology/microsoft-guidance-2026-08-03/",
        "source_quality": "tier_1",
        "published_at": "2026-08-03T08:00:00+00:00",
        "age_hours": 2.0,
        "event_type": "earnings",
        "ticker": "MSFT",
        "related_tickers": ["MSFT"],
        "ticker_association_basis": "explicit_title_entity",
        "source_evidence": {
            "quality": "tier_1",
            "link_verified": True,
            "original_document_verified": True,
            "corroboration": "corroborated",
            "source_agreement": "consistent_headline_signal",
        },
        "news_intelligence": {
            "is_important": True,
            "importance_score": 18,
            "fact_basis": "publisher_summary",
            "fact_summary": "Microsoft raised its outlook after stronger cloud demand.",
        },
        "primary_sources": [
            {
                "authority": "U.S. Securities and Exchange Commission",
                "form": "8-K",
                "url": "https://www.sec.gov/Archives/edgar/data/qa/qa.htm",
            }
        ],
        "market_confirmation": {
            "status": "confirmed",
            "expected_headline_direction": "positive",
            "ticker": "MSFT",
            "benchmark": "QQQ",
            "asset_move_since_publication": 1.8,
            "benchmark_move_since_publication": 0.4,
            "relative_move_since_publication": 1.4,
            "baseline_at": "2026-08-03T07:45:00+00:00",
            "observed_at": "2026-08-03T09:00:00+00:00",
            "event_window_aligned": True,
            "causality_proven": False,
        },
    }
    rejected = [
        {**valid, "title": "Contradicted", "market_confirmation": {**valid["market_confirmation"], "status": "contradicted"}},
        {**valid, "title": "No explicit ticker", "ticker_association_basis": "provider_related_feed_only"},
        {**valid, "title": "Stale", "age_hours": 25.0},
        {**valid, "title": "Not important", "news_intelligence": {**valid["news_intelligence"], "is_important": False}},
        {**valid, "title": "Mixed source direction", "source_evidence": {**valid["source_evidence"], "source_agreement": "mixed_headline_signal"}},
        {**valid, "title": "No earnings filing", "source_evidence": {**valid["source_evidence"], "original_document_verified": False}},
    ]
    playbooks = service._build_confirmed_news_playbooks({"top_news": [valid, *rejected]})

    assert len(playbooks) == 1
    candidate = playbooks[0]
    assert candidate["id"] == "news-MSFT-long"
    assert candidate["setup_type"] == "confirmed_news_event"
    assert candidate["score"] >= 88
    assert candidate["news_evidence"]["original_document_verified"] is True
    assert candidate["news_evidence"]["market_confirmation"]["event_window_aligned"] is True
    assert candidate["news_evidence"]["market_confirmation"]["causality_proven"] is False

    news_context = {
        "generated_at": "2026-08-03T10:00:00+00:00",
        "top_news": [valid, *rejected],
    }
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings(), news_context)
    news_playbook = next(item for item in dashboard["playbooks"] if item["id"] == "news-MSFT-long")
    assert news_playbook["trade_ticket"]["news_evidence"]["source_url"] == valid["source_url"]
    assert news_playbook["trade_ticket"]["real_money_ready"] is False
    monitor = dashboard["news_gate_monitor"]
    assert monitor["status"] == "ready"
    assert monitor["checked_count"] == 7
    assert monitor["eligible_count"] == 1
    assert monitor["rejected_count"] == 6
    assert monitor["autopilot_qualified_count"] == 1
    assert monitor["next_best_rejected"]["reasons"] == ["price_reaction_contradicted"]
    assert {item["reason"] for item in monitor["top_reasons"]} >= {
        "price_reaction_contradicted",
        "ticker_not_explicit_in_title",
        "news_older_than_24h",
        "importance_gate_not_met",
        "source_signal_conflict",
        "earnings_primary_document_missing",
    }

    blocked_monitor = service._build_news_gate_monitor(
        news_context,
        {"day_status": "risk_review"},
        [news_playbook],
        {"selected": [], "exploration": [], "aggressive_exploration": []},
    )
    assert blocked_monitor["status"] == "account_blocked"
    assert blocked_monitor["account_blocked"] is True

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "news-MSFT-long", "direction": "short"},
            sample_scoreboard(),
            sample_settings(),
            {"top_news": [valid]},
        )
    except ValueError as exc:
        assert "direction must match" in str(exc)
    else:
        raise AssertionError("Confirmed-news playbook allowed a direction opposite to its evidence.")

    opened = service.create_trade_from_playbook(
        {"playbook_id": "news-MSFT-long", "direction": "long"},
        sample_scoreboard(),
        sample_settings(),
        {"top_news": [valid]},
    )
    assert opened["trade_ticket"]["news_evidence"]["market_confirmation"]["causality_proven"] is False
    assert "Newsquelle: Reuters" in opened["notes"]
    assert opened["max_holding_days"] == 3
    assert opened["trade_ticket"]["max_holding_days"] == 3


def test_news_trade_management_exits_failed_reaction_and_reviews_stall() -> None:
    service = build_service(FakePortfolioManager())
    base = {
        "ticker": "MSFT",
        "asset_class": "equity",
        "direction": "long",
        "setup_type": "confirmed_news_event",
        "entry_price": 100.0,
        "stop_price": 97.0,
        "target_price": 106.5,
        "current_market_data": {},
        "trade_ticket": {
            "news_evidence": {
                "source_url": "https://www.reuters.com/technology/microsoft-guidance/",
            }
        },
    }
    failed = service._build_trade_management_plan(
        {
            **base,
            "opened_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "current_price": 99.0,
            "unrealized_pnl_pct": -1.0,
        }
    )
    assert failed["status"] == "news_reaction_failed"
    assert failed["decision_grade"] == "exit"
    assert failed["action"] == "close_review"
    assert failed["causality_proven"] is False
    assert failed["source_url"].startswith("https://www.reuters.com/")

    stalled = service._build_trade_management_plan(
        {
            **base,
            "opened_at": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
            "current_price": 100.1,
            "unrealized_pnl_pct": 0.1,
        }
    )
    assert stalled["status"] == "news_momentum_stalled"
    assert stalled["decision_grade"] == "review"
    assert stalled["action"] == "thesis_check"
    assert float(stalled["elapsed_hours"]) >= 29.9


def test_news_management_auto_closes_reaction_and_equity_time_exits() -> None:
    recent_manager = FakePortfolioManager(
        [
            {
                "id": "news-reaction-exit",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "confirmed_news_event",
                "status": "open",
                "opened_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                "entry_price": 101.0,
                "stop_price": 95.0,
                "target_price": 108.0,
                "quantity": 10,
                "confidence_score": 91,
                "leverage": 1,
                "trade_ticket": {"news_evidence": {"source_url": "https://www.reuters.com/qa"}},
            }
        ]
    )
    recent_result = build_service(recent_manager).close_trades_on_management_exits()
    assert len(recent_result["closed"]) == 1
    assert recent_result["closed"][0]["exit_reason"] == "managed_news_reaction_failed"

    expired_manager = FakePortfolioManager(
        [
            {
                "id": "news-time-exit",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "confirmed_news_event",
                "status": "open",
                "opened_at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
                "entry_price": 100.0,
                "stop_price": 95.0,
                "target_price": 108.0,
                "quantity": 10,
                "confidence_score": 91,
                "leverage": 1,
                "max_holding_days": 3,
                "trade_ticket": {"news_evidence": {"source_url": "https://www.reuters.com/qa"}},
            }
        ]
    )
    expired_result = build_service(expired_manager).close_trades_on_management_exits()
    assert len(expired_result["closed"]) == 1
    assert expired_result["closed"][0]["exit_reason"] == "managed_holding_period_expired"

    legacy_crypto_manager = FakePortfolioManager(
        [
            {
                "id": "legacy-crypto-time-exit",
                "ticker": "BTC-USD",
                "asset_class": "crypto",
                "direction": "long",
                "setup_type": "crypto_flow",
                "status": "open",
                "opened_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
                "entry_price": 64_000.0,
                "stop_price": 60_480.0,
                "target_price": 71_040.0,
                "quantity": 0.05,
                "confidence_score": 82,
                "leverage": 1,
            }
        ]
    )
    legacy_crypto_service = build_service(legacy_crypto_manager)
    legacy_enriched = legacy_crypto_service._enrich_trade(legacy_crypto_manager.trades[0])
    assert legacy_enriched["management_plan"]["status"] == "holding_period_expired"
    assert legacy_enriched["management_plan"]["max_holding_days"] == 7
    assert legacy_enriched["management_plan"]["holding_period_source"] == "strategy_policy"
    legacy_result = legacy_crypto_service.close_trades_on_management_exits()
    assert len(legacy_result["closed"]) == 1
    assert legacy_result["closed"][0]["exit_reason"] == "managed_holding_period_expired"


def test_demo_account_sizing() -> None:
    manager = FakePortfolioManager()
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())

    demo = dashboard["demo_account"]
    assert demo["starting_capital"] == 500_000.0
    assert demo["equity"] == 500_000.0
    assert demo["capital_flow"]["starting_capital_value"] == 500_000.0
    assert demo["capital_flow"]["equity_value"] == 500_000.0
    assert demo["capital_flow"]["open_exposure_value"] == 0.0
    assert demo["capital_flow"]["realized_pnl_value"] == 0
    assert demo["capital_flow"]["unrealized_pnl_value"] == 0
    assert demo["capital_flow"]["net_pnl_value"] == 0
    assert demo["capital_flow"]["capital_status"] == "flat"
    assert demo["risk_budget_per_trade_value"] == 3_750.0
    assert demo["risk_budget_per_option_trade_value"] == 2_500.0
    assert demo["max_position_value"] == 100_000.0
    assert demo["max_gross_exposure_value"] == 500_000.0
    assert demo["remaining_gross_exposure_value"] == 500_000.0
    assert demo["max_ticker_exposure_value"] == 125_000.0
    assert demo["max_option_premium_value"] == 10_000.0
    assert demo["max_open_option_premium_value"] == 40_000.0
    assert demo["remaining_option_premium_value"] == 40_000.0

    aapl = next(item for item in dashboard["playbooks"] if item["ticker"] == "AAPL")
    assert aapl["demo_tradeable"] is True
    assert aapl["max_holding_days"] == 10
    assert aapl["suggested_quantity"] == 1000
    assert aapl["suggested_notional_value"] == 100_000.0
    assert aapl["suggested_max_loss_value"] <= 3_750.0
    assert aapl["suggested_account_pct"] <= 20.0
    assert aapl["suggested_risk_pct"] <= 0.75
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
    assert ticket["max_holding_days"] == 10
    assert ticket["account_risk_pct"] <= 0.75
    assert ticket["market_data"]["freshness"] == "fresh"
    assert ticket["market_data"]["liquidity_status"] == "strong"
    assert "market_data_timestamp_missing" not in ticket["validation"]["errors"]
    selected = dashboard["auto_selection"]["selected"]
    assert selected
    selected_aapl = next(item for item in selected if item["ticker"] == "AAPL")
    assert selected_aapl["strategy_context"]["label"] == "Momentum Follow-Through"
    assert selected_aapl["strategy_context"]["real_world_ready"] is False
    assert selected_aapl["strategy_context"]["readiness_gaps"]

    aapl_call = next(item for item in dashboard["playbooks"] if item["id"] == "option-AAPL-call")
    assert aapl_call["asset_class"] == "option"
    assert aapl_call["direction"] == "call"
    assert aapl_call["demo_tradeable"] is True
    assert aapl_call["suggested_quantity"] == 10
    assert aapl_call["suggested_notional_value"] == 2_500.0
    assert aapl_call["suggested_max_loss_value"] == 2_500.0
    assert aapl_call["suggested_risk_pct"] == 0.5
    assert aapl_call["max_holding_days"] == 10
    assert aapl_call["decision_framework"]["evidence_level"] in {"paper_candidate", "high_quality_paper", "watch"}
    assert aapl_call["trade_ticket"]["status"] == "paper_only"
    assert "option_chain_not_validated" in aapl_call["trade_ticket"]["validation"]["warnings"]
    assert "prämie" in aapl_call["decision_framework"]["risk_plan"].lower()

    gold_call = next(item for item in dashboard["playbooks"] if item["id"] == "commodity-option-GLD-call")
    assert gold_call["asset_class"] == "option"
    assert gold_call["setup_type"] == "commodity_call_leverage_learning"
    assert gold_call["underlying_asset"] == "Gold"
    assert gold_call["underlying_proxy"] == "GLD"
    assert gold_call["trade_ticket"]["status"] == "paper_only"
    assert gold_call["trade_ticket"]["real_money_ready"] is False
    assert "leverage_product_data_required" in gold_call["trade_ticket"]["validation"]["warnings"]
    assert "Strike or knockout level" in gold_call["decision_framework"]["product_data_required"]
    assert "Knockout" in gold_call["decision_framework"]["risk_plan"]

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "commodity-option-GLD-call", "direction": "call", "quantity": 0, "leverage": 1},
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "Leveraged product data gate" in str(exc)
        assert "issuer_required" in str(exc)
    else:
        raise AssertionError("Commodity leverage proxy must require concrete product data.")

    created_gold_call = service.create_trade_from_playbook(
        {
            "playbook_id": "commodity-option-GLD-call",
            "direction": "call",
            "quantity": 0,
            "leverage": 1,
            "product_data": {
                "product_type": "knockout",
                "issuer": "QA Bank",
                "strike_or_knockout_level": 205.0,
                "expiry": "2030-01-17",
                "bid": 4.80,
                "ask": 4.95,
                "offered_leverage": 20,
                "distance_to_knockout_pct": 8.0,
                "overnight_risk_ack": True,
            },
        },
        sample_scoreboard(),
        sample_settings(),
    )
    assert created_gold_call["asset_class"] == "option"
    assert created_gold_call["leverage"] == 20
    assert created_gold_call["entry_price"] > 4.95
    assert created_gold_call["trade_ticket"]["leveraged_product"]["issuer"] == "QA Bank"
    assert created_gold_call["trade_ticket"]["leveraged_product"]["spread_pct"] < 6
    assert created_gold_call["trade_ticket"]["leverage_assessment"]["provider_offered_leverage"] == 20
    assert created_gold_call["trade_ticket"]["leverage_assessment"]["leverage_embedded_in_product_price"] is True
    assert created_gold_call["invested_value"] < 20_000
    assert "Geprüftes Hebelprodukt" in created_gold_call["notes"]

    created = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created["ticker"] == "AAPL"
    assert created["quantity"] == 999.200639
    assert created["entry_price"] == 100.08
    assert created["invested_value"] == 100_000.0
    assert created["stop_price"] < created["entry_price"] < created["target_price"]
    assert "Entscheidungs-Snapshot beim Paper-Einstieg" in created["notes"]
    assert "Trigger:" in created["notes"]
    assert "Invalidierung:" in created["notes"]
    assert created["trade_ticket"]["schema_version"] == "1.0"
    assert created["trade_ticket"]["real_money_ready"] is False
    assert created["trade_ticket"]["entry_source_label"] == "Paper-Autopilot"
    assert created["playbook_id"] == "equity-AAPL-long"
    assert created["source_playbook"]["strategy_context"]["label"] == "Momentum Follow-Through"
    assert created["source_playbook"]["strategy_context"]["real_world_ready"] is False
    assert created["source_playbook"]["trigger"]
    assert created["source_playbook"]["invalidation"]
    entry_execution = created["trade_ticket"]["execution_model"]["entry"]
    assert entry_execution["reference_price"] == 100.0
    assert entry_execution["fill_price"] == 100.08
    assert entry_execution["cost_bps"] == 8.0
    assert entry_execution["estimated_cost_value"] == 79.94
    assert len([item for item in manager.outcomes if item["trade_id"] == created["id"]]) == 5

    try:
        service.create_trade_from_playbook(
            {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 1001, "leverage": 1},
            sample_scoreboard(),
            sample_settings(),
        )
    except ValueError as exc:
        assert "risk cap" in str(exc)
    else:
        raise AssertionError("Requested quantity above the demo risk cap must be blocked.")

    created_call = service.create_trade_from_playbook(
        {"playbook_id": "option-AAPL-call", "direction": "call", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created_call["ticker"] == "AAPL"
    assert created_call["asset_class"] == "option"
    assert created_call["direction"] == "call"
    assert created_call["quantity"] == 9
    assert created_call["entry_price"] == 2.5312
    assert created_call["stop_price"] == 1.27
    assert created_call["target_price"] == 5.06
    assert created_call["trade_ticket"]["execution_model"]["entry"]["cost_bps"] == 125.0
    assert "Options-Gate:" in created_call["notes"]
    assert "nur Paper-Premienmodell" in created_call["notes"]
    call_outcomes = [item for item in manager.outcomes if item["trade_id"] == created_call["id"]]
    assert {item["horizon_hours"] for item in call_outcomes} == {1, 24, 72, 168, 240}

    result = service.evaluate_due_outcomes()
    assert result["evaluated"] >= 1
    assert any(item.get("status") == "evaluated" for item in manager.outcomes)

    closed_created = service.close_trade(created["id"], closed_price=105.0)
    assert closed_created["closed_price"] == 104.916
    assert closed_created["trade_ticket"]["execution_model"]["exit"]["reference_price"] == 105.0
    assert closed_created["trade_ticket"]["execution_model"]["exit"]["cost_bps"] == 8.0
    assert closed_created["realized_pnl_value"] < (105.0 - 100.0) * 1000


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
    assert stats["loss_count"] == 0
    assert stats["performance"]["profit_factor"] is None
    assert stats["performance"]["expectancy_value"] == 500.0
    assert stats["performance"]["evidence_status"] == "insufficient_sample"


def test_performance_metrics_expose_bad_payoff_despite_high_win_rate() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    trades = []
    for index in range(8):
        trades.append(
            {
                "id": f"win-{index}",
                "status": "closed",
                "setup_type": "qa_payoff",
                "realized_pnl_pct": 1.0,
                "realized_pnl_value": 100.0,
                "exit_reason": "target_review",
                "lessons_learned": "Good follow-through with controlled risk.",
            }
        )
    for index in range(2):
        trades.append(
            {
                "id": f"loss-{index}",
                "status": "closed",
                "setup_type": "qa_payoff",
                "realized_pnl_pct": -10.0,
                "realized_pnl_value": -1000.0,
                "exit_reason": "stop_loss",
                "lessons_learned": "Loss was too large versus average winner.",
            }
        )

    stats = service._build_stats(trades, starting_capital=500_000.0)
    performance = stats["performance"]
    assert stats["win_rate"] == 80.0
    assert performance["profit_factor"] == 0.4
    assert performance["payoff_ratio"] == 0.1
    assert performance["expectancy_value"] == -120.0
    assert performance["evidence_status"] == "building_sample"

    setup = service._build_setup_performance(trades)[0]
    assert setup["quality_status"] == "downgrade"
    assert "stärkere Bestätigung" in setup["next_action"]


def test_entry_source_performance_separates_manual_and_autopilot() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    rows = service._build_entry_source_performance(
        [
            {
                "id": "auto-win",
                "status": "closed",
                "realized_pnl_pct": 4.0,
                "realized_pnl_value": 400.0,
                "trade_ticket": {"entry_source_label": "Paper-Autopilot"},
            },
            {
                "id": "manual-loss",
                "status": "closed",
                "realized_pnl_pct": -3.0,
                "realized_pnl_value": -300.0,
                "trade_ticket": {"entry_source_label": "Paper-Playbook manuell"},
            },
        ]
    )
    by_source = {item["entry_source_label"]: item for item in rows}
    assert by_source["Paper-Autopilot"]["performance"]["expectancy_value"] == 400.0
    assert by_source["Paper-Playbook manuell"]["performance"]["expectancy_value"] == -300.0
    assert "Paper-Autopilot: 1 geschlossene Paper-Trades" in by_source["Paper-Autopilot"]["summary"]
    assert rows[0]["entry_source_label"] == "Paper-Autopilot"


def test_news_evidence_learning_requires_sample_and_adjusts_conservatively() -> None:
    service = PaperTradingService.__new__(PaperTradingService)

    def news_trade(index: int, pnl: float, publisher: str = "Reuters") -> Dict[str, Any]:
        return {
            "id": f"news-{index}",
            "status": "closed",
            "setup_type": "confirmed_news_event",
            "realized_pnl_pct": pnl,
            "realized_pnl_value": pnl * 100,
            "exit_reason": "managed_news_reaction_failed" if pnl < 0 else "managed_target_hit",
            "trade_ticket": {
                "news_evidence": {
                    "publisher": publisher,
                    "event_type": "earnings",
                    "source_url": "https://www.reuters.com/markets/qa/",
                }
            },
        }

    early = service._build_news_evidence_performance([news_trade(i, -1.0) for i in range(9)])
    assert early["sources"][0]["quality_status"] == "building_evidence"
    assert early["sources"][0]["score_delta"] == 0

    trades = [news_trade(i, 1.0 if i < 3 else -1.0) for i in range(10)]
    performance = service._build_news_evidence_performance(trades)
    reuters = performance["sources"][0]
    earnings = performance["event_types"][0]
    assert reuters["trades"] == 10
    assert reuters["quality_status"] == "downgrade"
    assert reuters["score_delta"] == -6
    assert reuters["reaction_failure_rate"] == 70.0
    assert earnings["score_delta"] == -6
    assert performance["summary"]["minimum_adjustment_sample"] == 10

    playbooks = [
        {
            "id": "news-MSFT-long",
            "setup_type": "confirmed_news_event",
            "score": 90,
            "news_evidence": {"publisher": "Reuters", "event_type": "earnings"},
        }
    ]
    service._apply_news_evidence_learning(playbooks, performance)
    assert playbooks[0]["score"] == 84
    assert playbooks[0]["news_learning_adjustment"]["score_delta"] == -6
    assert playbooks[0]["news_learning_adjustment"]["real_money_ready"] is False


def test_news_shadow_lab_uses_one_canonical_24h_outcome_per_forecast() -> None:
    manager = FakePortfolioManager()
    strict_news = {
        "ticker": "MSFT",
        "ticker_association_basis": "explicit_title_entity",
        "publisher": "Reuters",
        "source_quality": "tier_1",
        "source_url": "https://www.reuters.com/markets/qa/",
        "published_at": "2026-08-01T10:00:00+00:00",
        "age_hours": 2.0,
        "event_type": "earnings",
        "source_evidence": {
            "link_verified": True,
            "original_document_verified": True,
            "source_agreement": "consistent_headline_signal",
        },
        "news_intelligence": {"is_important": True},
        "market_confirmation": {
            "status": "confirmed",
            "expected_headline_direction": "positive",
            "event_window_aligned": True,
        },
    }
    directional_news = {
        "ticker": "MSFT",
        "publisher": "Reuters",
        "source_url": "https://www.reuters.com/markets/qa/",
        "published_at": "2026-08-01T10:00:00+00:00",
        "event_type": "earnings",
    }
    for index in range(11):
        news = strict_news if index < 5 or index == 10 else directional_news
        forecast_id = f"shadow-{index}"
        manager.signal_forecasts.append(
            {
                "id": forecast_id,
                "symbol": "MSFT",
                "direction": "long",
                "setup_type": "top_news_forecast",
                "source_label": "trusted_news",
                "metadata_json": json.dumps({"news_item": news}),
            }
        )
        if index == 10:
            manager.signal_forecast_outcomes.append(
                {"forecast_id": forecast_id, "horizon_hours": 24, "status": "pending"}
            )
            continue
        hit = index < 5 or index in {5, 6}
        move = 1.0 if hit else -1.0
        result = "hit" if hit else "miss"
        manager.signal_forecast_outcomes.extend(
            [
                {
                    "forecast_id": forecast_id,
                    "horizon_hours": 1,
                    "status": "evaluated",
                    "result": result,
                    "performance_pct": move,
                },
                {
                    "forecast_id": forecast_id,
                    "horizon_hours": 24,
                    "status": "evaluated",
                    "result": result,
                    "performance_pct": move,
                },
            ]
        )

    lab = PaperTradingService(manager)._build_news_shadow_lab()
    summary = lab["summary"]
    assert summary["forecasts"] == 11
    assert summary["evaluated_24h"] == 10
    assert summary["pending_24h"] == 1
    assert summary["hit_rate"] == 70.0
    assert summary["avg_directional_move_pct"] == 0.4
    assert summary["strict_gate_lift_pct_points"] == 30.0
    cohorts = {item["label"]: item for item in lab["quality_cohorts"]}
    assert cohorts["strict_gate_confirmed"]["evaluated"] == 5
    assert cohorts["strict_gate_confirmed"]["hit_rate"] == 100.0
    assert cohorts["directional_headline"]["evaluated"] == 5
    assert lab["sources"][0]["evaluated"] == 10
    assert lab["sources"][0]["evidence_status"] == "usable"
    earnings = lab["event_types"][0]
    assert earnings["paper_prior_score_delta"] == 2

    playbooks = [
        {
            "setup_type": "confirmed_news_event",
            "score": 90,
            "news_evidence": {"event_type": "earnings"},
        },
        {
            "setup_type": "confirmed_news_event",
            "score": 84,
            "news_evidence": {"event_type": "earnings"},
            "news_learning_adjustment": {"score_delta": -6},
        },
    ]
    PaperTradingService(manager)._apply_news_shadow_learning(playbooks, lab)
    assert playbooks[0]["score"] == 92
    assert playbooks[0]["news_shadow_prior"]["applied_score_delta"] == 2
    assert playbooks[1]["score"] == 84
    assert playbooks[1]["news_shadow_prior"]["applied_score_delta"] == 0
    assert playbooks[1]["news_shadow_prior"]["direct_trade_evidence_precedence"] is True
    PaperTradingService(manager)._refresh_playbook_decision_state(
        playbooks,
        {"min_score_for_new_trade": 93, "min_score_for_leverage": 95},
    )
    assert playbooks[0]["tradeable"] is False
    assert "Score below minimum trade score 93." in playbooks[0]["do_not_trade_reasons"]
    playbooks[0]["score"] = 94
    PaperTradingService(manager)._refresh_playbook_decision_state(
        playbooks,
        {"min_score_for_new_trade": 93, "min_score_for_leverage": 95},
    )
    assert playbooks[0]["tradeable"] is True
    assert PaperTradingService(manager)._news_shadow_event_prior_delta(
        {
            "evaluated": 27,
            "decisive": 14,
            "hit_rate": 14.3,
            "avg_directional_move_pct": -0.59,
        }
    ) == -4


def test_learning_context_performance_groups_account_state() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    rows = service._build_learning_context_performance(
        [
            {
                "id": "protect-win",
                "status": "closed",
                "realized_pnl_pct": 2.0,
                "realized_pnl_value": 200.0,
                "trade_ticket": {
                    "learning_context": {
                        "autopilot_mode": "learn",
                        "account_day_status": "protect_profit",
                        "account_queue_status": "protect",
                        "risk_multiplier": 0.1,
                    }
                },
            },
            {
                "id": "protect-loss",
                "status": "closed",
                "realized_pnl_pct": -1.0,
                "realized_pnl_value": -100.0,
                "trade_ticket": {
                    "learning_context": {
                        "autopilot_mode": "learn",
                        "account_day_status": "protect_profit",
                        "account_queue_status": "protect",
                        "risk_multiplier": 0.1,
                    }
                },
            },
            {
                "id": "normal-manual",
                "status": "closed",
                "realized_pnl_pct": 5.0,
                "realized_pnl_value": 500.0,
                "trade_ticket": {},
            },
        ]
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["key"] == "protect_profit:protect:learn"
    assert row["trades"] == 2
    assert row["avg_risk_multiplier"] == 0.1
    assert row["performance"]["expectancy_value"] == 50.0
    assert "protect_profit / protect / learn" in row["summary"]


def test_strategy_readiness_requires_positive_money_expectancy() -> None:
    setup_type = "insider_follow"
    trades: List[Dict[str, Any]] = []
    outcomes: List[Dict[str, Any]] = []
    for index in range(18):
        trades.append(
            {
                "id": f"hit-{index}",
                "status": "closed",
                "ticker": "AAPL",
                "setup_type": setup_type,
                "direction": "long",
                "realized_pnl_pct": 1.0,
                "realized_pnl_value": 100.0,
            }
        )
        outcomes.append({"setup_type": setup_type, "result": "hit"})
    for index in range(2):
        trades.append(
            {
                "id": f"miss-{index}",
                "status": "closed",
                "ticker": "AAPL",
                "setup_type": setup_type,
                "direction": "long",
                "realized_pnl_pct": -10.0,
                "realized_pnl_value": -1000.0,
            }
        )
        outcomes.append({"setup_type": setup_type, "result": "hit"})

    rows = StrategyLibrary.build_readiness(trades, outcomes)
    momentum = next(item for item in rows if item["id"] == "momentum_follow_through")
    assert momentum["hit_rate"] == 100.0
    assert momentum["performance"]["expectancy_value"] == -10.0
    assert momentum["performance"]["profit_factor"] == 0.9
    assert momentum["real_world_ready"] is False
    assert momentum["recommendation"] == "continue_learning"
    assert any("Erwartung pro Trade" in gap for gap in momentum["readiness_gaps"])
    assert any("Profit Factor" in gap for gap in momentum["readiness_gaps"])
    assert "Erwartung pro Trade" in momentum["next_step"]


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
    service._get_market_snapshot = lambda ticker, since=None, **kwargs: {  # type: ignore[method-assign]
        "price": 90.0 if ticker == "AAPL" else 100.0,
        "data_as_of": "2026-06-19T08:00:00+00:00",
        "freshness": "fresh",
        "liquidity_status": "strong",
        "age_hours": 1.0,
    }
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
    assert demo["exposure_profile"]["net_direction"] == "net_short"
    assert demo["exposure_profile"]["open_trade_count"] == 1
    assert demo["exposure_profile"]["open_pnl_value"] == 500.0
    short_bucket = next(item for item in demo["exposure_profile"]["buckets"] if item["key"] == "short")
    assert short_bucket["count"] == 1
    assert short_bucket["notional_value"] == 5000.0
    assert short_bucket["pnl_value"] == 500.0
    assert demo["exposure_profile"]["biggest_open_risk"]["ticker"] == "AAPL"
    assert demo["trade_action_queue"]["top_priority"]["ticker"] == "AAPL"
    assert demo["trade_action_queue"]["top_priority"]["direction"] == "short"
    assert demo["trade_action_queue"]["counts"]["exit"] == 1


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
                "quantity": 6000,
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


def test_demo_account_limits_risk_review_to_affected_risk_and_scales_independent_trades() -> None:
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
    assert dashboard["demo_account"]["trade_action_queue"]["status"] == "review"
    assert dashboard["demo_account"]["trade_action_queue"]["top_priority"]["ticker"] == "MSFT"
    assert dashboard["demo_account"]["trade_action_queue"]["counts"]["review"] == 1
    assert dashboard["demo_account"]["review_tickers"] == ["MSFT"]
    assert aapl["demo_tradeable"] is True
    assert aapl["risk_multiplier"] == 0.5
    assert aapl["suggested_max_loss_value"] == 1_875.0
    assert dashboard["auto_selection"]["selected"]

    reviewed_sizing = service._suggest_demo_sizing(
        {
            "ticker": "MSFT",
            "asset_class": "equity",
            "reference_price": 100.0,
            "risk_buffer_pct": 3.5,
            "tradeable": True,
        },
        dashboard["demo_account"],
    )
    assert reviewed_sizing["demo_tradeable"] is False
    assert any("selbst im Risiko-Review" in reason for reason in reviewed_sizing["demo_block_reasons"])

    correlated_crypto_sizing = service._suggest_demo_sizing(
        {
            "ticker": "ETH-USD",
            "asset_class": "crypto",
            "reference_price": 2_000.0,
            "risk_buffer_pct": 5.5,
            "tradeable": True,
        },
        {
            **dashboard["demo_account"],
            "review_tickers": ["BTC-USD"],
            "review_asset_classes": ["crypto"],
        },
    )
    assert correlated_crypto_sizing["demo_tradeable"] is False
    assert any("korreliertes Krypto-Risiko" in reason for reason in correlated_crypto_sizing["demo_block_reasons"])

    created = service.create_trade_from_playbook(
        {"playbook_id": "equity-AAPL-long", "direction": "long", "quantity": 0, "leverage": 1},
        sample_scoreboard(),
        sample_settings(),
    )
    assert created["ticker"] == "AAPL"
    assert created["trade_ticket"]["max_loss_value"] <= 1_875.0


def test_profit_protection_limits_autopilot_to_small_learning() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "near-target",
                "ticker": "MSFT",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_protect",
                "status": "open",
                "opened_at": "2026-06-19T08:00:00",
                "entry_price": 95.0,
                "stop_price": 90.0,
                "target_price": 101.0,
                "quantity": 10,
                "confidence_score": 95,
                "leverage": 1,
            }
        ]
    )
    service = build_service(manager)
    dashboard = service.build_dashboard(sample_scoreboard(), sample_settings())

    assert dashboard["demo_account"]["day_status"] == "protect_profit"
    selection = dashboard["auto_selection"]
    assert selection["selected"] == []
    assert selection["aggressive_exploration"] == []
    assert selection["exploration"]
    rejected = selection["blocker_summary"]["next_best_rejected"]
    assert rejected["missing_to_trade"] == "Gewinnschutz bei offenen Gewinnern prüfen"
    assert rejected["next_action"].startswith("Erst Gewinnschutz")
    assert any(item["category"] == "profit_protection" for item in selection["blocker_summary"]["blocker_groups"])

    executed = service.run_auto_selection(sample_scoreboard(), sample_settings(), execute=True, mode="learn")
    assert executed["opened"]
    opened = executed["opened"][0]
    context = opened["trade_ticket"]["learning_context"]
    assert context["autopilot_mode"] == "learn"
    assert context["account_day_status"] == "protect_profit"
    assert context["account_queue_status"] == "protect"
    assert context["risk_multiplier"] == 0.1
    assert "Lernkontext:" in opened["notes"]


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
        "market_data": {
            "price": 4000.0,
            "data_as_of": "2026-06-19T08:00:00+00:00",
            "freshness": "fresh",
            "liquidity_status": "strong",
        },
        "data_as_of": "2026-06-19T08:00:00+00:00",
    }
    sized = {**playbook, **service._suggest_demo_sizing(playbook, demo_account)}
    sized["trade_ticket"] = service._build_trade_ticket(sized, demo_account)
    assert sized["demo_block_reasons"][0].startswith("Strict-Signalregel:")
    selection = service._build_auto_selection([sized], [], demo_account)
    assert selection["selected"] == []
    assert selection["exploration"][0]["ticker"] == "ETH-USD"
    assert selection["rejected"][0]["learning_block_reasons"] == []
    capital = service._summarize_candidate_capital(selection["exploration"])
    assert capital["count"] == 1
    assert capital["notional_value"] > 0
    assert capital["max_loss_value"] > 0


def test_aggressive_learning_uses_wider_pool_with_capped_risk() -> None:
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
        "id": "equity-AAPL-long-aggressive",
        "ticker": "AAPL",
        "asset_class": "equity",
        "direction": "long",
        "setup_type": "news_momentum",
        "score": 55.0,
        "reference_price": 100.0,
        "risk_buffer_pct": 3.5,
        "tradeable": False,
        "do_not_trade_reasons": ["Score below minimum trade score 78."],
        "thesis": "Early paper-only news momentum test.",
        "decision_framework": {
            "entry_trigger": "AAPL confirms the headline with price and volume.",
            "invalidation": "AAPL loses the trigger zone.",
        },
        "market_data": {
            "price": 100.0,
            "data_as_of": "2026-06-19T08:00:00+00:00",
            "freshness": "fresh",
            "liquidity_status": "strong",
        },
        "data_as_of": "2026-06-19T08:00:00+00:00",
    }
    sized = {**playbook, **service._suggest_demo_sizing(playbook, demo_account)}
    sized["trade_ticket"] = service._build_trade_ticket(sized, demo_account)
    selection = service._build_auto_selection([sized], [], demo_account)

    assert selection["selected"] == []
    assert selection["exploration"] == []
    assert selection["aggressive_learning_min_score"] == 52.0
    assert selection["aggressive_learning_risk_multiplier"] == 0.60
    aggressive = selection["aggressive_exploration"][0]
    assert aggressive["ticker"] == "AAPL"
    assert aggressive["aggressive_learning_mode"] is True
    assert aggressive["risk_multiplier"] == 0.60
    assert aggressive["suggested_notional_value"] == round(float(sized["suggested_notional_value"]) * 0.60, 2)
    assert aggressive["suggested_max_loss_value"] == round(float(sized["suggested_max_loss_value"]) * 0.60, 2)


def test_aggressive_learning_respects_saved_autopilot_settings() -> None:
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
        "id": "equity-HOOD-long-aggressive-custom",
        "ticker": "HOOD",
        "asset_class": "equity",
        "direction": "long",
        "setup_type": "news_momentum",
        "score": 57.0,
        "reference_price": 100.0,
        "risk_buffer_pct": 3.5,
        "tradeable": False,
        "do_not_trade_reasons": ["Score below minimum trade score 78."],
        "thesis": "Custom aggressive paper-only test.",
        "decision_framework": {
            "entry_trigger": "HOOD confirms the headline with price and volume.",
            "invalidation": "HOOD loses the trigger zone.",
        },
        "market_data": {
            "price": 100.0,
            "data_as_of": "2026-06-19T08:00:00+00:00",
            "freshness": "fresh",
            "liquidity_status": "strong",
        },
        "data_as_of": "2026-06-19T08:00:00+00:00",
    }
    sized = {**playbook, **service._suggest_demo_sizing(playbook, demo_account)}
    sized["trade_ticket"] = service._build_trade_ticket(sized, demo_account)

    blocked = service._build_auto_selection(
        [sized],
        [],
        demo_account,
        autopilot_settings={"aggressive_min_score": 58, "aggressive_risk_multiplier": 0.40},
    )
    assert blocked["aggressive_exploration"] == []

    allowed = service._build_auto_selection(
        [sized],
        [],
        demo_account,
        autopilot_settings={"aggressive_min_score": 55, "aggressive_risk_multiplier": 0.40},
    )
    aggressive = allowed["aggressive_exploration"][0]
    assert aggressive["ticker"] == "HOOD"
    assert aggressive["risk_multiplier"] == 0.40
    assert aggressive["suggested_max_loss_value"] == round(float(sized["suggested_max_loss_value"]) * 0.40, 2)
    assert allowed["interesting_now"][0]["ticker"] == "HOOD"


def test_autopilot_profile_summary_explains_risk_and_protection() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    profile = service._build_autopilot_profile_summary(
        {
            "mode": "aggressive_learning",
            "max_trades": 4,
            "strict_min_score": 88,
            "learning_min_score": 60,
            "aggressive_min_score": 55,
            "learning_risk_multiplier": 0.10,
            "aggressive_risk_multiplier": 0.40,
        },
        {
            "risk_budget_per_trade_value": 2_000.0,
            "day_status": "protect_profit",
        },
    )
    assert profile["label"] == "Aggressive Learning"
    assert profile["min_score"] == 55.0
    assert profile["risk_multiplier"] == 0.40
    assert profile["per_trade_risk_value"] == 800.0
    assert profile["planned_run_risk_value"] == 3_200.0
    assert profile["protection_active"] is True
    assert profile["recommended_mode"] == "learn"
    assert profile["recommendation_tone"] == "warning"
    assert "Konto-Schutz" in profile["guardrails"][0]


def test_leverage_product_validation_contract() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    blocked = service.validate_leverage_product_data({})
    assert blocked["valid"] is False
    assert "issuer_required" in blocked["errors"]
    assert "overnight_risk_ack_required" in blocked["errors"]

    valid = service.validate_leverage_product_data(
        {
            "product_type": "knockout",
            "issuer": "QA Bank",
            "strike_or_knockout_level": 205.0,
            "expiry": "2030-01-17",
            "bid": 4.80,
            "ask": 4.95,
            "offered_leverage": 20,
            "distance_to_knockout_pct": 8.0,
            "overnight_risk_ack": True,
        }
    )
    assert valid["valid"] is True
    assert valid["errors"] == []
    assert valid["data"]["spread_pct"] < 6
    assert valid["data"]["offered_leverage"] == 20
    assert valid["data"]["leverage_is_embedded_in_product_price"] is True

    too_wide = service.validate_leverage_product_data(
        {
            "product_type": "option_certificate",
            "issuer": "QA Bank",
            "strike_or_knockout_level": 205.0,
            "expiry": "2030-01-17",
            "bid": 4.00,
            "ask": 4.60,
            "offered_leverage": 12,
            "overnight_risk_ack": True,
        }
    )
    assert too_wide["valid"] is False
    assert "spread_too_wide_over_12_pct" in too_wide["errors"]

    enriched = service._enrich_trade(
        {
            "id": "provider-leverage-pnl",
            "ticker": "GLD",
            "asset_class": "option",
            "direction": "call",
            "status": "closed",
            "entry_price": 5.0,
            "closed_price": 5.5,
            "quantity": 10,
            "leverage": 20,
            "stop_price": 2.5,
            "target_price": 10.0,
            "trade_ticket": {
                "leveraged_product": {
                    "offered_leverage": 20,
                    "leverage_is_embedded_in_product_price": True,
                }
            },
        }
    )
    assert enriched["invested_value"] == 5_000.0
    assert enriched["realized_pnl_value"] == 500.0
    assert enriched["realized_pnl_pct"] == 10.0


def test_market_quality_gate_blocks_stale_and_thin_snapshots() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    stale = {
        "price": 10.0,
        "data_as_of": "2026-01-01T00:00:00+00:00",
        "freshness": "stale",
        "liquidity_status": "adequate",
    }
    thin = {
        "price": 10.0,
        "data_as_of": "2026-06-19T08:00:00+00:00",
        "freshness": "fresh",
        "liquidity_status": "thin",
    }
    assert "market_data_stale" in service._market_snapshot_blockers(stale)
    assert "market_liquidity_too_thin" in service._market_snapshot_blockers(thin)
    assert service._market_snapshot_blockers({}) == ["market_snapshot_missing"]


def test_execution_fill_is_adverse_for_long_and_short() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    market = {"liquidity_status": "strong", "age_hours": 1, "data_as_of": "2026-07-17T09:00:00Z"}
    long_entry = service._simulate_execution_fill(100, "long", "entry", "equity", market, 10, 1)
    long_exit = service._simulate_execution_fill(100, "long", "exit", "equity", market, 10, 1)
    short_entry = service._simulate_execution_fill(100, "short", "entry", "equity", market, 10, 1)
    short_exit = service._simulate_execution_fill(100, "short", "exit", "equity", market, 10, 1)
    put_entry = service._simulate_execution_fill(2.5, "put", "entry", "option", market, 1, 100)
    put_exit = service._simulate_execution_fill(2.5, "put", "exit", "option", market, 1, 100)

    assert long_entry["fill_price"] > 100 > long_exit["fill_price"]
    assert short_entry["fill_price"] < 100 < short_exit["fill_price"]
    assert put_entry["side"] == "buy" and put_entry["fill_price"] > 2.5
    assert put_exit["side"] == "sell" and put_exit["fill_price"] < 2.5
    assert long_entry["estimated_cost_value"] > 0
    assert short_exit["estimated_cost_value"] > 0
    assert service._calc_return_pct(long_entry["fill_price"], long_exit["fill_price"], 1, 1) < 0
    assert service._calc_return_pct(short_entry["fill_price"], short_exit["fill_price"], -1, 1) < 0


def test_demo_exposure_capacity_gates() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    playbook = {
        "ticker": "AAPL",
        "asset_class": "equity",
        "reference_price": 100.0,
        "risk_buffer_pct": 3.5,
        "tradeable": True,
    }
    base_account = {
        "equity": 500_000.0,
        "cash_available_value": 200_000.0,
        "risk_budget_per_trade_value": 1_750.0,
        "risk_budget_per_option_trade_value": 1_250.0,
        "remaining_risk_value": 10_000.0,
        "max_position_value": 50_000.0,
        "max_option_premium_value": 3_750.0,
        "max_ticker_exposure_value": 60_000.0,
        "remaining_gross_exposure_value": 100_000.0,
        "remaining_option_premium_value": 10_000.0,
        "exposure_by_ticker": {},
        "open_trade_slots": 5,
        "day_status": "monitor",
        "learning_feedback": {},
    }

    ticker_limited = service._suggest_demo_sizing(
        playbook,
        {**base_account, "exposure_by_ticker": {"AAPL": 55_000.0}},
    )
    assert ticker_limited["suggested_notional_value"] == 5_000.0
    assert ticker_limited["remaining_ticker_capacity_value"] == 5_000.0

    gross_blocked = service._suggest_demo_sizing(
        playbook,
        {**base_account, "remaining_gross_exposure_value": 0.0},
    )
    assert gross_blocked["demo_tradeable"] is False
    assert "Gross exposure budget is exhausted." in gross_blocked["demo_block_reasons"]

    cash_blocked = service._suggest_demo_sizing(
        playbook,
        {**base_account, "cash_available_value": 0.0},
    )
    assert cash_blocked["demo_tradeable"] is False
    assert "Demo cash capacity is exhausted." in cash_blocked["demo_block_reasons"]

    ticker_blocked = service._suggest_demo_sizing(
        playbook,
        {**base_account, "exposure_by_ticker": {"AAPL": 60_000.0}},
    )
    assert ticker_blocked["demo_tradeable"] is False
    assert "Ticker exposure budget is exhausted." in ticker_blocked["demo_block_reasons"]

    option_blocked = service._suggest_demo_sizing(
        {**playbook, "asset_class": "option", "direction": "call", "reference_price": 2.5, "contract_multiplier": 100},
        {**base_account, "remaining_option_premium_value": 0.0},
    )
    assert option_blocked["demo_tradeable"] is False
    assert "Option premium budget is exhausted." in option_blocked["demo_block_reasons"]
    assert service._auto_rejection_category("Gross exposure budget is exhausted.") == "capacity"
    assert "Gesamt-Exposure" in service._auto_rejection_display_reason("Gross exposure budget is exhausted.")


def test_paper_risk_circuit_breaker() -> None:
    service = PaperTradingService.__new__(PaperTradingService)
    config = {
        "daily_loss_limit_pct": 1.0,
        "max_drawdown_pct": 8.0,
        "max_consecutive_losses": 3,
        "loss_streak_cooldown_hours": 24.0,
    }
    recent_losses = [
        {
            "status": "closed",
            "closed_at": (datetime.now() - timedelta(minutes=index + 1)).isoformat(),
            "realized_pnl_value": -1_000.0,
        }
        for index in range(3)
    ]
    streak = service._build_paper_risk_circuit(recent_losses, 497_000.0, 500_000.0, config)
    assert streak["active"] is True
    assert streak["status"] == "paused"
    assert streak["consecutive_losses"] == 3
    assert streak["cooldown_until"]
    assert "Paper loss streak cooldown is active." in streak["reasons"]

    daily = service._build_paper_risk_circuit(
        [{"status": "closed", "closed_at": datetime.now().isoformat(), "realized_pnl_value": -6_000.0}],
        494_000.0,
        500_000.0,
        config,
    )
    assert daily["active"] is True
    assert "Daily paper loss limit reached." in daily["reasons"]

    drawdown = service._build_paper_risk_circuit(
        [
            {
                "status": "closed",
                "closed_at": (datetime.now() - timedelta(hours=48)).isoformat(),
                "realized_pnl_value": -40_000.0,
            }
        ],
        460_000.0,
        500_000.0,
        config,
    )
    assert drawdown["active"] is False
    assert drawdown["status"] == "reduced_risk"
    assert drawdown["current_drawdown_pct"] == 8.0
    assert drawdown["risk_multiplier"] == 0.25

    account = {
        "equity": 500_000.0,
        "cash_available_value": 500_000.0,
        "risk_budget_per_trade_value": 1_750.0,
        "remaining_risk_value": 15_000.0,
        "max_position_value": 50_000.0,
        "remaining_gross_exposure_value": 300_000.0,
        "max_ticker_exposure_value": 60_000.0,
        "exposure_by_ticker": {},
        "open_trade_slots": 5,
        "day_status": "monitor",
        "learning_feedback": {},
    }
    playbook = {
        "ticker": "AAPL",
        "asset_class": "equity",
        "reference_price": 100.0,
        "risk_buffer_pct": 3.5,
        "tradeable": True,
    }
    paused = service._suggest_demo_sizing(playbook, {**account, "risk_circuit": streak})
    assert paused["demo_tradeable"] is False
    assert any(reason.startswith("Paper risk circuit:") for reason in paused["demo_block_reasons"])

    reduced = service._suggest_demo_sizing(playbook, {**account, "risk_circuit": drawdown})
    assert reduced["demo_tradeable"] is True
    assert reduced["risk_multiplier"] == 0.25
    assert reduced["suggested_max_loss_value"] == 437.5


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


def test_closed_trade_cannot_be_closed_twice() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "closed-once",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_idempotent_close",
                "status": "closed",
                "opened_at": "2026-06-18T08:00:00",
                "closed_at": "2026-06-19T08:00:00",
                "entry_price": 100.0,
                "closed_price": 104.0,
                "stop_price": 95.0,
                "target_price": 104.0,
                "quantity": 10,
                "exit_reason": "first_exit",
                "lessons_learned": "First close must remain authoritative.",
            }
        ]
    )
    service = build_service(manager)

    try:
        service.close_trade(
            "closed-once",
            closed_price=1.0,
            exit_reason="duplicate_exit",
            lessons_learned="Must not be saved.",
        )
        raise AssertionError("Duplicate paper close unexpectedly succeeded.")
    except PaperTradeAlreadyClosedError:
        pass

    persisted = manager.trades[0]
    assert persisted["closed_at"] == "2026-06-19T08:00:00"
    assert persisted["closed_price"] == 104.0
    assert persisted["exit_reason"] == "first_exit"
    assert persisted["lessons_learned"] == "First close must remain authoritative."


def test_managed_exit_tolerates_concurrent_close() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "concurrent-close",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_concurrent_close",
                "status": "open",
                "opened_at": "2026-06-18T08:00:00",
                "entry_price": 90.0,
                "stop_price": 85.0,
                "target_price": 95.0,
                "quantity": 10,
                "confidence_score": 90,
                "leverage": 1,
            }
        ]
    )
    service = build_service(manager)
    manager.close_paper_trade = lambda *args, **kwargs: None  # type: ignore[method-assign]

    result = service.close_trades_on_management_exits()

    assert result["status"] == "ok"
    assert result["closed"] == []
    assert result["errors"] == []
    assert result["skipped"] == [
        {
            "id": "concurrent-close",
            "ticker": "AAPL",
            "status": "already_closed",
        }
    ]


def test_option_holding_period_expires_without_fabricated_quote() -> None:
    opened_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    manager = FakePortfolioManager(
        [
            {
                "id": "expired-option",
                "ticker": "AAPL",
                "asset_class": "option",
                "direction": "call",
                "option_type": "call",
                "setup_type": "qa_option_time_exit",
                "status": "open",
                "opened_at": opened_at,
                "entry_price": 2.5,
                "stop_price": 1.25,
                "target_price": 5.0,
                "quantity": 2,
                "contract_multiplier": 100,
                "max_holding_days": 7,
                "confidence_score": 90,
                "leverage": 1,
            }
        ]
    )
    service = build_service(manager)

    enriched = service._enrich_trade(manager.trades[0])
    management = enriched["management_plan"]

    assert enriched["current_price"] is None
    assert management["status"] == "holding_period_expired"
    assert management["action"] == "price_and_close_review"
    assert management["decision_grade"] == "exit"
    assert management["max_holding_days"] == 7
    assert management["trigger_reference_price"] is None
    assert "kein erfundener Auto-Exit" in management["summary"]

    managed_exit = service.close_trades_on_management_exits()
    assert managed_exit["status"] == "ok"
    assert managed_exit["closed"] == []
    assert managed_exit["errors"] == []
    assert managed_exit["skipped"][0]["status"] == "holding_period_expired"
    assert manager.trades[0]["status"] == "open"


def test_managed_exit_applies_execution_cost_once() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "managed-target",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_managed_exit",
                "status": "open",
                "opened_at": "2026-06-18T08:00:00",
                "entry_price": 90.0,
                "stop_price": 85.0,
                "target_price": 95.0,
                "quantity": 10,
                "confidence_score": 90,
                "leverage": 1,
                "notes": "",
                "exit_reason": "",
                "lessons_learned": "",
                "trade_ticket": {
                    "execution_model": {
                        "entry": {
                            "reference_price": 89.9281,
                            "fill_price": 90.0,
                            "cost_bps": 8.0,
                        }
                    }
                },
            }
        ]
    )
    service = build_service(manager)
    result = service.close_trades_on_management_exits()

    assert result["status"] == "ok"
    assert len(result["closed"]) == 1
    closed = result["closed"][0]
    assert closed["closed_price"] == 99.92
    assert closed["exit_reason"] == "managed_target_hit"
    exit_execution = closed["trade_ticket"]["execution_model"]["exit"]
    assert exit_execution["reference_price"] == 100.0
    assert exit_execution["fill_price"] == 99.92
    assert exit_execution["estimated_cost_value"] == 0.8


def test_managed_exit_uses_intraday_trigger_price() -> None:
    manager = FakePortfolioManager(
        [
            {
                "id": "managed-intraday-target",
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "qa_intraday_exit",
                "status": "open",
                "opened_at": "2026-06-18T08:00:00",
                "entry_price": 100.0,
                "stop_price": 95.0,
                "target_price": 102.0,
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
    service._get_market_snapshot = lambda ticker, since=None, **kwargs: {  # type: ignore[method-assign]
        "price": 100.5,
        "data_as_of": "2026-06-19T08:15:00+00:00",
        "source": "qa_intraday",
        "interval": "5m",
        "age_hours": 0.1,
        "freshness": "fresh",
        "liquidity_status": "strong",
        "monitoring_low": 99.0,
        "monitoring_high": 103.0,
        "monitoring_trigger": "target_hit",
        "monitoring_triggered_at": "2026-06-19T08:05:00",
        "monitoring_trigger_price": 102.0,
    }

    result = service.close_trades_on_management_exits()

    assert result["status"] == "ok"
    assert len(result["closed"]) == 1
    closed = result["closed"][0]
    assert closed["closed_price"] == 102.0
    assert closed["closed_price"] != 100.5
    assert closed["exit_reason"] == "managed_target_hit"
    assert "Trigger reference: 102.0000" in closed["notes"]


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


def test_intraday_market_snapshot_tracks_range_since_entry() -> None:
    manager = FakePortfolioManager()
    service = PaperTradingService(manager)  # type: ignore[arg-type]
    now = datetime.now().astimezone()
    index = pd.date_range(
        start=now - timedelta(minutes=15),
        periods=4,
        freq="5min",
    )
    intraday = pd.DataFrame(
        {
            "Close": [100.0, 101.0, 99.0, 100.5],
            "High": [100.5, 103.0, 100.0, 101.0],
            "Low": [99.5, 100.5, 94.0, 99.0],
            "Volume": [100_000, 120_000, 110_000, 90_000],
        },
        index=index,
    )

    class IntradayTicker:
        def history(self, *, period: str, interval: str):
            assert period == "5d"
            assert interval == "5m"
            return intraday

    with patch("src.paper_trading_service.yf.Ticker", return_value=IntradayTicker()):
        snapshot = service._get_market_snapshot(
            "AAPL",
            since=(now - timedelta(minutes=11)).isoformat(),
            stop_price=95.0,
            target_price=102.0,
            direction="long",
        )
        stop_snapshot = service._get_market_snapshot(
            "AAPL",
            since=(now - timedelta(minutes=11)).isoformat(),
            stop_price=95.0,
            target_price=110.0,
            direction="long",
        )

    assert snapshot["source"] == "yfinance_intraday"
    assert snapshot["interval"] == "5m"
    assert snapshot["price"] == 100.5
    assert snapshot["monitoring_low"] == 94.0
    assert snapshot["monitoring_high"] == 103.0
    assert snapshot["monitoring_trigger"] == "target_hit"
    assert snapshot["monitoring_triggered_at"]
    assert snapshot["monitoring_trigger_price"] == 102.0
    assert snapshot["average_volume_5d"] == 420_000.0
    assert snapshot["liquidity_status"] == "strong"

    management = service._build_trade_management_plan(
        {
            "entry_price": 100.0,
            "current_price": 100.5,
            "stop_price": 95.0,
            "target_price": 102.0,
            "direction": "long",
            "current_market_data": snapshot,
            "unrealized_pnl_pct": 0.5,
        }
    )
    assert management["status"] == "target_hit"
    assert management["triggered_at"] == snapshot["monitoring_triggered_at"]
    assert management["trigger_reference_price"] == 102.0

    stop_management = service._build_trade_management_plan(
        {
            "entry_price": 100.0,
            "current_price": 100.5,
            "stop_price": 95.0,
            "target_price": 110.0,
            "direction": "long",
            "current_market_data": stop_snapshot,
            "unrealized_pnl_pct": 0.5,
        }
    )
    assert stop_snapshot["monitoring_trigger"] == "stop_hit"
    assert stop_management["status"] == "stop_hit"


def test_intraday_same_bar_conflict_prefers_stop() -> None:
    manager = FakePortfolioManager()
    service = PaperTradingService(manager)  # type: ignore[arg-type]
    now = datetime.now().astimezone()
    index = pd.date_range(
        start=now - timedelta(minutes=5),
        periods=2,
        freq="5min",
    )
    intraday = pd.DataFrame(
        {
            "Close": [100.0, 100.5],
            "Open": [93.0, 100.0],
            "High": [103.0, 101.0],
            "Low": [94.0, 99.0],
            "Volume": [100_000, 90_000],
        },
        index=index,
    )

    class IntradayTicker:
        def history(self, *, period: str, interval: str):
            assert period == "5d"
            assert interval == "5m"
            return intraday

    with patch("src.paper_trading_service.yf.Ticker", return_value=IntradayTicker()):
        snapshot = service._get_market_snapshot(
            "AAPL",
            since=(now - timedelta(minutes=6)).isoformat(),
            stop_price=95.0,
            target_price=102.0,
            direction="long",
        )

    assert snapshot["monitoring_trigger"] == "stop_hit"
    assert snapshot["monitoring_trigger_price"] == 93.0
    management = service._build_trade_management_plan(
        {
            "entry_price": 100.0,
            "current_price": 100.5,
            "stop_price": 95.0,
            "target_price": 102.0,
            "direction": "long",
            "current_market_data": snapshot,
            "unrealized_pnl_pct": 0.5,
        }
    )
    assert management["status"] == "stop_hit"
    assert management["trigger_reference_price"] == 93.0


def test_market_snapshot_falls_back_to_daily_data() -> None:
    manager = FakePortfolioManager()
    service = PaperTradingService(manager)  # type: ignore[arg-type]
    index = pd.date_range(
        start=datetime.now().astimezone() - timedelta(days=4),
        periods=5,
        freq="1d",
    )
    daily = pd.DataFrame(
        {
            "Close": [98.0, 99.0, 100.0, 101.0, 102.0],
            "High": [99.0, 100.0, 101.0, 102.0, 103.0],
            "Low": [97.0, 98.0, 99.0, 100.0, 101.0],
            "Volume": [1_000_000] * 5,
        },
        index=index,
    )
    calls: List[str] = []

    class FallbackTicker:
        def history(self, *, period: str, interval: str):
            calls.append(interval)
            if interval == "5m":
                raise RuntimeError("qa intraday provider outage")
            return daily

    with patch("src.paper_trading_service.yf.Ticker", return_value=FallbackTicker()):
        snapshot = service._get_market_snapshot("AAPL")
        cached_snapshot = service._get_market_snapshot("AAPL")

    assert calls == ["5m", "1d"]
    assert snapshot["source"] == "yfinance_daily"
    assert snapshot["interval"] == "1d"
    assert snapshot["price"] == 102.0
    assert snapshot["monitoring_low"] is None
    assert snapshot["monitoring_high"] is None
    assert cached_snapshot["price"] == 102.0


if __name__ == "__main__":
    test_equity_paper_leverage_is_quality_gated_and_risk_neutral()
    test_confirmed_news_requires_full_evidence_chain()
    test_news_trade_management_exits_failed_reaction_and_reviews_stall()
    test_news_management_auto_closes_reaction_and_equity_time_exits()
    test_demo_account_sizing()
    test_realized_return_uses_account_equity()
    test_performance_metrics_expose_bad_payoff_despite_high_win_rate()
    test_entry_source_performance_separates_manual_and_autopilot()
    test_news_evidence_learning_requires_sample_and_adjusts_conservatively()
    test_news_shadow_lab_uses_one_canonical_24h_outcome_per_forecast()
    test_learning_context_performance_groups_account_state()
    test_strategy_readiness_requires_positive_money_expectancy()
    test_short_trade_money_flow_and_demo_equity()
    test_put_learning_inverts_underlying_move()
    test_demo_account_blocks_when_open_risk_is_exhausted()
    test_demo_account_limits_risk_review_to_affected_risk_and_scales_independent_trades()
    test_profit_protection_limits_autopilot_to_small_learning()
    test_learning_feedback_tracks_missing_journals()
    test_auto_rejection_summary_prefers_fixable_candidate()
    test_strict_score_block_does_not_block_learning_candidate()
    test_aggressive_learning_uses_wider_pool_with_capped_risk()
    test_aggressive_learning_respects_saved_autopilot_settings()
    test_autopilot_profile_summary_explains_risk_and_protection()
    test_leverage_product_validation_contract()
    test_market_quality_gate_blocks_stale_and_thin_snapshots()
    test_execution_fill_is_adverse_for_long_and_short()
    test_demo_exposure_capacity_gates()
    test_paper_risk_circuit_breaker()
    test_close_trade_auto_documents_profitable_exit()
    test_closed_trade_cannot_be_closed_twice()
    test_managed_exit_tolerates_concurrent_close()
    test_option_holding_period_expires_without_fabricated_quote()
    test_managed_exit_applies_execution_cost_once()
    test_managed_exit_uses_intraday_trigger_price()
    test_outcome_learning_penalizes_weak_setups()
    test_intraday_market_snapshot_tracks_range_since_entry()
    test_intraday_same_bar_conflict_prefers_stop()
    test_market_snapshot_falls_back_to_daily_data()
    print("qa_paper_demo_account: ok")
