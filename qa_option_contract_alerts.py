from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from src.email_alert_service import EmailAlertService
from src.paper_trading_service import PaperTradingService


class DummyPortfolioManager:
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def quoted_contract(
    ticker: str,
    option_type: str,
    strike: float,
    ask: float,
) -> dict:
    return {
        "status": "available",
        "ticker": ticker,
        "option_type": option_type,
        "contract_symbol": f"{ticker}260918{option_type[0].upper()}{int(strike * 1000):08d}",
        "expiry": "2026-09-18",
        "days_to_expiry": 39,
        "strike": strike,
        "underlying_price": 100.0,
        "bid": round(ask - 0.2, 2),
        "ask": ask,
        "mid": round(ask - 0.1, 2),
        "spread_pct": 8.0,
        "last_price": round(ask - 0.1, 2),
        "implied_volatility_pct": 24.5,
        "volume": 321,
        "open_interest": 1450,
        "moneyness_pct": strike - 100,
        "break_even": strike + ask if option_type == "call" else strike - ask,
        "distance_to_break_even_pct": 2.2 if option_type == "call" else -2.2,
        "max_loss_per_contract": ask * 100,
        "source": "yfinance_option_chain",
        "data_as_of": "2026-08-10T10:00:00",
        "quote_quality": "delayed_snapshot_not_executable",
    }


def test_chain_contract_selection() -> None:
    service = PaperTradingService(DummyPortfolioManager())
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    calls = pd.DataFrame(
        [
            {
                "contractSymbol": "GLD-C-95",
                "strike": 95.0,
                "bid": 6.8,
                "ask": 7.4,
                "lastPrice": 7.1,
                "openInterest": 20,
                "volume": 3,
                "impliedVolatility": 0.31,
                "lastTradeDate": datetime.now(timezone.utc),
            },
            {
                "contractSymbol": "GLD-C-100",
                "strike": 100.0,
                "bid": 2.0,
                "ask": 2.2,
                "lastPrice": 2.1,
                "openInterest": 900,
                "volume": 250,
                "impliedVolatility": 0.245,
                "lastTradeDate": datetime.now(timezone.utc),
            },
        ]
    )
    puts = calls.assign(
        contractSymbol=["GLD-P-95", "GLD-P-100"],
        bid=[1.0, 2.1],
        ask=[1.2, 2.3],
    )
    fake_ticker = SimpleNamespace(
        options=(expiry,),
        option_chain=lambda selected_expiry: SimpleNamespace(calls=calls, puts=puts),
    )
    with patch("src.paper_trading_service.yf.Ticker", return_value=fake_ticker):
        call = service._get_option_contract_snapshot("GLD", "call", 100.0)
        put = service._get_option_contract_snapshot("GLD", "put", 100.0)

    require(call["status"] == "available", "call contract snapshot should be available")
    require(call["contract_symbol"] == "GLD-C-100", "selector should prefer the liquid near-money call")
    require(call["break_even"] == 102.2, "call break-even should equal strike plus ask")
    require(call["max_loss_per_contract"] == 220.0, "call premium risk should use ask times 100")
    require(put["contract_symbol"] == "GLD-P-100", "selector should use the put side of the chain")
    require(put["break_even"] == 97.7, "put break-even should equal strike minus ask")


def test_playbooks_are_contract_and_direction_specific() -> None:
    service = PaperTradingService(DummyPortfolioManager())
    service._market_reference_fields = lambda ticker: {
        "reference_price": 100.0,
        "data_as_of": "2026-08-10T10:00:00",
        "market_data": {"price": 100.0},
    }
    service._get_option_contract_snapshot = lambda ticker, option_type, underlying_price: quoted_contract(
        ticker,
        option_type,
        100.0,
        2.2 if option_type == "call" else 2.4,
    )
    playbooks = service._build_commodity_leverage_playbooks()
    require(len(playbooks) == 6, "three underlyings should produce one call and one put each")
    by_id = {item["id"]: item for item in playbooks}
    gold_call = by_id["commodity-option-GLD-call"]
    gold_put = by_id["commodity-option-GLD-put"]
    oil_call = by_id["commodity-option-USO-call"]
    require(gold_call["headline"] != gold_put["headline"], "call and put headlines must differ")
    require(gold_call["thesis"] != gold_put["thesis"], "call and put theses must differ")
    require(gold_call["thesis"] != oil_call["thesis"], "underlying theses must differ")
    require(gold_call["reference_price"] == 2.2, "playbook premium must use the quoted ask")
    require(gold_call["source_label"] == "Yahoo Finance options chain snapshot", "source must identify the chain snapshot")
    framework = service._build_decision_framework(gold_call)
    require(framework["entry_trigger"] == gold_call["entry_trigger"], "framework must retain the specific confirmation")
    require(framework["invalidation"] == gold_call["invalidation"], "framework must retain the specific invalidation")

    equity_options = service._build_option_learning_playbooks(
        [
            {
                "ticker": "AAPL",
                "asset_class": "equity",
                "direction": "long",
                "headline": "AAPL guidance and relative strength improve",
                "score": 92,
                "reference_price": 100.0,
                "source_label": "SEC filing",
                "data_as_of": "2026-08-10T10:00:00",
                "market_data": {"price": 100.0},
            }
        ]
    )
    require(len(equity_options) == 1, "high-score equity should produce a contract-specific option playbook")
    apple_call = equity_options[0]
    require(apple_call["option_contract"]["contract_symbol"].startswith("AAPL"), "equity option must retain its contract")
    require("AAPL guidance" in apple_call["headline"], "equity option must retain its specific catalyst")
    require("AAPL" in apple_call["entry_trigger"], "equity option confirmation must name the underlying")


def test_telegram_contains_contract_evidence_and_honest_fallback() -> None:
    alert_service = EmailAlertService.__new__(EmailAlertService)
    contract = quoted_contract("GLD", "call", 100.0, 2.2)
    event = {
        "asset_class": "option",
        "direction": "call",
        "trade_ticket": {
            "asset_class": "option",
            "option_contract": contract,
            "option_decision": {
                "thesis": "Gold rises only if real yields fall and price confirms.",
                "event_drivers": ["US real yields", "US dollar"],
                "data_limit": "Delayed snapshot; executable broker quote not verified.",
            },
        },
    }
    text = "\n".join(alert_service._paper_option_contract_lines(event))
    for expected in (
        "GLD260918C00100000",
        "Strike 100.00",
        "Verfall 2026-09-18",
        "IV 24.50%",
        "Open Interest 1450",
        "Break-even",
        "US real yields / US dollar",
        "executable broker quote not verified",
    ):
        require(expected in text, f"telegram option block missing {expected!r}")

    fallback_text = "\n".join(
        alert_service._paper_option_contract_lines(
            {
                "asset_class": "option",
                "trade_ticket": {
                    "asset_class": "option",
                    "option_contract": {"status": "unavailable", "reason": "provider_timeout"},
                },
            }
        )
    )
    require("nur eine Schätzung" in fallback_text, "missing chain data must be labeled as an estimate")
    require("provider_timeout" in fallback_text, "fallback should expose the concrete provider reason")


def main() -> int:
    tests = [
        test_chain_contract_selection,
        test_playbooks_are_contract_and_direction_specific,
        test_telegram_contains_contract_evidence_and_honest_fallback,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"option contract alert QA ok: {len(tests)} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
