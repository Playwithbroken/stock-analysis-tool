from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.paper_trading_service import PaperTradingService


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http_{self.status_code}")

    def json(self):
        return self.payload


def test_realtime_chain_and_greeks_contract():
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if url.endswith("/markets/options/expirations"):
            return FakeResponse({"expirations": {"date": [expiry]}})
        if url.endswith("/markets/options/chains"):
            return FakeResponse(
                {
                    "options": {
                        "option": {
                            "symbol": "AAPL260913C00200000",
                            "option_type": "call",
                            "strike": 200,
                            "bid": 5.0,
                            "ask": 5.4,
                            "last": 5.2,
                            "volume": 240,
                            "open_interest": 1800,
                            "ask_date": now_ms,
                            "greeks": {
                                "delta": 0.54,
                                "gamma": 0.031,
                                "theta": -0.08,
                                "vega": 0.21,
                                "mid_iv": 0.32,
                                "updated_at": now_ms,
                            },
                        }
                    }
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    service = PaperTradingService.__new__(PaperTradingService)
    with patch.dict(
        os.environ,
        {"TRADIER_ACCESS_TOKEN": "test-tradier-token", "TRADIER_ENVIRONMENT": "production"},
    ), patch("src.option_data_provider.requests.get", side_effect=fake_get):
        snapshot = service._get_option_contract_snapshot("AAPL", "call", 200.0)

    assert snapshot["status"] == "available"
    assert snapshot["source"] == "tradier_brokerage_options"
    assert snapshot["realtime"] is True
    assert snapshot["broker_quote_reference"] is True
    assert snapshot["fill_guaranteed"] is False
    assert snapshot["quote_quality"] == "realtime_broker_reference_not_fill_guarantee"
    assert snapshot["greeks"] == {"delta": 0.54, "gamma": 0.031, "theta": -0.08, "vega": 0.21}
    assert snapshot["greeks_source"] == "ORATS via Tradier"
    assert len(calls) == 2
    assert calls[1]["params"]["greeks"] == "true"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-tradier-token"


def test_stored_contract_quote_uses_same_locked_symbol():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def fake_get(url, params, headers, timeout):
        assert url.endswith("/markets/quotes")
        assert params["symbols"] == "AAPL260913C00200000"
        assert params["greeks"] == "true"
        return FakeResponse(
            {
                "quotes": {
                    "quote": {
                        "symbol": "AAPL260913C00200000",
                        "bid": 5.7,
                        "ask": 5.9,
                        "last": 5.8,
                        "volume": 300,
                        "open_interest": 1900,
                        "bid_date": now_ms,
                        "greeks": {
                            "delta": 0.57,
                            "gamma": 0.029,
                            "theta": -0.075,
                            "vega": 0.2,
                            "mid_iv": 0.31,
                        },
                    }
                }
            }
        )

    service = PaperTradingService.__new__(PaperTradingService)
    ticket = {
        "option_contract": {
            "contract_symbol": "AAPL260913C00200000",
            "ticker": "AAPL",
            "expiry": "2026-09-13",
            "option_type": "call",
        },
        "option_contract_identity": {
            "status": "locked",
            "contract_symbol": "AAPL260913C00200000",
            "underlying_ticker": "AAPL",
            "expiry": "2026-09-13",
            "option_type": "call",
        },
    }
    with patch.dict(
        os.environ,
        {"TRADIER_ACCESS_TOKEN": "test-tradier-token", "TRADIER_ENVIRONMENT": "production"},
    ), patch("src.option_data_provider.requests.get", side_effect=fake_get):
        quote = service._get_stored_option_contract_quote(ticket)

    assert quote["status"] == "available"
    assert quote["contract_symbol"] == "AAPL260913C00200000"
    assert quote["price"] == 5.7
    assert quote["source"] == "tradier_brokerage_option_quote"
    assert quote["fill_guaranteed"] is False


def test_missing_token_is_explicit_and_safe():
    service = PaperTradingService.__new__(PaperTradingService)
    with patch.dict(os.environ, {"TRADIER_ACCESS_TOKEN": ""}):
        result = service._get_tradier_option_contract_snapshot("AAPL", "call", 200.0)
    assert result["status"] == "unavailable"
    assert result["reason"] == "tradier_access_token_not_configured"
    assert result["realtime"] is False


def test_provider_evidence_is_visible_in_app_telegram_and_config():
    root = Path(__file__).resolve().parent
    panel = (root / "frontend/src/components/PaperTradingPanel.tsx").read_text(encoding="utf-8")
    telegram = (root / "src/email_alert_service.py").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    assert "Broker-Echtzeit · kein Fill-Versprechen" in panel
    assert "ORATS via Tradier" not in panel  # source is rendered from the provider payload
    for field in ("greeks.delta", "greeks.gamma", "greeks.theta", "greeks.vega", "greeks_source"):
        assert field in panel
    for field in ("Delta", "Gamma", "Theta", "Vega", "Fill nicht garantiert", "greeks_source"):
        assert field in telegram
    assert "TRADIER_ACCESS_TOKEN=<tradier-production-market-data-token>" in env_example
    assert "TRADIER_ENVIRONMENT=production" in env_example


if __name__ == "__main__":
    tests = [
        test_realtime_chain_and_greeks_contract,
        test_stored_contract_quote_uses_same_locked_symbol,
        test_missing_token_is_explicit_and_safe,
        test_provider_evidence_is_visible_in_app_telegram_and_config,
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"tradier option provider QA ok: {len(tests)} contracts")
