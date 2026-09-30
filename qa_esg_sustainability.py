"""
Automated QA Test Suite for Feature 17:
Institutional ESG & Sustainability Radar (SFDR Article 8/9, Carbon Intensity WACI, Controversy & Exclusion Screening).
"""

import unittest
import os
from fastapi.testclient import TestClient
from src.esg_service import ESGService


class TestESGSustainability(unittest.TestCase):

    def setUp(self):
        self.clean_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 10, "current_price": 180.0},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "shares": 5, "current_price": 400.0},
            {"ticker": "SAP", "name": "SAP SE", "shares": 10, "current_price": 180.0},
        ]
        self.dirty_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 10, "current_price": 180.0},
            {"ticker": "RHM", "name": "Rheinmetall AG", "shares": 5, "current_price": 500.0},
            {"ticker": "XOM", "name": "Exxon Mobil", "shares": 10, "current_price": 110.0},
        ]

    def test_01_portfolio_esg_weighting_math(self):
        """Verify weighted average ESG scores, E-S-G pillars, and WACI carbon intensity."""
        res = ESGService.analyze_portfolio_esg(self.clean_holdings)
        self.assertTrue(res.get("valid"))
        self.assertGreaterEqual(res["portfolio_esg_score"], 75.0)
        self.assertIn(res["portfolio_esg_rating"], ["AAA", "AA"])

        # Check pillar scores
        p = res["pillars"]
        self.assertGreaterEqual(p["environmental"], 70.0)
        self.assertGreaterEqual(p["social"], 70.0)
        self.assertGreaterEqual(p["governance"], 70.0)

        # Check WACI
        ci = res["carbon_intensity"]
        self.assertLess(ci["portfolio_waci"], ci["benchmark_waci"])
        self.assertTrue(ci["is_cleaner_than_benchmark"])

    def test_02_sfdr_classification_rules(self):
        """Verify that clean tech portfolios receive Article 8 or 9, while excluded assets downgrade to Article 6."""
        # Clean portfolio
        res_clean = ESGService.analyze_portfolio_esg(self.clean_holdings)
        sfdr_clean = res_clean["sfdr"]["classification"]
        self.assertTrue("Artikel 8" in sfdr_clean or "Artikel 9" in sfdr_clean)
        self.assertFalse(res_clean["exclusions"]["has_violations"])

        # Dirty portfolio with weapons (RHM)
        res_dirty = ESGService.analyze_portfolio_esg(self.dirty_holdings)
        sfdr_dirty = res_dirty["sfdr"]["classification"]
        self.assertIn("Artikel 6", sfdr_dirty)
        self.assertTrue(res_dirty["exclusions"]["has_violations"])
        self.assertGreaterEqual(res_dirty["exclusions"]["violations_count"], 1)

    def test_03_single_stock_esg_and_exclusions(self):
        """Verify single stock ESG profile fetching and exclusion flag mapping."""
        # Microsoft (AAA)
        msft = ESGService.get_stock_esg_profile("MSFT")
        self.assertEqual(msft["esg_rating"], "AAA")
        self.assertFalse(msft["exclusions"]["weapons"])

        # Rheinmetall (Weapons exclusion)
        rhm = ESGService.get_stock_esg_profile("RHM")
        self.assertTrue(rhm["exclusions"]["weapons"])

        # British American Tobacco (Tobacco exclusion)
        bti = ESGService.get_stock_esg_profile("BTI")
        self.assertTrue(bti["exclusions"]["tobacco"])

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/esg, GET /api/stock/{ticker}/esg, and POST /api/portfolio/esg/analyze."""
        import api
        client = TestClient(api.app)

        pw = os.environ.get("APP_ACCESS_PASSWORD", "testpass123")
        login_res = client.post("/api/auth/login", json={"password": pw})
        session_cookie = login_res.cookies.get("session_id")
        cookies = {"session_id": session_cookie} if session_cookie else {}

        # 1. Fetch or create portfolio
        pf_list_res = client.get("/api/portfolios", cookies=cookies)
        self.assertEqual(pf_list_res.status_code, 200)
        pfs = pf_list_res.json()
        if not pfs:
            create_res = client.post("/api/portfolio/create", json={"name": "ESG QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/esg
        esg_res = client.get(f"/api/portfolio/{p_id}/esg", cookies=cookies)
        self.assertEqual(esg_res.status_code, 200)
        esg_json = esg_res.json()
        self.assertTrue(esg_json.get("valid"))
        self.assertIn("portfolio_esg_score", esg_json)
        self.assertIn("sfdr", esg_json)
        self.assertIn("carbon_intensity", esg_json)

        # 3. GET /api/stock/{ticker}/esg
        stock_res = client.get("/api/stock/AAPL/esg", cookies=cookies)
        self.assertEqual(stock_res.status_code, 200)
        stock_json = stock_res.json()
        self.assertEqual(stock_json.get("ticker"), "AAPL")

        # 4. POST /api/portfolio/esg/analyze
        custom_res = client.post(
            "/api/portfolio/esg/analyze",
            json={"tickers": ["AAPL", "SAP"]},
            cookies=cookies
        )
        self.assertEqual(custom_res.status_code, 200)
        custom_json = custom_res.json()
        self.assertTrue(custom_json.get("valid"))


if __name__ == "__main__":
    unittest.main()
