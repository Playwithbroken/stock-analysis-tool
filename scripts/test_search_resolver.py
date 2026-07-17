import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import api


class SlowDiscovery:
    async def search_ticker(self, _query):
        await asyncio.sleep(1)
        return []


class WorkingDiscovery:
    async def search_ticker(self, _query):
        return [
            {
                "ticker": "LIVEONLY",
                "name": "Live Only Corp",
                "type": "EQUITY",
                "source": "discovery_test",
            }
        ]


async def quote_result(_query, limit=8):
    return [
        {
            "ticker": "ZZSEARCH",
            "name": "ZZ Search Corp",
            "type": "EQUITY",
            "source": "quote_test",
        }
    ]


async def failed_quote(_query, limit=8):
    raise RuntimeError("quote provider unavailable")


async def run_tests():
    api._RESPONSE_CACHE.clear()
    with (
        patch.object(api, "SEARCH_DISCOVERY_TIMEOUT_SECONDS", 0.02),
        patch.object(api, "SEARCH_QUOTE_PROVIDER_TIMEOUT_SECONDS", 0.1),
        patch.object(api, "get_discovery_service", return_value=SlowDiscovery()),
        patch.object(api, "_search_yahoo_finance", side_effect=quote_result),
    ):
        results = await api._resolve_search_results("ZZSEARCH", limit=6)
        assert results and results[0]["ticker"] == "ZZSEARCH", results

    api._RESPONSE_CACHE.clear()
    with (
        patch.object(api, "SEARCH_DISCOVERY_TIMEOUT_SECONDS", 0.1),
        patch.object(api, "SEARCH_QUOTE_PROVIDER_TIMEOUT_SECONDS", 0.1),
        patch.object(api, "get_discovery_service", return_value=WorkingDiscovery()),
        patch.object(api, "_search_yahoo_finance", side_effect=failed_quote),
    ):
        results = await api._resolve_search_results("LIVEONLY", limit=6)
        assert results and results[0]["ticker"] == "LIVEONLY", results

    print("search resolver tests passed")


if __name__ == "__main__":
    asyncio.run(run_tests())
