from datetime import datetime, timezone

from src.email_alert_service import EmailAlertService
from src.paper_trading_service import PaperTradingService


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def market_context():
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "macro_regime": "risk-off",
        "opening_bias": "Defensive tape with energy and duration in focus.",
        "regions": {
            "europe": {
                "assets": [
                    {"ticker": "^GDAXI", "change_1d": 0.2},
                    {"ticker": "^FTSE", "change_1d": -0.4},
                    {"ticker": "^FCHI", "change_1d": -0.1},
                ]
            },
            "usa": {
                "assets": [
                    {"ticker": "ES=F", "change_1d": -0.5},
                    {"ticker": "NQ=F", "change_1d": -0.8},
                    {"ticker": "YM=F", "change_1d": -0.3},
                ]
            },
        },
        "macro_assets": [
            {"ticker": "^TNX", "price": 4.69, "change_1d": 0.77},
            {"ticker": "DX-Y.NYB", "price": 99.75, "change_1d": 0.15},
        ],
    }


class MemoryManager:
    def __init__(self):
        self.created = None
        self.outcomes = []

    def create_paper_trade(self, payload):
        self.created = payload
        return {
            **payload,
            "id": "regime-trade-1",
            "status": "open",
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "max_holding_days": None,
        }

    def upsert_paper_trade_outcomes(self, trade_id, outcomes):
        self.outcomes = outcomes
        return len(outcomes)


def test_regime_snapshot_is_complete_honest_and_persisted():
    manager = MemoryManager()
    service = PaperTradingService(manager)
    snapshot = service._build_entry_market_regime(market_context())
    require(snapshot["immutable_at_entry"] is True, "regime is not marked immutable")
    require(snapshot["quality"]["status"] == "complete", "complete context was downgraded")
    require(snapshot["risk_appetite"]["label"] == "risk-off", "risk appetite missing")
    require(snapshot["rates"]["label"] == "rising", "rate direction missing")
    require(snapshot["dollar"]["label"] == "strengthening", "dollar direction missing")
    require(snapshot["volatility"]["is_proxy"] is True, "volatility was overclaimed as direct VIX")
    require(snapshot["breadth"]["is_proxy"] is True, "breadth was overclaimed as exchange breadth")

    service._enrich_trade = lambda trade: trade
    trade = service.create_trade_from_payload(
        {
            "ticker": "AAPL",
            "asset_class": "equity",
            "direction": "long",
            "entry_price": 100.0,
            "quantity": 2,
            "leverage": 1,
        },
        market_context(),
    )
    stored = (trade.get("trade_ticket") or {}).get("entry_market_regime") or {}
    require(stored.get("risk_appetite", {}).get("label") == "risk-off", "raw trade lost entry regime")
    require(len(manager.outcomes) == 4, "raw trade outcome schedule regressed")


def test_regime_performance_and_telegram_are_auditable():
    service = PaperTradingService(MemoryManager())
    regime = service._build_entry_market_regime(market_context())
    closed = [
        {
            "trade_ticket": {"entry_market_regime": regime},
            "realized_pnl_pct": 5.0,
            "realized_pnl_value": 500.0,
        },
        {
            "trade_ticket": {"entry_market_regime": regime},
            "realized_pnl_pct": -2.0,
            "realized_pnl_value": -200.0,
        },
    ]
    performance = service._build_market_regime_performance(closed)
    require(performance["coverage_pct"] == 100.0, "regime coverage is wrong")
    risk_off = next(
        row for row in performance["rows"]
        if row["dimension"] == "risk_appetite" and row["label"] == "risk-off"
    )
    require(risk_off["trades"] == 2, "regime outcomes were not grouped")
    require(risk_off["performance"]["profit_factor"] == 2.5, "regime profit factor is wrong")
    require(risk_off["readiness"] == "insufficient_sample", "small sample was overstated")

    alert = EmailAlertService.__new__(EmailAlertService)
    lines = alert._paper_entry_regime_lines({"entry_market_regime": regime})
    rendered = "\n".join(lines)
    for marker in ("Entry-Regime:", "risk-off", "Volatilität", "Proxy", "US10Y", "unveränderlich"):
        require(marker in rendered, f"Telegram entry regime missing {marker}")


def main():
    tests = [
        test_regime_snapshot_is_complete_honest_and_persisted,
        test_regime_performance_and_telegram_are_auditable,
    ]
    for test in tests:
        test()
    print(f"Paper entry market regime QA passed ({len(tests)} test groups).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
