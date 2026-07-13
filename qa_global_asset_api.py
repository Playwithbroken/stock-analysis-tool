from __future__ import annotations

import os
import tempfile
from typing import Any, Dict


class OfflineDataFetcher:
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self.info = {
            "longName": f"{ticker} QA Asset",
            "currentPrice": 100.0,
            "regularMarketPrice": 100.0,
            "currency": "USD",
        }

    def get_all_data(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": f"{self.ticker} QA Asset",
            "price_data": {"error": "provider intentionally offline"},
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
        return {"error": "provider intentionally offline"}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "global-asset-api.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["APP_COOKIE_SECURE"] = "false"

        from fastapi.testclient import TestClient
        import api

        api.DataFetcher = OfflineDataFetcher

        async def offline_yahoo(query: str, limit: int = 8):
            return []

        class OfflineDiscoveryService:
            async def search_ticker(self, query: str):
                raise RuntimeError("discovery provider intentionally offline")

        api._search_yahoo_finance = offline_yahoo
        api.get_discovery_service = lambda: OfflineDiscoveryService()

        client = TestClient(api.app)
        login = client.post("/api/auth/login", json={"password": "test-pass"})
        if login.status_code != 200:
            print(f"FAIL login: HTTP {login.status_code}")
            return 1

        cases = [
            ("Robinhood", "HOOD", "equity"),
            ("Apple", "AAPL", "equity"),
            ("S&P 500 ETF", "VOO", "etf"),
            ("Bitcoin", "BTC-USD", "crypto"),
        ]
        failures: list[str] = []

        for query, expected, asset_class in cases:
            search = client.get("/api/search", params={"q": query})
            resolve = client.get("/api/search/resolve", params={"q": query})
            suggestions = client.get("/api/search/suggestions", params={"q": query})
            analysis = client.get(f"/api/analyze/{query}")

            responses = {
                "search": search,
                "resolve": resolve,
                "suggestions": suggestions,
                "analysis": analysis,
            }
            for label, response in responses.items():
                if response.status_code != 200:
                    failures.append(f"{query} {label}: HTTP {response.status_code} {response.text}")

            if any(response.status_code != 200 for response in responses.values()):
                continue

            search_tickers = [str(row.get("ticker") or "").upper() for row in search.json()]
            resolved_ticker = str(resolve.json().get("ticker") or "").upper()
            suggestion_tickers = [str(item).upper() for item in suggestions.json().get("Ticker", [])]
            analyzed_ticker = str(analysis.json().get("ticker") or "").upper()
            degraded = bool(analysis.json().get("data_quality", {}).get("degraded"))

            print(
                f"{asset_class}: {query!r} -> search={search_tickers[:1]} "
                f"resolve={resolved_ticker} analyze={analyzed_ticker} degraded={degraded}"
            )
            if expected not in search_tickers:
                failures.append(f"{query}: {expected} missing from search")
            if resolved_ticker != expected:
                failures.append(f"{query}: resolve expected {expected}, got {resolved_ticker}")
            if expected not in suggestion_tickers:
                failures.append(f"{query}: {expected} missing from suggestions")
            if analyzed_ticker != expected or not degraded:
                failures.append(f"{query}: analyzer expected degraded {expected}, got {analyzed_ticker}")

        original_resolver = api._resolve_search_results

        async def broken_resolver(query: str, limit: int = 6):
            raise RuntimeError("resolver intentionally broken")

        api._resolve_search_results = broken_resolver
        try:
            for endpoint in ("/api/search", "/api/search/resolve", "/api/search/suggestions"):
                response = client.get(endpoint, params={"q": "HOOD"})
                if response.status_code != 200:
                    failures.append(f"{endpoint}: fallback returned HTTP {response.status_code}")
        finally:
            api._resolve_search_results = original_resolver

        if failures:
            print("\nGlobal asset API failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("Global stock, ETF and crypto API QA passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
