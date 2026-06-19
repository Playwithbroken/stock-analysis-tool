import os
import sys
import tempfile
from typing import Any, Dict


class FakeDataFetcher:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.info = {
            "longName": f"{ticker} Test Asset",
            "currentPrice": 123.45,
            "regularMarketPrice": 123.45,
            "currency": "USD",
            "fiftyTwoWeekHigh": 150.0,
            "fiftyTwoWeekLow": 90.0,
        }

    def get_all_data(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": f"{self.ticker} Test Asset",
            "price_data": {"error": "provider unavailable in QA"},
            "fundamentals": {},
            "volatility": {},
            "analyst_data": {},
            "short_interest": {},
            "news": [],
            "comparison": {},
            "earnings_history": [],
            "guidance_signal": {},
            "fetch_time": "qa",
        }

    def get_price_data_fast(self) -> Dict[str, Any]:
        return {"error": "fast provider unavailable in QA"}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "analyzer-resolution-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        from fastapi.testclient import TestClient
        import api

        api.DataFetcher = FakeDataFetcher

        async def fake_yahoo_search(query: str, limit: int = 8):
            return []

        class FakeDiscoveryService:
            async def search_ticker(self, query: str):
                return []

        api._search_yahoo_finance = fake_yahoo_search
        api.get_discovery_service = lambda: FakeDiscoveryService()

        client = TestClient(api.app)
        login = client.post("/api/auth/login", json={"password": "test-pass"})
        if login.status_code != 200:
            print(f"FAIL login failed: {login.status_code} {login.text}")
            return 1

        cases = [
            ("robinhood", "HOOD"),
            ("jepi dividend etf", "JEPI"),
            ("solana crypto", "SOL-USD"),
            ("bnb crypto", "BNB-USD"),
            ("coinbase stock", "COIN"),
        ]

        failures = []
        for query, expected in cases:
            response = client.get(f"/api/analyze/{query}")
            if response.status_code != 200:
                failures.append(f"{query}: HTTP {response.status_code} {response.text}")
                continue
            payload = response.json()
            ticker = str(payload.get("ticker") or "").upper()
            degraded = bool(payload.get("data_quality", {}).get("degraded"))
            insufficient = bool(payload.get("data_quality", {}).get("insufficient_signal"))
            print(f"{query!r} -> {ticker} degraded={degraded} insufficient={insufficient}")
            if ticker != expected:
                failures.append(f"{query}: expected {expected}, got {ticker}")
            if not degraded or not insufficient:
                failures.append(f"{query}: fallback quality flags missing: {payload.get('data_quality')}")

        if failures:
            print("\nAnalyzer resolution failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("Analyzer resolution smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
