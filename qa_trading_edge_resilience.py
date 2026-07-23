from __future__ import annotations

import os
import tempfile
import time


class StubPortfolioManager:
    def get_signal_watch_items(self):
        return [{"kind": "ticker", "value": "AAPL"}]


class StubSignalService:
    def build_watchlist_snapshot(self, items):
        return {"items": items or []}


class FastMorningBriefService:
    def get_trading_edge(self, snapshot=None):
        return {
            "regime": {"vix": {"value": 15.2, "change": -0.4, "regime": "normal"}},
            "sectors": [{"ticker": "XLK", "name": "Technology", "change_1d": 0.4, "change_5d": 1.2}],
        }


class SlowMorningBriefService:
    def get_trading_edge(self, snapshot=None):
        time.sleep(0.05)
        return {"regime": {"vix": {"value": 19.0, "change": 1.1, "regime": "elevated"}}}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "trading-edge-resilience.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64
        os.environ["APP_COOKIE_SECURE"] = "false"
        os.environ["TRADING_EDGE_HTTP_CACHE_TTL_SECONDS"] = "300"
        os.environ["TRADING_EDGE_STALE_CACHE_TTL_SECONDS"] = "1800"

        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)
        original_manager = api.get_portfolio_manager
        original_signal_service = api.get_public_signal_service
        original_brief_service = api.get_morning_brief_service

        failures: list[str] = []
        try:
            login = client.post("/api/auth/login", json={"password": "test-pass"})
            if login.status_code != 200:
                failures.append(f"login returned HTTP {login.status_code}")

            api.get_portfolio_manager = lambda: StubPortfolioManager()
            api.get_public_signal_service = lambda: StubSignalService()

            api._cache_forget(api.TRADING_EDGE_CACHE_KEY)
            os.environ["TRADING_EDGE_API_TIMEOUT_SECONDS"] = "2"
            api.get_morning_brief_service = lambda: FastMorningBriefService()
            generated = client.get("/api/market/trading-edge")
            generated_payload = generated.json()
            if generated.status_code != 200:
                failures.append(f"generated response returned HTTP {generated.status_code}")
            elif generated_payload.get("meta", {}).get("delivery_mode") != "generated":
                failures.append(f"generated metadata missing: {generated_payload.get('meta')}")
            elif not generated_payload.get("regime", {}).get("vix"):
                failures.append("generated payload missed vix regime data")

            api.get_morning_brief_service = lambda: (_ for _ in ()).throw(RuntimeError("cache should be used"))
            cached = client.get("/api/market/trading-edge")
            cached_payload = cached.json()
            if cached.status_code != 200:
                failures.append(f"cached response returned HTTP {cached.status_code}")
            elif cached_payload.get("meta", {}).get("cached") is not True:
                failures.append(f"cached metadata missing: {cached_payload.get('meta')}")
            elif not cached_payload.get("regime", {}).get("vix"):
                failures.append("cached payload lost generated data")

            api._cache_forget(api.TRADING_EDGE_CACHE_KEY)
            os.environ["TRADING_EDGE_API_TIMEOUT_SECONDS"] = "0.001"
            api.get_morning_brief_service = lambda: SlowMorningBriefService()
            timeout = client.get("/api/market/trading-edge")
            timeout_payload = timeout.json()
            if timeout.status_code != 200:
                failures.append(f"timeout response returned HTTP {timeout.status_code}")
            elif timeout_payload.get("meta", {}).get("refresh_state") != "timeout":
                failures.append(f"timeout did not return degraded metadata: {timeout_payload}")
        finally:
            api.get_portfolio_manager = original_manager
            api.get_public_signal_service = original_signal_service
            api.get_morning_brief_service = original_brief_service
            api._cache_forget(api.TRADING_EDGE_CACHE_KEY)

        if failures:
            print("\nTrading Edge resilience failures:")
            for failure in failures:
                print(f"- {failure}")
            return 1

    print("Trading Edge resilience QA passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
