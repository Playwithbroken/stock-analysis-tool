import asyncio
import os
import tempfile
from datetime import datetime, timezone


async def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DATA_DIR"] = tmp
        os.environ["PORTFOLIO_DB_PATH"] = os.path.join(tmp, "search-suggestions-test.db")
        os.environ["APP_ACCESS_PASSWORD"] = "test-pass"
        os.environ["APP_SESSION_SECRET"] = "x" * 64

        import api

        api._cache_forget("search:suggestions")

        class FakeDiscoveryService:
            future_star_watch = ["RKLB", "LUNR", "HOOD"]

            async def get_market_movers(self, type: str = "gainers", window: str = "1d"):
                if type == "losers":
                    return [{"ticker": "PFE", "name": "Pfizer Inc."}]
                return [
                    {"ticker": "LUNR", "name": "Intuitive Machines"},
                    {"ticker": "RGTI", "name": "Rigetti Computing"},
                ]

        api.get_discovery_service = lambda: FakeDiscoveryService()

        class FakeMorningBriefService:
            def get_cached_or_last_brief(self):
                return {
                    "event_pings": [
                        {
                            "symbols": ["XLE", "GLD"],
                            "trade_impact": {"symbols": ["TLT"]},
                        }
                    ],
                    "event_layer": [
                        {
                            "ticker": "SPY",
                            "event_intelligence": {"affected_assets": ["QQQ"]},
                        }
                    ],
                    "top_news": [{"ticker": "HOOD"}],
                    "market_movers": {},
                }

        api.get_morning_brief_service = lambda: FakeMorningBriefService()
        manager = api.get_portfolio_manager()

        manager.create_paper_trade(
            {
                "ticker": "HOOD",
                "asset_class": "equity",
                "direction": "long",
                "setup_type": "paper_learning",
                "thesis": "QA paper trade should surface in search suggestions.",
                "entry_price": 100,
                "quantity": 1,
                "confidence_score": 88,
            }
        )

        now = datetime.now(timezone.utc).isoformat()
        manager.upsert_signal_forecast(
            {
                "id": "qa-forecast-rklb",
                "signal_key": "qa:rklb:learning",
                "symbol": "RKLB",
                "direction": "long",
                "setup_type": "learning_forecast",
                "session_label": "QA",
                "source_label": "QA",
                "thesis": "QA forecast should surface in search suggestions.",
                "trigger": "Breakout confirmation",
                "invalidation": "Failed follow-through",
                "confidence": 0.82,
                "rank_score": 82,
                "expected_move": "up",
                "entry_price": 10,
                "forecast_time": now,
                "metadata_json": "{}",
                "created_at": now,
            },
            [],
        )

        suggestions = await api._build_dynamic_search_suggestions()
        cached_suggestions = await api._build_dynamic_search_suggestions()
        interesting = suggestions.get("Jetzt interessant") or []
        macro_alerts = suggestions.get("Macro Alerts") or []
        movers = suggestions.get("Market Movers") or []
        paper = suggestions.get("Paper Trading") or []
        learning = suggestions.get("Lernsignale") or []

        print(f"Jetzt interessant: {interesting}")
        print(f"Macro Alerts: {macro_alerts}")
        print(f"Market Movers: {movers}")
        print(f"Paper Trading: {paper}")
        print(f"Lernsignale: {learning}")

        if not any("(XLE)" in item for item in macro_alerts):
            print("FAIL: macro alert XLE missing from search suggestions")
            return 1
        if not any("(GLD)" in item for item in macro_alerts):
            print("FAIL: macro alert GLD missing from search suggestions")
            return 1
        if not any("(TLT)" in item for item in macro_alerts):
            print("FAIL: macro trade-impact TLT missing from search suggestions")
            return 1
        if not any("(LUNR)" in item for item in [*interesting, *movers]):
            print("FAIL: live mover LUNR missing from dynamic suggestions")
            return 1
        if not any("(PFE)" in item for item in movers):
            print("FAIL: live loser PFE missing from market mover suggestions")
            return 1
        if not any("(HOOD)" in item for item in paper):
            print("FAIL: HOOD paper trade missing from dynamic suggestions")
            return 1
        if not any("(RKLB)" in item for item in learning):
            print("FAIL: RKLB learning forecast missing from dynamic suggestions")
            return 1
        if any("paper_learning" in item or "learning_forecast" in item for item in [*paper, *learning]):
            print("FAIL: technical setup labels leaked into user-facing search suggestions")
            return 1
        if any(item.split(" (", 1)[0].strip().islower() and "_" in item.split(" (", 1)[0] for item in [*paper, *learning]):
            print("FAIL: underscored internal labels leaked into user-facing search suggestions")
            return 1
        if "meta" in cached_suggestions:
            print("FAIL: cache metadata leaked as a search suggestion category")
            return 1

    print("dynamic search suggestions QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
