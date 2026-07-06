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
        paper = suggestions.get("Paper Trading") or []
        learning = suggestions.get("Lernsignale") or []

        print(f"Paper Trading: {paper}")
        print(f"Lernsignale: {learning}")

        if not any("(HOOD)" in item for item in paper):
            print("FAIL: HOOD paper trade missing from dynamic suggestions")
            return 1
        if not any("(RKLB)" in item for item in learning):
            print("FAIL: RKLB learning forecast missing from dynamic suggestions")
            return 1

    print("dynamic search suggestions QA ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
