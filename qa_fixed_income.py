"""
Automated QA Test Suite for Feature 21:
Institutional Fixed Income & Bond Yield Curve Analytics Terminal
(Yield-to-Maturity, Modified Duration, MacAulay Duration, Convexity, DV01 & Yield Curve Shifts).
"""

import unittest
import os
from fastapi.testclient import TestClient
from src.fixed_income_service import FixedIncomeService


class TestFixedIncomeTerminal(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "shares": 50, "current_price": 90.0},    # 4,500 EUR (Long Duration ~16.8)
            {"ticker": "BND", "name": "Vanguard Total Bond Market ETF", "shares": 60, "current_price": 75.0},         # 4,500 EUR (Aggregate ~6.5)
            {"ticker": "SHY", "name": "iShares 1-3 Year Treasury Bond ETF", "shares": 30, "current_price": 82.0},     # 2,460 EUR (Short Duration ~1.9)
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 20, "current_price": 200.0},                           # 4,000 EUR (Equity proxy)
        ]
        self.total_val = 15460.0

    def test_01_duration_and_convexity_mathematics(self):
        """Verify 2nd order Taylor expansion: Delta P = -ModD * dy + 0.5 * Convexity * dy^2."""
        mod_d = 7.5
        conv = 0.85

        # Rate hike +100 bps (+0.01)
        hike_100 = FixedIncomeService.calculate_price_change(mod_d, conv, 100)
        # First order would be -7.50%, convexity adds +0.5 * 0.85 * (0.01)^2 * 100 = +0.00425% -> ~ -7.496%
        self.assertLess(hike_100, 0.0)
        self.assertAlmostEqual(hike_100, -7.50, places=1)

        # Rate cut -100 bps (-0.01)
        cut_100 = FixedIncomeService.calculate_price_change(mod_d, conv, -100)
        self.assertGreater(cut_100, 0.0)
        self.assertAlmostEqual(cut_100, 7.50, places=1)

        # Convexity property: Price gain on -100 bps is slightly greater than price loss on +100 bps in absolute terms
        self.assertGreaterEqual(abs(cut_100), abs(hike_100))

    def test_02_dv01_and_portfolio_aggregation(self):
        """Verify DV01 = Value * ModD * 0.0001 and portfolio duration weighting."""
        res = FixedIncomeService.analyze_portfolio_fixed_income(self.sample_holdings, self.total_val)
        self.assertTrue(res["valid"])

        summary = res["summary"]
        self.assertGreater(summary["modified_duration"], 0.0)
        self.assertGreater(summary["macaulay_duration"], summary["modified_duration"])
        self.assertGreater(summary["convexity"], 0.0)

        # DV01 must equal Portfolio Value * ModD * 0.0001
        expected_dv01 = round(self.total_val * summary["modified_duration"] * 0.0001, 2)
        self.assertAlmostEqual(summary["dv01_eur"], expected_dv01, places=1)

        # Scenarios check
        scenarios = res["scenarios"]
        self.assertEqual(len(scenarios), 5)
        for sc in scenarios:
            if sc["shift_bps"] > 0:
                self.assertLess(sc["delta_eur"], 0.0)
            elif sc["shift_bps"] < 0:
                self.assertGreater(sc["delta_eur"], 0.0)

    def test_03_rating_distribution_and_sleeve(self):
        """Verify rating distribution partitions correctly and sleeve percentage."""
        res = FixedIncomeService.analyze_portfolio_fixed_income(self.sample_holdings, self.total_val)
        self.assertTrue(res["valid"])

        ratings = res["rating_distribution"]
        total_rating_pct = sum(r["weight_pct"] for r in ratings)
        self.assertAlmostEqual(total_rating_pct, 100.0, places=1)

        # Fixed income sleeve is significant
        self.assertGreater(res["fixed_income_sleeve_pct"], 50.0)

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/fixed-income and POST /api/portfolio/fixed-income/simulate."""
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
            create_res = client.post("/api/portfolio/create", json={"name": "Fixed Income QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "BND", "shares": 30, "buyPrice": 75}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "BND", "shares": 30, "buyPrice": 75}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/fixed-income
        fi_res = client.get(f"/api/portfolio/{p_id}/fixed-income", cookies=cookies)
        self.assertEqual(fi_res.status_code, 200)
        fi_json = fi_res.json()
        self.assertTrue(fi_json.get("valid"))
        self.assertIn("summary", fi_json)
        self.assertIn("scenarios", fi_json)
        self.assertIn("rating_distribution", fi_json)
        self.assertIn("holdings", fi_json)

        # 3. POST /api/portfolio/fixed-income/simulate
        sim_res = client.post(
            "/api/portfolio/fixed-income/simulate",
            json={"portfolio_id": p_id, "shift_bps": 75.0},
            cookies=cookies
        )
        self.assertEqual(sim_res.status_code, 200)
        sim_json = sim_res.json()
        self.assertEqual(sim_json["shift_bps"], 75.0)
        self.assertIn("delta_eur", sim_json)


if __name__ == "__main__":
    unittest.main()
