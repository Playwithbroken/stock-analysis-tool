import ast
import asyncio
import copy
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

from src.data_fetcher import DataFetcher


class FakeChartResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "chart": {
                "result": [{
                    "timestamp": [1717200000, 1719792000],
                    "indicators": {
                        "quote": [{"close": [100.0, 105.0], "volume": [1000, 1200]}],
                    },
                }],
            },
        }


def test_history_failures_keep_requested_range() -> None:
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.ticker = "TEST"
    fetcher.stock = Mock()
    fetcher.stock.history.side_effect = RuntimeError("provider unavailable")
    with patch("src.data_fetcher.requests.get", side_effect=RuntimeError("direct unavailable")) as direct:
        try:
            fetcher.get_history("5d", "15m")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Provider failure must not create history")
        assert direct.call_count == 1
        assert direct.call_args.kwargs["params"] == {"range": "5d", "interval": "15m"}
        fetcher.stock.history.assert_called_once_with(period="5d", interval="15m", auto_adjust=False)


def test_history_endpoint_outage_contract() -> None:
    # Execute the real route without booting unrelated services or using network.
    tree = ast.parse(Path(__file__).with_name("api.py").read_text(encoding="utf-8"))
    route = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_history")
    route.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[route], type_ignores=[]))
    cache = {}
    writes = []
    calls = []
    state = {"fresh": True, "available": True}
    points = [{"time": "2026-08-25", "price": 100}, {"time": "2026-08-31", "price": 105}]

    class FakeFetcher:
        def __init__(self, ticker):
            self.ticker = ticker

        def get_history(self, period, interval):
            calls.append((self.ticker, period, interval))
            return copy.deepcopy(points) if state["available"] else []

    def save(key, value):
        writes.append(key)
        cache[key] = value
        return value

    with ThreadPoolExecutor(max_workers=1) as executor:
        scope = {
            "asyncio": asyncio, "copy": copy, "os": os,
            "Dict": Dict, "Any": Any, "Optional": Optional, "List": List,
            "DataFetcher": FakeFetcher, "_HISTORY_EXECUTOR": executor,
            "_cache_get": lambda key, ttl: cache.get(key) if state["fresh"] else None,
            "_cache_get_stale": lambda key, ttl: cache.get(key),
            "_cache_set": save, "_safe_int_env": lambda key, default, **kwargs: default,
            "convert_numpy_types": lambda value: value,
        }
        exec(compile(module, "api.py:get_history", "exec"), scope)

        async def check():
            history = scope["get_history"]
            live = await history("test", "5d", "15m")
            assert live["items"] == points and live["meta"]["mode"] == "live"
            assert calls == [("TEST", "5d", "15m")]
            assert await history("test", "5d", "15m") == live
            assert len(calls) == 1, "Fresh exact-range cache must be reused"

            state.update(fresh=False, available=False)
            stale = await history("test", "5d", "15m")
            assert stale["items"] == points and stale["meta"]["mode"] == "stale"
            assert stale["meta"]["period"] == "5d"
            assert live["meta"]["mode"] == "live", "Stale response must not mutate original data"

            writes.clear()
            empty = await history("test", "max", "1mo")
            assert empty["items"] == [] and empty["meta"]["mode"] == "unavailable"
            assert writes == [], "Outages must not be cached or replace last-good history"
            assert calls[-1] == ("TEST", "max", "1mo")
            before = len(calls)
            await history("test", "max", "1mo")
            assert len(calls) == before + 1, "Retry must actually ask the provider again"

        asyncio.run(check())


def main() -> None:
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.ticker = "TEST"
    with patch("src.data_fetcher.requests.get", return_value=FakeChartResponse()) as chart_request:
        monthly = fetcher.get_history("5y", "1mo")
        assert len(monthly) == 2
        assert monthly[0]["time"] == "2024-06-01"
        assert monthly[1]["time"] == "2024-07-01"
        assert monthly[1]["price"] == 105.0
        assert monthly[1]["full_date"].startswith("2024-07-01T")

        intraday = fetcher.get_history("1d", "5m")
        assert intraday[0]["time"] == "00:00"
        assert intraday[1]["time"] == "00:00"

        five_day = fetcher.get_history("5d", "15m")
        assert len(five_day) == 2
        assert chart_request.call_args.kwargs["params"] == {"range": "5d", "interval": "15m"}

    test_history_failures_keep_requested_range()
    test_history_endpoint_outage_contract()
    print("chart history contract QA passed (range fidelity, cache, outage, retry)")


if __name__ == "__main__":
    main()
