import os
import sys
import tempfile


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "advisory-test.db")

        from src.advisory_service import build_portfolio_advisory_check, build_suitability_check
        from src.storage import PortfolioManager

        manager = PortfolioManager()
        default_profile = manager.get_workspace_profile()
        if "advisory_profile_complete" not in default_profile:
            print("FAIL advisory defaults missing from workspace profile")
            return 1
        if default_profile.get("advisory_profile_complete"):
            print("FAIL default advisory profile should require explicit confirmation")
            return 1

        saved = manager.save_workspace_profile(
            {
                "investment_objective": "growth",
                "time_horizon": "long",
                "risk_tolerance": "high",
                "experience_level": "advanced",
                "loss_capacity": "high",
                "liquidity_need": "low",
                "preferred_strategy": "long_term",
                "max_single_position_pct": 250,
                "max_portfolio_drawdown_pct": -4,
                "suitability_notes": "Prefers verified thesis, trigger and invalidation.",
            }
        )
        if not saved.get("advisory_profile_complete"):
            print("FAIL complete advisory profile not marked complete")
            return 1
        if saved.get("max_single_position_pct") != 100.0:
            print("FAIL max_single_position_pct was not clamped to 100")
            return 1
        if saved.get("max_portfolio_drawdown_pct") != 1.0:
            print("FAIL max_portfolio_drawdown_pct was not clamped to 1")
            return 1

        conservative = manager.save_workspace_profile(
            {
                "risk_tolerance": "low",
                "experience_level": "beginner",
                "loss_capacity": "low",
                "preferred_strategy": "dividend",
                "max_single_position_pct": 8,
                "max_portfolio_drawdown_pct": 10,
            }
        )
        blocked = build_suitability_check(
            conservative,
            {
                "symbol": "BTC-USD",
                "asset_class": "crypto",
                "action": "trade",
                "strategy": "day_trading",
                "risk_level": "speculative",
                "position_pct": 20,
            },
        )
        if blocked.get("decision") != "blocked":
            print(f"FAIL unsuitable speculative day trade not blocked: {blocked}")
            return 1
        if "position_size_too_large" not in blocked.get("risk_flags", []):
            print("FAIL position size risk flag missing")
            return 1

        suitable_profile = manager.save_workspace_profile(
            {
                "risk_tolerance": "high",
                "experience_level": "advanced",
                "loss_capacity": "high",
                "preferred_strategy": "long_term",
                "max_single_position_pct": 15,
                "max_portfolio_drawdown_pct": 25,
            }
        )
        allowed = build_suitability_check(
            suitable_profile,
            {
                "symbol": "AAPL",
                "asset_class": "equity",
                "action": "setup",
                "strategy": "long_term",
                "risk_level": "medium",
                "position_pct": 5,
                "thesis": "Earnings quality, margin trend and invalidation are documented.",
            },
        )
        if allowed.get("decision") != "setup_allowed":
            print(f"FAIL suitable long-term setup not allowed: {allowed}")
            return 1

        concentrated = build_portfolio_advisory_check(
            suitable_profile,
            {
                "summary": {
                    "total_value": 10000,
                    "num_holdings": 3,
                    "avg_score": 22,
                    "return_since_buy_pct": 4,
                    "sector_allocation": {"Technology": 70, "Cash": 30},
                },
                "holdings": [
                    {"ticker": "AAPL", "position_value": 6000, "score": 40, "sector": "Technology"},
                    {"ticker": "MSFT", "position_value": 2500, "score": 35, "sector": "Technology"},
                    {"ticker": "CASH", "position_value": 1500, "score": 0, "sector": "Cash"},
                ],
            },
        )
        if concentrated.get("decision") != "blocked_for_new_risk":
            print(f"FAIL concentrated portfolio not blocked for new risk: {concentrated}")
            return 1
        if "single_position_limit_breach" not in concentrated.get("risk_flags", []):
            print("FAIL concentrated portfolio missing single position risk flag")
            return 1

        balanced = build_portfolio_advisory_check(
            suitable_profile,
            {
                "summary": {
                    "total_value": 10000,
                    "num_holdings": 6,
                    "avg_score": 45,
                    "return_since_buy_pct": 6,
                    "sector_allocation": {"Technology": 30, "Healthcare": 20, "Consumer": 20, "ETF": 30},
                },
                "holdings": [
                    {"ticker": "AAPL", "position_value": 1400, "score": 55, "sector": "Technology"},
                    {"ticker": "MSFT", "position_value": 1300, "score": 55, "sector": "Technology"},
                    {"ticker": "JNJ", "position_value": 1500, "score": 40, "sector": "Healthcare"},
                    {"ticker": "PEP", "position_value": 1500, "score": 35, "sector": "Consumer"},
                    {"ticker": "VOO", "position_value": 1400, "score": 45, "sector": "ETF"},
                    {"ticker": "SCHD", "position_value": 1400, "score": 40, "sector": "ETF"},
                    {"ticker": "TLT", "position_value": 1000, "score": 20, "sector": "ETF"},
                ],
            },
        )
        if balanced.get("decision") != "within_framework":
            print(f"FAIL balanced portfolio not marked within framework: {balanced}")
            return 1

    print("Advisory profile smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
