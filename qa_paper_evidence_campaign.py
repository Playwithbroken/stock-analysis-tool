from pathlib import Path

from src.paper_trading_service import PaperTradingService
from src.strategy_library import StrategyLibrary


ROOT = Path(__file__).resolve().parent


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    empty_readiness = StrategyLibrary.build_readiness([], [])
    campaign = StrategyLibrary.build_evidence_campaign(empty_readiness)
    require(campaign.get("strategy_count") == 6, failures, "campaign does not cover all six strategies")
    require(campaign.get("global_outcomes_remaining") == 100, failures, "global 100-outcome target missing")
    require(campaign.get("overall_ready") is False, failures, "empty evidence was marked ready")

    trades = []
    outcomes = []
    for strategy in StrategyLibrary.STRATEGIES:
        setup_type = strategy.setup_types[0]
        for index in range(30):
            trade_id = f"{strategy.id}-{index}"
            trades.append({
                "id": trade_id,
                "ticker": f"T{index}",
                "setup_type": setup_type,
                "strategy_id": strategy.id,
                "status": "closed",
                "realized_pnl_pct": 1.0,
                "realized_pnl_value": 100.0,
                "closed_at": f"2026-07-{(index % 28) + 1:02d}T12:00:00",
            })
            outcomes.append({"trade_id": trade_id, "setup_type": setup_type, "strategy_id": strategy.id, "result": "hit"})
    full_readiness = StrategyLibrary.build_readiness(trades, outcomes)
    full_campaign = StrategyLibrary.build_evidence_campaign(full_readiness)
    require(full_campaign.get("closed_trades_total") == 180, failures, "closed-trade total is wrong")
    require(full_campaign.get("decisive_outcomes_total") == 180, failures, "decisive-outcome total is wrong")
    require(full_campaign.get("strategies_ready") == 6, failures, "qualified strategies were not marked ready")
    require(full_campaign.get("overall_ready") is True, failures, "complete real evidence campaign was not ready")

    mappings = {
        "small_cap_discovery": "small_cap_future_star",
        "earnings_reaction": "earnings_guidance_reaction",
        "macro_event": "macro_event_edge",
        "option_call_learning": "defined_risk_options",
    }
    for setup_type, expected_strategy in mappings.items():
        mapped = StrategyLibrary.find_for_playbook({"setup_type": setup_type, "asset_class": "equity"})
        require(mapped.get("id") == expected_strategy, failures, f"{setup_type} maps to {mapped.get('id')} instead of {expected_strategy}")
    explicit_news = StrategyLibrary.find_for_playbook({"setup_type": "confirmed_news_event", "strategy_id": "macro_event_edge"})
    require(explicit_news.get("id") == "macro_event_edge", failures, "stable news setup did not honor explicit strategy assignment")

    candidates = [
        {"ticker": "READY", "score": 99, "strategy_context": {"real_world_ready": True, "evidence_progress_pct": 100, "closed_trades": 30}},
        {"ticker": "UNDER", "score": 72, "strategy_context": {"real_world_ready": False, "evidence_progress_pct": 0, "closed_trades": 0}},
        {"ticker": "MID", "score": 90, "strategy_context": {"real_world_ready": False, "evidence_progress_pct": 50, "closed_trades": 15}},
    ]
    ordered = sorted(candidates, key=PaperTradingService._evidence_priority_sort_key)
    require([row["ticker"] for row in ordered] == ["UNDER", "MID", "READY"], failures, "evidence priority ordering is wrong")

    source_contracts = {
        ROOT / "src" / "paper_trading_service.py": ["small_cap_discovery", "earnings_guidance_reaction", "macro_event_edge", "_evidence_priority_sort_key"],
        ROOT / "src" / "email_alert_service.py": ["Evidenzkampagne:", "Nächster Evidenz-Fokus:"],
        ROOT / "frontend" / "src" / "components" / "PaperTradingPanel.tsx": ["paper-evidence-campaign"],
    }
    for path, markers in source_contracts.items():
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in source, failures, f"{path.name} lacks {marker}")

    if failures:
        print("Paper evidence campaign QA failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("paper evidence campaign QA ok (6 strategies, 30 closes each, 100 outcomes, coverage priority)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
