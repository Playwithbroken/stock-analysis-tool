from __future__ import annotations

import asyncio

import src.discovery_service as discovery_module
from src.discovery_service import DiscoveryService


class FailingDataFetcher:
    def __init__(self, ticker: str) -> None:
        raise RuntimeError(f"provider unavailable for {ticker}")


async def test_discovery_fallbacks_when_provider_fails() -> None:
    original = discovery_module.DataFetcher
    discovery_module.DataFetcher = FailingDataFetcher  # type: ignore[assignment]
    try:
        service = DiscoveryService()

        heatmap = await service.get_sentiment_heatmap()
        assert heatmap
        assert heatmap[0]["fallback"] is True
        assert heatmap[0]["hot_stocks"]

        etfs = await service.get_etfs()
        assert etfs
        assert etfs[0]["ticker"]
        assert "Fallback" in etfs[0]["trend_context"]

        stars = await service.get_star_assets()
        assert stars["day_winner"]
        assert stars["day_loser"]
        assert stars["for_you"]
    finally:
        discovery_module.DataFetcher = original  # type: ignore[assignment]


if __name__ == "__main__":
    asyncio.run(test_discovery_fallbacks_when_provider_fails())
    print("qa_discovery_resilience: ok")
