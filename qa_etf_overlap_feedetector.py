"""
QA Test Suite for Feature 9: ETF Overlap & Fee Vampire (Gebuehren-Vampir) Detector
Tests pairwise ETF overlap, look-through concentration, compound fee simulation, and API endpoints.
"""

import os
import unittest
from starlette.testclient import TestClient

from src.etf_overlap_service import ETFOverlapService, KNOWN_ETF_PROFILES
from api import app


class TestETFOverlapFeeDetector(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        pw = os.environ.get("APP_ACCESS_PASSWORD")
        if pw:
            self.client.post("/api/auth/login", json={"password": pw})

    def test_01_pairwise_overlap_math(self):
        """Verify pairwise ETF overlap logic and symmetry."""
        # 1. Self overlap must be 100%
        self_res = ETFOverlapService.calculate_pairwise_overlap("SPY", "SPY")
        self.assertAlmostEqual(self_res["overlap_percentage"], 100.0, places=1)
        self.assertEqual(self_res["shared_holdings_count"], len(KNOWN_ETF_PROFILES["SPY"]["holdings"]))

        # 2. Overlap between S&P 500 (SPY) and Nasdaq 100 (QQQ)
        overlap_spy_qqq = ETFOverlapService.calculate_pairwise_overlap("SPY", "QQQ")
        self.assertGreater(overlap_spy_qqq["overlap_percentage"], 30.0)
        self.assertLess(overlap_spy_qqq["overlap_percentage"], 80.0)
        self.assertGreater(overlap_spy_qqq["shared_holdings_count"], 5)

        # 3. Symmetry: overlap(A, B) == overlap(B, A)
        overlap_qqq_spy = ETFOverlapService.calculate_pairwise_overlap("QQQ", "SPY")
        self.assertAlmostEqual(
            overlap_spy_qqq["overlap_percentage"],
            overlap_qqq_spy["overlap_percentage"],
            places=2
        )

        # 4. European alias resolution (e.g. EUNL.DE -> URTH)
        alias_res = ETFOverlapService.calculate_pairwise_overlap("EUNL.DE", "SXR8.DE")
        self.assertGreater(alias_res["overlap_percentage"], 50.0)
        print("[OK] Test 1: Pairwise ETF Overlap Math & Aliases Passed")

    def test_02_portfolio_look_through_concentration(self):
        """Verify look-through holding decomposition combining direct shares and ETFs."""
        # Portfolio with 50% MSCI World (URTH) and 50% direct Apple shares (AAPL)
        holdings = [
            {"ticker": "URTH", "shares": 10, "buyPrice": 100.0},  # Value: 1000 EUR
            {"ticker": "AAPL", "shares": 10, "buyPrice": 100.0},  # Value: 1000 EUR
        ]
        # URTH has 4.8% AAPL -> 50% * 4.8% = 2.4% indirect AAPL
        # Direct AAPL is 50.0%
        # Total effective AAPL = 52.4%

        res = ETFOverlapService.analyze_portfolio(holdings, monthly_savings=250.0, gross_return=0.07)
        self.assertEqual(res["total_portfolio_value"], 2000.0)
        self.assertEqual(res["etf_count"], 1)
        self.assertEqual(res["single_stock_count"], 1)

        clusters = res["top_look_through_clusters"]
        self.assertGreater(len(clusters), 0)

        aapl_cluster = next((c for c in clusters if c["ticker"] == "AAPL"), None)
        self.assertIsNotNone(aapl_cluster)
        self.assertAlmostEqual(aapl_cluster["effective_portfolio_weight_pct"], 52.4, places=1)
        self.assertTrue(aapl_cluster["is_mega_cluster"])

        # Cluster warning should be triggered
        self.assertIsNotNone(res["cluster_warning"])
        self.assertIn("AAPL", res["cluster_warning"])
        print("[OK] Test 2: Look-Through Concentration Passed")

    def test_03_fee_vampire_simulation_and_scores(self):
        """Verify weighted TER, compound fee loss over 10, 20, 30 years and Vampire score."""
        # 1. Low-cost ETF portfolio (SPY 0.07% TER)
        cheap_holdings = [{"ticker": "SPY", "shares": 100, "buyPrice": 100.0}]
        cheap_res = ETFOverlapService.analyze_portfolio(cheap_holdings, monthly_savings=250.0, gross_return=0.07)
        self.assertEqual(cheap_res["fee_score"], "CHAMPION")
        self.assertAlmostEqual(cheap_res["weighted_ter_pct"], 0.07, places=2)

        # 2. High-cost ETF portfolio (ARKK 0.75% TER)
        vampire_holdings = [{"ticker": "ARKK", "shares": 100, "buyPrice": 100.0}]
        vampire_res = ETFOverlapService.analyze_portfolio(vampire_holdings, monthly_savings=250.0, gross_return=0.07)
        self.assertEqual(vampire_res["fee_score"], "VAMPIRE")
        self.assertAlmostEqual(vampire_res["weighted_ter_pct"], 0.75, places=2)

        # Check simulations (10, 20, 30 years)
        sims = vampire_res["fee_simulations"]
        self.assertEqual(len(sims), 3)
        sim_30y = next(s for s in sims if s["years"] == 30)
        self.assertGreater(sim_30y["lost_to_fees"], 10000.0)
        self.assertGreater(sim_30y["fee_drag_pct"], 5.0)

        # Expensive positions check
        self.assertEqual(len(vampire_res["expensive_positions"]), 1)
        self.assertEqual(vampire_res["expensive_positions"][0]["ticker"], "ARKK")
        print("[OK] Test 3: Fee Vampire Simulation & Score Passed")

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/etf-overlap, POST, and GET /api/etf/compare."""
        # Create a test portfolio
        create_res = self.client.post("/api/portfolios", json={"name": "ETF QA Test Portfolio"})
        self.assertEqual(create_res.status_code, 200)
        p_id = create_res.json()["id"]

        try:
            self.client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "URTH", "shares": 50, "buyPrice": 100.0})
            self.client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "QQQ", "shares": 20, "buyPrice": 250.0})

            # 1. GET /api/portfolio/{p_id}/etf-overlap
            resp_get = self.client.get(f"/api/portfolio/{p_id}/etf-overlap")
            self.assertEqual(resp_get.status_code, 200)
            data_get = resp_get.json()
            self.assertEqual(data_get["portfolio_id"], p_id)
            self.assertEqual(data_get["etf_count"], 2)
            self.assertIn("fee_score", data_get)
            self.assertIn("fee_simulations", data_get)
            self.assertEqual(len(data_get["etf_overlap_matrix"]), 2)

            # 2. POST /api/portfolio/{p_id}/etf-overlap with custom parameters
            resp_post = self.client.post(
                f"/api/portfolio/{p_id}/etf-overlap",
                json={"monthly_savings": 500.0, "gross_return": 0.08}
            )
            self.assertEqual(resp_post.status_code, 200)
            data_post = resp_post.json()
            self.assertEqual(data_post["monthly_savings_input"], 500.0)

            # 3. GET /api/etf/compare
            resp_comp = self.client.get("/api/etf/compare?etf1=URTH&etf2=QQQ")
            self.assertEqual(resp_comp.status_code, 200)
            data_comp = resp_comp.json()
            self.assertIn("overlap_percentage", data_comp)
            self.assertIn("shared_holdings", data_comp)

            # 4. 404 on invalid portfolio
            resp_404 = self.client.get("/api/portfolio/invalid-999999/etf-overlap")
            self.assertEqual(resp_404.status_code, 404)

            print("[OK] Test 4: All API Endpoints Verified")
        finally:
            self.client.delete(f"/api/portfolios/{p_id}")


if __name__ == "__main__":
    unittest.main()
