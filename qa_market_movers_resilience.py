import asyncio
import unittest
import time
from src.discovery_service import DiscoveryService, FALLBACK_MOVERS

class TestMarketMoversResilience(unittest.TestCase):
    def setUp(self):
        self.service = DiscoveryService()

    def test_market_movers_live_and_cached(self):
        async def run():
            t0 = time.time()
            g_task = self.service.get_market_movers("gainers", "1d")
            l_task = self.service.get_market_movers("losers", "1d")
            gainers, losers = await asyncio.gather(g_task, l_task)
            first_elapsed = time.time() - t0

            self.assertGreaterEqual(len(gainers), 4)
            self.assertGreaterEqual(len(losers), 4)
            for g in gainers:
                self.assertIn("ticker", g)
                self.assertIn("change", g)
                self.assertIn("price", g)
            for l in losers:
                self.assertIn("ticker", l)
                self.assertIn("change", l)
                self.assertIn("price", l)

            # Check cached speed
            t1 = time.time()
            g2 = await self.service.get_market_movers("gainers", "1d")
            l2 = await self.service.get_market_movers("losers", "1d")
            second_elapsed = time.time() - t1
            self.assertLess(second_elapsed, 0.1) # Must be instant from cache
            self.assertEqual(len(g2), len(gainers))
            self.assertEqual(len(l2), len(losers))

        asyncio.run(run())

    def test_fallback_structure(self):
        for window in ["1d", "1w", "1m"]:
            self.assertIn(window, FALLBACK_MOVERS)
            self.assertIn("gainers", FALLBACK_MOVERS[window])
            self.assertIn("losers", FALLBACK_MOVERS[window])
            self.assertGreaterEqual(len(FALLBACK_MOVERS[window]["gainers"]), 5)
            self.assertGreaterEqual(len(FALLBACK_MOVERS[window]["losers"]), 5)

if __name__ == "__main__":
    unittest.main()
