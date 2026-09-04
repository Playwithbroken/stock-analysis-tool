from __future__ import annotations

import os
import tempfile


PROFILE_KEYS = (
    "PAPER_CAPITAL_PROFILE",
    "PAPER_TRADING_STARTING_CAPITAL",
    "PAPER_TRADING_RISK_PER_TRADE_PCT",
    "PAPER_TRADING_MAX_OPEN_RISK_PCT",
    "PAPER_TRADING_MAX_POSITION_PCT",
    "PAPER_TRADING_MAX_GROSS_EXPOSURE_PCT",
    "PAPER_TRADING_MIN_CASH_RESERVE_PCT",
    "PAPER_TRADING_TARGET_GROSS_EXPOSURE_PCT",
    "PAPER_TRADING_MAX_TICKER_EXPOSURE_PCT",
    "PAPER_TRADING_MAX_OPEN_TRADES",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    previous = {key: os.environ.get(key) for key in PROFILE_KEYS}
    try:
        for key in PROFILE_KEYS:
            os.environ.pop(key, None)
        os.environ["PAPER_CAPITAL_PROFILE"] = "conviction"
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["APP_DATA_DIR"] = tmp
            os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "conviction.db")

            from src.paper_trading_service import PaperTradingService
            from src.storage import PortfolioManager

            service = PaperTradingService(PortfolioManager())
            account = service._build_demo_account([], [])
            require(account["capital_profile"] == "conviction", "conviction profile is not active")
            require(account["starting_capital"] == 500_000, "paper capital is not 500,000")
            require(account["risk_budget_per_trade_value"] == 3_750, "risk budget must be 0.75%")
            require(account["max_position_value"] == 100_000, "position cap must be 20%")
            require(account["max_gross_exposure_value"] == 450_000, "10% cash reserve must remain")
            require(account["capital_deployment"]["target_gross_exposure_value"] == 375_000, "deployment target must be 75%")
            require(account["capital_deployment"]["status"] == "deploy_on_qualified_signals", "empty account should seek qualified deployment")
            require(account["open_trade_slots"] == 16, "conviction profile must allow 16 diversified positions")
            require(account["mode"] == "paper_learning_only", "profile escaped paper-only mode")

            high = service._conviction_risk_multiplier({"score": 94}, account, 0.60)
            medium = service._conviction_risk_multiplier({"score": 84}, account, 0.60)
            exploratory = service._conviction_risk_multiplier({"score": 70}, account, 0.60)
            require(high == (1.0, "high"), "high conviction did not receive full paper risk")
            require(medium == (0.8, "medium"), "medium conviction tier is wrong")
            require(exploratory == (0.6, "exploratory"), "low conviction was incorrectly upsized")

        print("PASS: 500k conviction paper profile and score-tiered sizing")
        return 0
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
