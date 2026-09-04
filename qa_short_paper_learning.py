from __future__ import annotations

import os
import tempfile
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"X-Request-ID": "short-qa"}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def account(equity: str = "500000"):
    return {
        "id": "paper-short-account",
        "status": "ACTIVE",
        "trading_blocked": False,
        "equity": equity,
    }


def asset(*, borrow_status: str = "easy_to_borrow", shortable: bool = True):
    return {
        "class": "us_equity",
        "symbol": "AAPL",
        "status": "active",
        "tradable": True,
        "marginable": True,
        "shortable": shortable,
        "borrow_status": borrow_status,
        "easy_to_borrow": borrow_status == "easy_to_borrow",
    }


def main() -> int:
    original_db_path = None
    with tempfile.TemporaryDirectory(prefix="short-paper-qa-") as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = str(Path(tmp) / "short.db")
        os.environ["PAPER_CAPITAL_PROFILE"] = "conviction"

        from src.integrations.brokers.alpaca_paper import AlpacaPaperBrokerAdapter, AlpacaPaperConfig
        from src.paper_trading_service import PaperTradingService
        from src.storage import PortfolioManager
        import src.storage as storage

        original_db_path = storage.DB_PATH
        storage.DB_PATH = os.environ["PORTFOLIO_DB_PATH"]
        storage.init_db()

        manager = PortfolioManager()
        service = PaperTradingService(manager)
        demo = service._build_demo_account([], [])
        short = service._suggest_demo_sizing(
            {
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "short",
                "reference_price": 100,
                "risk_buffer_pct": 4,
                "score": 94,
                "tradeable": True,
                "correlation_check": {"blocked": False},
            },
            demo,
        )
        require(short["demo_tradeable"] is True, "qualified equity short was blocked")
        require(short["short_position"] is True, "short sizing was not labeled")
        require(short["suggested_notional_value"] <= 60_000, "short exceeded 12% position cap")
        require(short["suggested_quantity"] == int(short["suggested_quantity"]), "fractional local short was suggested")
        require(short["suggested_max_loss_value"] <= 2_812.50, "short exceeded reduced risk budget")
        service._validate_requested_trade_capacity(
            {
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "short",
                "quantity": 500,
                "entry_price": 100,
                "stop_price": 104,
            },
            demo,
        )
        try:
            service._validate_requested_trade_capacity(
                {
                    "ticker": "AAPL",
                    "asset_class": "equity",
                    "direction": "short",
                    "quantity": 500,
                    "entry_price": 100,
                    "stop_price": 99,
                },
                demo,
            )
            raise AssertionError("manual short without protective upper stop was allowed")
        except ValueError as exc:
            require("protective stop" in str(exc), "manual short stop blocker is unclear")

        no_capacity = {**demo, "remaining_short_exposure_value": 0}
        blocked = service._suggest_demo_sizing(
            {
                "ticker": "MSFT",
                "asset_class": "equity",
                "direction": "short",
                "reference_price": 100,
                "risk_buffer_pct": 4,
                "score": 94,
                "tradeable": True,
                "correlation_check": {"blocked": False},
            },
            no_capacity,
        )
        require(blocked["demo_tradeable"] is False, "exhausted short exposure did not block")

        crypto = service._suggest_demo_sizing(
            {
                "ticker": "BTC-USD",
                "asset_class": "crypto",
                "direction": "short",
                "reference_price": 100_000,
                "risk_buffer_pct": 5,
                "score": 95,
                "tradeable": True,
                "correlation_check": {"blocked": False},
            },
            demo,
        )
        require(crypto["demo_tradeable"] is True, "synthetic crypto short was blocked")
        require(crypto["synthetic_crypto_short"] is True, "crypto short was not labeled synthetic")
        require(crypto["suggested_notional_value"] <= 25_000, "crypto short exceeded 5% position cap")
        require(crypto["suggested_max_loss_value"] <= 1_875, "crypto short exceeded reduced risk budget")
        service._validate_requested_trade_capacity(
            {
                "ticker": "BTC-USD",
                "asset_class": "crypto",
                "direction": "short",
                "quantity": 0.2,
                "entry_price": 100_000,
                "stop_price": 105_000,
            },
            demo,
        )
        disabled_crypto = service._suggest_demo_sizing(
            {
                "ticker": "BTC-USD",
                "asset_class": "crypto",
                "direction": "short",
                "reference_price": 100_000,
                "risk_buffer_pct": 5,
                "score": 95,
                "tradeable": True,
                "correlation_check": {"blocked": False},
            },
            {**demo, "synthetic_crypto_shorts_enabled": False},
        )
        require(disabled_crypto["demo_tradeable"] is False, "disabled synthetic crypto short was allowed")

        cost = service._synthetic_crypto_short_cost(
            {
                "asset_class": "crypto",
                "direction": "short",
                "opened_at": "2026-08-25T12:00:00",
                "closed_at": "2026-08-27T12:00:00",
                "trade_ticket": {"synthetic_short_cost_model": {"funding_bps_per_day": 5}},
            },
            10_000,
        )
        require(cost["cost_value"] == 10.0 and cost["cost_pct"] == 0.1, "48h crypto funding cost is wrong")

        from src.signal_score_service import SignalScoreService

        scorer = object.__new__(SignalScoreService)
        scored = scorer._score_crypto(
            [{"ticker": "BTC-USD", "change": -5, "name": "Bitcoin"}],
            {"source": 0.35, "timing": 0.30, "conviction": 0.35},
        )[0]
        require(scored["directional_bias"] == "short", "negative crypto momentum did not create short bias")
        require(scored["short_score"] > scored["long_score"], "crypto downside score is not directional")

        etb_session = FakeSession([FakeResponse(account()), FakeResponse([]), FakeResponse(asset())])
        etb_adapter = AlpacaPaperBrokerAdapter(
            AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
            http_session=etb_session,
        )
        etb = etb_adapter.assess_short_sale(symbol="AAPL", quantity=100, reference_price=100)
        require(etb["allowed"] is True and etb["opens_short"] is True, "ETB whole-share paper short was blocked")
        require(etb_session.calls[2]["url"].endswith("/v2/assets/AAPL"), "asset eligibility endpoint was not queried")

        htb_session = FakeSession([FakeResponse(account()), FakeResponse([]), FakeResponse(asset(borrow_status="hard_to_borrow"))])
        htb_adapter = AlpacaPaperBrokerAdapter(
            AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
            http_session=htb_session,
        )
        htb = htb_adapter.assess_short_sale(symbol="AAPL", quantity=100, reference_price=100)
        require(htb["allowed"] is False, "HTB short without locate was allowed")
        require("borrow_not_easy_to_borrow" in htb["reasons"], "HTB blocker missing")

        fractional_session = FakeSession([FakeResponse(account()), FakeResponse([]), FakeResponse(asset())])
        fractional_adapter = AlpacaPaperBrokerAdapter(
            AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
            http_session=fractional_session,
        )
        fractional = fractional_adapter.assess_short_sale(symbol="AAPL", quantity=1.5, reference_price=100)
        require(fractional["allowed"] is False, "fractional short was allowed")
        require("fractional_short_not_supported" in fractional["reasons"], "fractional blocker missing")

        closing_session = FakeSession(
            [
                FakeResponse(account()),
                FakeResponse([{"symbol": "AAPL", "qty": "10", "side": "long", "market_value": "1000"}]),
            ]
        )
        closing_adapter = AlpacaPaperBrokerAdapter(
            AlpacaPaperConfig(key_id="paper-key", secret_key="paper-secret", enabled=True),
            http_session=closing_session,
        )
        closing = closing_adapter.assess_short_sale(symbol="AAPL", quantity=5, reference_price=100)
        require(closing["allowed"] is True and closing["opens_short"] is False, "ordinary long reduction was treated as short")
        require(len(closing_session.calls) == 2, "long reduction unnecessarily queried borrow status")

        print("short paper-learning QA passed (sizing, ETB, HTB, fractional, crypto, long reduction)")
        if original_db_path is not None:
            storage.DB_PATH = original_db_path
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
