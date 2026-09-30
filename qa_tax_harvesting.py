"""
QA Test Suite for Feature 10: Smart Tax Loss Harvesting & Freistellungsauftrag Manager
Tests German capital gains tax formulas (§ 20 EStG), loss pot separation,
substitute matching, FSA broker splits, and API endpoints.
"""

import os
import unittest
from starlette.testclient import TestClient

from src.tax_harvesting_service import TaxHarvestingService, KNOWN_SUBSTITUTES
from api import app


class TestTaxHarvestingService(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        pw = os.environ.get("APP_ACCESS_PASSWORD")
        if pw:
            self.client.post("/api/auth/login", json={"password": pw})

    def test_01_effective_tax_rate_formulas(self):
        """Verify German capital gains tax rate calculations with and without church tax."""
        # 1. Base rate: 25% + 5.5% Soli = 26.375%
        rate_none = TaxHarvestingService.calculate_effective_tax_rate(0.0)
        self.assertAlmostEqual(rate_none, 0.26375, places=5)

        # 2. 8% church tax (BW / Bayern): (0.25 * (1 + 0.08 + 0.055)) / (1 + 0.25 * 0.08) = 0.27819
        rate_8 = TaxHarvestingService.calculate_effective_tax_rate(0.08)
        self.assertAlmostEqual(rate_8, 0.27819, places=4)

        # 3. 9% church tax (other states): (0.25 * (1 + 0.09 + 0.055)) / (1 + 0.25 * 0.09) = 0.27995
        rate_9 = TaxHarvestingService.calculate_effective_tax_rate(0.09)
        self.assertAlmostEqual(rate_9, 0.27995, places=4)

        print("[OK] Test 1: Effective Tax Rate Math Verified")

    def test_02_loss_pot_separation_and_tax_shield(self):
        """Verify § 20 EStG separation of Aktien-Verlusttopf and Allgemeiner Verlusttopf."""
        # Portfolio with 1 stock in loss (AAPL bought at 200, current 150 = -500 EUR loss)
        # and 1 ETF in loss (URTH bought at 100, current 80 = -200 EUR loss)
        # and 1 stock in gain (MSFT bought at 200, current 300 = +1000 EUR gain)
        holdings = [
            {"ticker": "AAPL", "shares": 10, "buyPrice": 200.0, "currentPrice": 150.0, "is_etf": False},
            {"ticker": "URTH", "shares": 10, "buyPrice": 100.0, "currentPrice": 80.0, "is_etf": True},
            {"ticker": "MSFT", "shares": 10, "buyPrice": 200.0, "currentPrice": 300.0, "is_etf": False},
        ]

        res = TaxHarvestingService.analyze_portfolio(
            holdings=holdings,
            church_tax_type="none",
            fsa_allowance=1000.0,
            fsa_used=200.0
        )

        self.assertEqual(len(res["loss_candidates_stocks"]), 1)
        self.assertEqual(len(res["loss_candidates_general"]), 1)
        self.assertEqual(res["gain_positions_count"], 1)

        # Check stock loss
        stock_item = res["loss_candidates_stocks"][0]
        self.assertEqual(stock_item["ticker"], "AAPL")
        self.assertEqual(stock_item["loss_pot"], "Aktien-Verlusttopf")
        self.assertEqual(stock_item["gain_loss_eur"], -500.0)
        # Tax shield = 500 * 0.26375 = 131.88 EUR
        self.assertAlmostEqual(stock_item["potential_tax_shield_eur"], 131.88, places=1)

        # Check ETF loss
        etf_item = res["loss_candidates_general"][0]
        self.assertEqual(etf_item["ticker"], "URTH")
        self.assertEqual(etf_item["loss_pot"], "Allgemeiner Verlusttopf")
        self.assertEqual(etf_item["gain_loss_eur"], -200.0)
        # Tax shield = 200 * 0.26375 = 52.75 EUR
        self.assertAlmostEqual(etf_item["potential_tax_shield_eur"], 52.75, places=1)

        # Total tax shield
        self.assertAlmostEqual(res["total_potential_tax_shield_eur"], 131.88 + 52.75, places=1)
        self.assertEqual(res["total_unrealized_stock_loss_eur"], 500.0)
        self.assertEqual(res["total_unrealized_general_loss_eur"], 200.0)

        print("[OK] Test 2: Loss Pot Separation & Tax Shield Verified")

    def test_03_substitute_recommendations(self):
        """Verify market-continuation substitute matching."""
        sub_urth = KNOWN_SUBSTITUTES.get("URTH")
        self.assertIsNotNone(sub_urth)
        self.assertEqual(sub_urth["substitute_ticker"], "VWCE.DE")
        self.assertGreater(sub_urth["correlation"], 0.95)

        sub_spy = KNOWN_SUBSTITUTES.get("SPY")
        self.assertIsNotNone(sub_spy)
        self.assertEqual(sub_spy["substitute_ticker"], "SXR8.DE")

        sub_aapl = KNOWN_SUBSTITUTES.get("AAPL")
        self.assertIsNotNone(sub_aapl)
        self.assertEqual(sub_aapl["substitute_ticker"], "MSFT")

        print("[OK] Test 3: Substitute Matching Logic Verified")

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/tax-harvesting and POST endpoints."""
        create_res = self.client.post("/api/portfolios", json={"name": "Tax Harvesting Test Portfolio"})
        self.assertEqual(create_res.status_code, 200)
        p_id = create_res.json()["id"]

        try:
            self.client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 220.0})
            self.client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "URTH", "shares": 20, "buyPrice": 120.0})

            # 1. GET request
            resp_get = self.client.get(f"/api/portfolio/{p_id}/tax-harvesting?church_tax=none&fsa_allowance=1000&fsa_used=250")
            self.assertEqual(resp_get.status_code, 200)
            data_get = resp_get.json()
            self.assertEqual(data_get["portfolio_id"], p_id)
            self.assertIn("total_potential_tax_shield_eur", data_get)
            self.assertIn("fsa", data_get)
            self.assertEqual(data_get["fsa"]["used_amount"], 250.0)
            self.assertEqual(data_get["fsa"]["remaining_amount"], 750.0)

            # 2. POST request with 9% church tax & 2000 FSA
            resp_post = self.client.post(
                f"/api/portfolio/{p_id}/tax-harvesting",
                json={"church_tax_type": "9%", "fsa_allowance": 2000.0, "fsa_used": 500.0}
            )
            self.assertEqual(resp_post.status_code, 200)
            data_post = resp_post.json()
            self.assertAlmostEqual(data_post["effective_tax_rate_pct"], 27.995, places=2)
            self.assertEqual(data_post["fsa"]["total_allowance"], 2000.0)
            self.assertEqual(data_post["fsa"]["remaining_amount"], 1500.0)

            # 3. 404 for missing portfolio
            resp_404 = self.client.get("/api/portfolio/invalid-999999/tax-harvesting")
            self.assertEqual(resp_404.status_code, 404)

            print("[OK] Test 4: All Tax Harvesting API Endpoints Verified")
        finally:
            self.client.delete(f"/api/portfolios/{p_id}")


if __name__ == "__main__":
    unittest.main()
