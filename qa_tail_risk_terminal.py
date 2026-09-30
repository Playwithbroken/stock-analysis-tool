"""
Automated QA Test Suite for Feature 16:
Institutional Tail Risk, Value-at-Risk (VaR/CVaR) & Underwater Drawdown Terminal.
"""

import unittest
import os
import math
from fastapi.testclient import TestClient
from src.tail_risk_service import TailRiskService


class TestTailRiskTerminal(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 20, "current_price": 180.0},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "shares": 10, "current_price": 400.0},
            {"ticker": "GOOGL", "name": "Alphabet Inc.", "shares": 15, "current_price": 150.0},
        ]
        self.total_val = 50000.0

    def test_01_var_and_cvar_mathematics(self):
        """Verify fundamental mathematical invariants of VaR and Expected Shortfall."""
        res = TailRiskService.analyze_portfolio_tail_risk(
            holdings=self.sample_holdings,
            total_portfolio_value=self.total_val,
            timeframe="1y"
        )
        self.assertTrue(res.get("valid"))
        vm = res["var_matrix"]

        # Invariant 1: 99% VaR >= 95% VaR
        self.assertGreaterEqual(vm["historical_var_99_pct"], vm["historical_var_95_pct"])
        self.assertGreaterEqual(vm["parametric_var_99_pct"], vm["parametric_var_95_pct"])

        # Invariant 2: Expected Shortfall (CVaR) >= VaR
        self.assertGreaterEqual(vm["expected_shortfall_95_pct"], vm["historical_var_95_pct"] - 1e-4)
        self.assertGreaterEqual(vm["expected_shortfall_99_pct"], vm["historical_var_99_pct"] - 1e-4)

        # Invariant 3: Cornish-Fisher VaR should be strictly non-negative and valid
        self.assertGreaterEqual(vm["cornish_fisher_var_95_pct"], 0.0)
        self.assertGreaterEqual(vm["cornish_fisher_var_99_pct"], 0.0)

    def test_02_underwater_drawdown_and_ulcer_index(self):
        """Verify underwater drawdown curve bounds and Ulcer Index consistency."""
        res = TailRiskService.analyze_portfolio_tail_risk(
            holdings=self.sample_holdings,
            total_portfolio_value=self.total_val,
            timeframe="1y"
        )
        dd = res["drawdown"]
        self.assertLessEqual(dd["max_drawdown_pct"], 0.0)
        self.assertGreaterEqual(dd["ulcer_index"], 0.0)

        # Check underwater chart points
        chart = res.get("underwater_chart", [])
        self.assertGreater(len(chart), 5)
        for pt in chart:
            self.assertLessEqual(pt["drawdown_pct"], 0.001)
            self.assertGreaterEqual(pt["drawdown_pct"], -100.0)

    def test_03_euro_losses_and_basel_scaling(self):
        """Verify Euro stress loss calculations and Basel 10-day square-root-of-10 scaling."""
        res = TailRiskService.analyze_portfolio_tail_risk(
            holdings=self.sample_holdings,
            total_portfolio_value=self.total_val,
            timeframe="1y"
        )
        el = res["euro_stress_losses"]
        vm = res["var_matrix"]

        # Basel 10-day scaling factor
        expected_10d_cvar_pct = vm["expected_shortfall_99_pct"] * math.sqrt(10.0)
        self.assertAlmostEqual(vm["cvar_10d_99_pct"], expected_10d_cvar_pct, places=1)

        # Euro amounts must match
        expected_cvar_1d_eur = (vm["expected_shortfall_99_pct"] / 100.0) * res["portfolio_value_eur"]
        self.assertAlmostEqual(el["cvar_1d_99_eur"], expected_cvar_1d_eur, places=1)

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/tail-risk and POST /api/portfolio/tail-risk/analyze."""
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
            create_res = client.post("/api/portfolio/create", json={"name": "Tail Risk QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/tail-risk
        tr_res = client.get(f"/api/portfolio/{p_id}/tail-risk?timeframe=1y", cookies=cookies)
        self.assertEqual(tr_res.status_code, 200)
        tr_json = tr_res.json()
        self.assertTrue(tr_json.get("valid"))
        self.assertIn("var_matrix", tr_json)
        self.assertIn("underwater_chart", tr_json)
        self.assertIn("drawdown", tr_json)

        # 3. POST /api/portfolio/tail-risk/analyze
        custom_res = client.post(
            "/api/portfolio/tail-risk/analyze",
            json={"tickers": ["AAPL", "MSFT"]},
            cookies=cookies
        )
        self.assertEqual(custom_res.status_code, 200)
        custom_json = custom_res.json()
        self.assertTrue(custom_json.get("valid"))


if __name__ == "__main__":
    unittest.main()
