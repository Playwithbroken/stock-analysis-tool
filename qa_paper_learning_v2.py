from __future__ import annotations

import os
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "paper-learning-v2.db")

        from src.paper_learning_service import FEATURE_SCHEMA, PaperLearningService
        from src.paper_trading_service import PaperTradingService
        from src.storage import PortfolioManager

        manager = PortfolioManager()
        service = PaperLearningService(manager)
        ticket = {
            "ticket_id": "ticket-1",
            "instrument": "AAPL",
            "asset_class": "equity",
            "direction": "long",
            "status": "paper_ready",
            "paper_ready": True,
            "entry_condition": "Breakout with volume confirmation",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "target_1": 107.0,
            "target_2": 110.0,
            "quantity": 10,
            "notional_value": 1000,
            "max_loss_value": 50,
            "risk_reward": 2.0,
            "thesis": "Verified quality and momentum setup",
            "invalidation": "Close below 95",
            "strategy_id": "quality_momentum",
            "source_label": "verified_fixture",
            "data_as_of": datetime.now(timezone.utc).isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "market_data": {"source": "verified_fixture", "data_as_of": datetime.now(timezone.utc).isoformat(), "price": 100, "liquidity_status": "strong"},
            "entry_market_regime": {"trend": "up", "volatility": "normal"},
            "validation": {"valid": True, "errors": [], "warnings": [], "blocked_reasons": []},
        }
        playbook = {
            "id": "ticket-1",
            "ticker": "AAPL",
            "asset_class": "equity",
            "direction": "long",
            "setup_type": "quality_momentum",
            "score": 82,
            "suggested_quantity": 10,
            "correlation_check": {"blocked": False},
        }
        snapshot = service.build_feature_snapshot(playbook, ticket)
        ticket["learning_feature_snapshot"] = snapshot
        require(snapshot.get("schema_version") == FEATURE_SCHEMA, failures, "feature schema missing")
        require(bool(snapshot.get("snapshot_hash")), failures, "snapshot hash missing")
        require(snapshot.get("gate_decision", {}).get("real_money_execution_allowed") is False, failures, "snapshot enabled real money")

        etf_snapshot = service.build_feature_snapshot({
            **playbook,
            "asset_class": "etf",
            "asset_evidence": {
                "source": "verified_fund_fixture",
                "data_as_of": ticket["data_as_of"],
                "category": "US Large Blend",
                "expense_ratio": 0.0003,
                "total_assets": 500_000_000_000,
            },
        }, {**ticket, "asset_class": "etf", "instrument": "VOO"})
        require(etf_snapshot.get("asset_features", {}).get("fields", {}).get("expense_ratio") == 0.0003, failures, "ETF expense ratio missing")
        require("replication_method" in etf_snapshot.get("asset_features", {}).get("availability", {}).get("research_missing", []), failures, "ETF missing research was imputed")

        crypto_snapshot = service.build_feature_snapshot({
            **playbook,
            "asset_class": "crypto",
            "asset_evidence": {
                "source": "verified_crypto_fixture",
                "data_as_of": ticket["data_as_of"],
                "trading_pair": "BTC-USD",
                "price": 50_000,
            },
        }, {**ticket, "asset_class": "crypto", "instrument": "BTC-USD"})
        crypto_fields = crypto_snapshot.get("asset_features", {}).get("fields", {})
        require(crypto_fields.get("trading_pair") == "BTC-USD", failures, "crypto pair identity missing")
        require(crypto_fields.get("quote_currency") == "USD", failures, "crypto quote currency missing")
        require("execution_venue" in crypto_snapshot.get("asset_features", {}).get("availability", {}).get("research_missing", []), failures, "crypto venue absence was hidden")

        equity_snapshot = service.build_feature_snapshot({
            **playbook,
            "asset_class": "equity",
            "asset_evidence": {"market_cap": 3_000_000_000, "source": "verified_equity_fixture"},
        }, ticket)
        require(equity_snapshot.get("asset_features", {}).get("fields", {}).get("market_cap") == 3_000_000_000, failures, "equity market cap missing")

        cost_ticket = {
            **ticket,
            "execution_model": {
                "entry": {
                    "reference_price": 100.0,
                    "fill_price": 100.1,
                    "cost_bps": 10.0,
                    "estimated_cost_value": 1.0,
                    "estimated_fee_value": 0.2,
                    "estimated_slippage_value": 0.8,
                }
            },
        }
        cost_snapshot = service.build_feature_snapshot({
            **playbook,
            "asset_evidence": {"market_cap": 3_000_000_000, "source": "verified_equity_fixture"},
        }, cost_ticket)
        cost_ticket["learning_feature_snapshot"] = cost_snapshot
        cost_ticket["execution_model"]["exit"] = {
            "reference_price": 110.0,
            "fill_price": 109.8,
            "cost_bps": 18.18,
            "estimated_cost_value": 2.0,
            "estimated_fee_value": 0.2,
            "estimated_slippage_value": 1.8,
        }
        cost_attribution = service.build_attribution({
            "id": "cost-trade",
            "entry_price": 100.1,
            "closed_price": 109.8,
            "stop_price": 95,
            "target_price": 108,
            "quantity": 10,
            "contract_multiplier": 1,
            "direction": "long",
            "opened_at": "2026-01-01T09:00:00+00:00",
            "closed_at": "2026-01-02T09:00:00+00:00",
            "exit_reason": "target reached",
            "lessons_learned": "Plan and exit were followed.",
            "trade_ticket": cost_ticket,
        }, [])
        cost_metrics = cost_attribution.get("metrics") or {}
        require(cost_metrics.get("gross_pnl_pct") == 10.0, failures, "gross attribution is wrong")
        require(cost_metrics.get("execution_cost_value") == 3.0, failures, "round-trip costs are wrong")
        require(cost_metrics.get("holding_hours") == 24.0, failures, "holding duration is wrong")
        require(cost_metrics.get("target_reached") is True, failures, "target outcome was not classified")
        require(cost_attribution.get("process_quality") == "good_process_good_outcome", failures, "good process was not separated from outcome")

        first_trade_id = None
        now = datetime.now(timezone.utc)
        for index in range(8):
            row_ticket = {**ticket, "ticket_id": f"ticket-{index}"}
            row_ticket["learning_feature_snapshot"] = service.build_feature_snapshot({**playbook, "id": f"ticket-{index}"}, row_ticket)
            trade = manager.create_paper_trade({
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "quality_momentum",
                "thesis": "Verified quality and momentum setup",
                "entry_price": 100,
                "stop_price": 95,
                "target_price": 110,
                "quantity": 10,
                "trade_ticket": row_ticket,
            })
            first_trade_id = first_trade_id or trade["id"]
            manager.close_paper_trade(trade["id"], 94.0, exit_reason="signal.no_follow_through", trade_ticket=row_ticket)
            manager.upsert_paper_trade_outcomes(trade["id"], [{
                "id": f"{trade['id']}-24h",
                "horizon_hours": 24,
                "due_at": (now - timedelta(hours=1)).isoformat(),
                "status": "evaluated",
                "result": "miss",
                "checked_at": now.isoformat(),
                "check_price": 94.0,
                "performance_pct": -6.0,
                "benchmark_symbol": "SPY",
                "benchmark_entry_price": 400.0,
                "benchmark_check_price": 404.0,
                "benchmark_return_pct": 1.0,
                "active_return_pct": -7.0,
                "notes": "deterministic loss fixture",
                "error_tag": "weak_follow_through",
            }])

        stored = next(item for item in manager.list_paper_trades(limit=20) if item["id"] == first_trade_id)
        changed = dict(stored["trade_ticket"])
        changed["learning_feature_snapshot"] = {**changed["learning_feature_snapshot"], "snapshot_hash": "tampered"}
        try:
            manager.update_paper_trade_ticket(first_trade_id, changed, open_only=False)
            failures.append("immutable feature snapshot accepted a mutation")
        except ValueError:
            pass

        refresh = service.refresh_learning_state()
        require(refresh.get("closed_trades_attributed") == 8, failures, "closed trades were not attributed")
        dashboard = service.build_dashboard()
        require(len(dashboard.get("recent_runs") or []) >= 1, failures, "learning run history was not persisted")
        require((dashboard.get("recent_runs") or [{}])[0].get("status") == "ok", failures, "successful run history status is wrong")
        require(dashboard.get("summary", {}).get("attributed_trades") == 8, failures, "dashboard attribution count wrong")
        require(dashboard.get("summary", {}).get("missing_asset_features") == 8, failures, "asset data gaps were hidden")
        require(dashboard.get("summary", {}).get("shadow_rules") == 1, failures, "negative segment did not create one shadow rule")
        require(len(dashboard.get("hypotheses") or []) == 1, failures, "negative segment hypothesis missing or duplicated")
        hypothesis = (dashboard.get("hypotheses") or [{}])[0]
        require(len((hypothesis.get("evidence") or {}).get("trade_ids") or []) == 8, failures, "hypothesis trade evidence missing")
        require(bool(hypothesis.get("alternative_explanation")), failures, "hypothesis alternative explanation missing")
        require(bool(hypothesis.get("expires_at")), failures, "hypothesis expiry missing")
        learning_segment = (dashboard.get("segments") or [{}])[0]
        require(learning_segment.get("sample_unit") == "closed_trade", failures, "segment sample is not trade-based")
        require(learning_segment.get("sample_size") == 8, failures, "closed trades were double-counted in segment")
        require(learning_segment.get("expectancy_pct") == -6.0, failures, "segment expectancy is wrong")
        require(learning_segment.get("avg_active_return_pct") == -7.0, failures, "benchmark-relative segment return is wrong")
        require(learning_segment.get("benchmark_coverage_pct") == 100.0, failures, "benchmark coverage is wrong")
        require(learning_segment.get("segment", {}).get("regime_trend") == "up", failures, "entry trend regime was not segmented")
        require(learning_segment.get("segment", {}).get("regime_volatility") == "normal", failures, "entry volatility regime was not segmented")
        require(learning_segment.get("regime_complete") is True, failures, "complete market regime was marked incomplete")
        require((learning_segment.get("hit_rate_interval") or {}).get("method") == "wilson_95", failures, "segment uncertainty missing")
        require((dashboard.get("policy") or {}).get("real_money_execution_allowed") is False, failures, "learning policy enabled real money")
        require(
            (dashboard.get("policy") or {}).get("min_good_process_rate") == 80.0,
            failures,
            "process-quality promotion gate missing",
        )
        operations = dashboard.get("operations") or {}
        require(operations.get("missing_journals") == 8, failures, "missing journals were not surfaced")
        require(
            (operations.get("next_action") or {}).get("code") == "complete_journals",
            failures,
            "operational next action did not prioritize missing journals",
        )
        require(operations.get("paper_only") is True, failures, "operations lost paper-only scope")
        trade_detail = service.build_trade_detail(first_trade_id)
        require(trade_detail.get("snapshot_integrity", {}).get("status") == "valid", failures, "stored snapshot hash verification failed")
        require(trade_detail.get("original_plan", {}).get("stop_price") == 95.0, failures, "trade detail lost original plan")
        require(len(trade_detail.get("outcomes") or []) == 1, failures, "trade detail outcome timeline is wrong")
        require(trade_detail.get("decision_scope", {}).get("real_money_execution_allowed") is False, failures, "trade detail enabled real money")

        rule = (dashboard.get("rules") or [None])[0]
        if rule:
            try:
                service.review_rule(rule["id"], "pause", "")
                failures.append("rule action without review reason was accepted")
            except ValueError:
                pass
            try:
                service.review_rule(rule["id"], "activate_paper", "QA must remain shadow without future evidence")
                failures.append("shadow rule activated without future evidence")
            except ValueError:
                pass
            paused = service.review_rule(rule["id"], "pause", "QA pause")
            require(paused.get("rule", {}).get("status") == "paused", failures, "paper rule pause failed")
            require(bool(paused.get("audit", {}).get("event_hash")), failures, "rule change was not audited")
            preview = service.rollback_preview(rule["id"])
            require(preview.get("current", {}).get("status") == "paused", failures, "rollback preview current status is wrong")
            require(preview.get("restore", {}).get("status") == "shadow", failures, "rollback preview did not find previous state")
            rolled_back = service.review_rule(rule["id"], "rollback", "QA restores previous shadow state")
            require(rolled_back.get("rule", {}).get("status") == "shadow", failures, "rollback did not restore previous status")
            require(
                rolled_back.get("rule", {}).get("evaluation") == rule.get("evaluation"),
                failures,
                "rollback did not restore previous evaluation exactly",
            )
            history = manager.list_paper_learning_rule_history(rule_id=rule["id"], limit=10)
            require([item.get("action") for item in history[:2]] == ["rollback", "pause"], failures, "immutable rollback history is incomplete")
            require(bool(rolled_back.get("audit", {}).get("event_hash")), failures, "rollback was not audited")

        class ActiveRuleFixture:
            @staticmethod
            def list_paper_learning_rules(limit=1000):
                return [{
                    "id": "active-rule-1",
                    "hypothesis_id": "hypothesis-1",
                    "status": "active_paper",
                    "rule": {"score_delta": -20, "paper_risk_multiplier_cap": 0.25},
                }]

            @staticmethod
            def list_paper_learning_hypotheses(limit=1000):
                return [{
                    "id": "hypothesis-1",
                    "statement": "Weak follow-through requires a lower paper score and risk cap.",
                    "segment": {
                        "setup_type": "quality_momentum",
                        "asset_class": "equity",
                        "regime_trend": "up",
                        "regime_volatility": "normal",
                    },
                }]

        active_playbook = {
            "setup_type": "quality_momentum",
            "asset_class": "equity",
            "score": 80,
            "market_regime": {"trend": "bullish", "volatility": "moderate"},
        }
        PaperLearningService(ActiveRuleFixture()).apply_active_rules([active_playbook])
        require(active_playbook.get("score") == 72, failures, "active rule score cap was not applied")
        require(
            active_playbook.get("learning_rule_risk_multiplier_cap") == 0.25,
            failures,
            "active rule risk cap was not applied",
        )
        require(
            (active_playbook.get("learning_v2_adjustment") or {}).get("real_money_execution_allowed") is False,
            failures,
            "active learning rule enabled real money",
        )
        mismatched_regime_playbook = {
            "setup_type": "quality_momentum",
            "asset_class": "equity",
            "score": 80,
            "market_regime": {"trend": "down", "volatility": "high"},
        }
        PaperLearningService(ActiveRuleFixture()).apply_active_rules([mismatched_regime_playbook])
        require(mismatched_regime_playbook.get("score") == 80, failures, "regime-specific rule leaked into another regime")
        unknown_regime_attributions = [{
            "trade_id": f"unknown-regime-{index}",
            "ticker": "AAPL",
            "asset_class": "equity",
            "direction": "long",
            "setup_type": "quality_momentum",
            "process_quality": "good_process_bad_outcome",
            "metrics": {"net_pnl_pct": -2.0},
            "evidence": {"market_regime": {}},
        } for index in range(8)]
        unknown_segments = PaperLearningService._attribution_segment_rows(unknown_regime_attributions)
        require((unknown_segments or [{}])[0].get("regime_complete") is False, failures, "unknown market regime was treated as complete")
        require(not PaperLearningService.build_hypotheses(unknown_segments), failures, "unknown market regime created a learning rule")

        benchmark_service = PaperTradingService.__new__(PaperTradingService)
        benchmark_service._get_market_snapshot = lambda symbol: {"price": 110.0, "source": "qa", "data_as_of": now.isoformat()}
        benchmark_outcome = benchmark_service._paper_benchmark_outcome({
            "benchmark_symbol": "SPY",
            "benchmark_entry_price": 100.0,
            "direction": "long",
        }, 15.0)
        require(benchmark_outcome.get("benchmark_return_pct") == 10.0, failures, "benchmark return calculation is wrong")
        require(benchmark_outcome.get("active_return_pct") == 5.0, failures, "active return calculation is wrong")
        require(
            PaperTradingService._paper_benchmark_identity("ETH-USD", "crypto")[0] == "BTC-USD",
            failures,
            "crypto benchmark mapping is wrong",
        )
        require(
            PaperTradingService._paper_benchmark_identity("AAPL", "option")[0] is None,
            failures,
            "option benchmark was presented without delta adjustment",
        )

        class ActiveMonitorFixture:
            def __init__(self):
                self.rule = {
                    "id": "active-monitor-rule",
                    "hypothesis_id": "monitor-hypothesis",
                    "version": 1,
                    "status": "active_paper",
                    "rule": {"score_delta": -4, "paper_risk_multiplier_cap": 0.5},
                    "baseline": {},
                    "evaluation": {"promotion_checks": {}},
                }
                self.history = []

            def list_paper_learning_rules(self, limit=500):
                return [self.rule]

            def update_paper_learning_rule_status(self, rule_id, status, evaluation=None):
                self.rule = {**self.rule, "status": status, "evaluation": evaluation or {}}
                return self.rule

            @staticmethod
            def record_decision_audit(**kwargs):
                return {"event_hash": "monitor-audit-hash", **kwargs}

            def record_paper_learning_rule_history(self, **kwargs):
                row = {"id": f"history-{len(self.history) + 1}", **kwargs}
                self.history.insert(0, row)
                return row

            def list_paper_learning_rule_history(self, rule_id=None, limit=1):
                return self.history[:limit]

            def create_paper_learning_rule_version(self, source_rule_id):
                return {**self.rule, "id": "active-monitor-rule-v2", "version": 2, "status": "shadow", "evaluation": {}}

        monitor_fixture = ActiveMonitorFixture()
        monitor_trades = [{
            "id": f"monitor-loss-{index}",
            "status": "closed",
            "ticker": "AAPL",
            "asset_class": "equity",
            "direction": "long",
            "setup_type": "quality_momentum",
            "entry_price": 100.0,
            "closed_price": 98.0 - index,
            "stop_price": 95.0,
            "quantity": 1,
            "opened_at": f"2026-02-0{index + 1}T09:00:00+00:00",
            "closed_at": f"2026-02-0{index + 1}T16:00:00+00:00",
            "exit_reason": "risk exit",
            "lessons_learned": "Paper safety monitor fixture.",
            "trade_ticket": {
                "learning_feature_snapshot": {
                    "scores": {"active_learning_rule_ids": ["active-monitor-rule"]},
                    "plan": {"entry_price": 100.0, "stop_price": 95.0},
                    "snapshot_hash": f"monitor-snapshot-{index}",
                }
            },
        } for index in range(4)]
        monitor_service = PaperLearningService(monitor_fixture)
        monitor_result = monitor_service._monitor_active_rules(monitor_trades, [])
        require(monitor_result.get("auto_paused") == 1, failures, "active-rule loss-streak kill switch did not pause")
        require(monitor_fixture.rule.get("status") == "paused", failures, "active paper rule remained active after kill switch")
        require(
            (monitor_fixture.rule.get("evaluation", {}).get("live_monitor") or {}).get("status") == "auto_paused",
            failures,
            "active live monitor status is missing",
        )
        try:
            monitor_service.review_rule("active-monitor-rule", "rollback", "QA must not bypass automatic safety pause")
            failures.append("automatic safety pause was bypassed by rollback")
        except ValueError:
            pass
        restarted = monitor_service.review_rule("active-monitor-rule", "restart_shadow", "QA starts a fresh shadow validation version")
        require(restarted.get("rule", {}).get("status") == "shadow", failures, "paused rule did not restart in shadow")
        require(restarted.get("rule", {}).get("version") == 2, failures, "shadow restart did not create a new version")

        boundary = PaperLearningService._experiment_boundary(
            "2026-01-10T00:00:00+00:00",
            [
                {"id": "pre", "opened_at": "2026-01-09T00:00:00+00:00", "setup_type": "quality_momentum", "asset_class": "equity", "direction": "long"},
                {"id": "early", "opened_at": "2026-01-11T00:00:00+00:00", "setup_type": "quality_momentum", "asset_class": "equity", "direction": "long"},
                {"id": "valid", "opened_at": "2026-01-13T00:00:00+00:00", "setup_type": "quality_momentum", "asset_class": "equity", "direction": "long"},
            ],
            [{"trade_id": "pre", "due_at": "2026-01-12T00:00:00+00:00", "setup_type": "quality_momentum", "asset_class": "equity", "direction": "long"}],
            {"setup_type": "quality_momentum", "asset_class": "equity", "direction": "long"},
        )
        require(boundary.get("embargo_until") == "2026-01-12T00:00:00+00:00", failures, "overlapping label embargo is wrong")
        require(boundary.get("purged_trade_ids") == ["pre"], failures, "pre-start trade was not purged")

        series = PaperLearningService._performance_series_metrics([2.0, -1.0, -1.0, 3.0])
        require(series.get("expectancy_pct") == 0.75, failures, "champion/challenger expectancy metric is wrong")
        require(series.get("profit_factor") == 2.5, failures, "champion/challenger profit factor is wrong")
        require(series.get("max_loss_streak") == 2, failures, "champion/challenger loss streak is wrong")

        root = Path(__file__).resolve().parent
        api_source = (root / "api.py").read_text(encoding="utf-8")
        ui_source = (root / "frontend" / "src" / "components" / "PaperLearningV2Panel.tsx").read_text(encoding="utf-8")
        require('/api/trading/paper-learning-v2' in api_source, failures, "learning v2 API route missing")
        require('/api/trading/paper-learning-v2/trades/{trade_id}' in api_source, failures, "trade detail API route missing")
        require('/api/trading/paper-learning-v2/rules/{rule_id}/rollback-preview' in api_source, failures, "rollback preview API route missing")
        require('paper-learning-v2' in ui_source, failures, "learning v2 UI contract missing")
        require('paper-learning-operations' in ui_source, failures, "operational learning cockpit missing")
        require('paper-learning-rule-lab' in ui_source, failures, "manual paper rule lab missing")
        require('paper-learning-rollback-preview' in ui_source, failures, "rollback preview UI missing")
        require('paper-learning-rule-history' in ui_source, failures, "rule history UI missing")
        require('Live-Monitor' in ui_source, failures, "active-rule live monitor UI missing")
        require('Neue Shadow-Version' in ui_source, failures, "safe shadow restart UI missing")
        require('paper-learning-trade-reviews' in ui_source, failures, "auditable trade review UI missing")
        require('Pflichtbegründung' in ui_source, failures, "rule action reason is not visible")

        PaperLearningService._refresh_lock.acquire()
        try:
            busy_result = service.refresh_learning_state()
        finally:
            PaperLearningService._refresh_lock.release()
        require(busy_result.get("status") == "busy", failures, "overlapping learning run was not rejected")
        require(busy_result.get("retryable") is True, failures, "overlap response is not retryable")

        class FailingRefreshFixture:
            def __init__(self):
                self.settings = {}

            def set_app_setting(self, key, value):
                self.settings[key] = value

            @staticmethod
            def list_paper_trades(limit=1000):
                raise RuntimeError("deterministic refresh failure")

        failing_manager = FailingRefreshFixture()
        try:
            PaperLearningService(failing_manager).refresh_learning_state()
            failures.append("failed learning refresh did not raise")
        except RuntimeError:
            failed_run = json.loads(failing_manager.settings.get("paper_learning_v2_last_result") or "{}")
            require(failed_run.get("status") == "error", failures, "failed learning run was not observable")
            require(failed_run.get("retryable") is True, failures, "failed learning run is not marked retryable")
            require(bool(failed_run.get("run_id")), failures, "failed learning run id missing")

    if failures:
        print("Paper Learning v2 QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("paper learning v2 QA ok (immutable features, attribution, shadow rules, audit, paper-only gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
