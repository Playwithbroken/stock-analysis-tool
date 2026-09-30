"""
Automated QA Test Suite for Feature 22:
Institutional Risk-Adjusted Performance & Ratio Analytics Terminal
(Sharpe, Sortino, Calmar, Treynor, Omega, Information Ratio & Pain Index).
"""

import unittest
import os
from fastapi.testclient import TestClient
from src.ratio_analytics_service import RatioAnalyticsService


class TestRiskRatiosTerminal(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 50, "buyPrice": 160.0, "current_price": 220.0},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "shares": 30, "buyPrice": 320.0, "current_price": 420.0},
            {"ticker": "NVDA", "name": "Nvidia Corp.", "shares": 25, "buyPrice": 90.0, "current_price": 125.0},
            {"ticker": "SAP", "name": "SAP SE", "shares": 40, "buyPrice": 140.0, "current_price": 190.0},
        ]
        self.total_val = 31350.0

    def test_01_sortino_sharpe_calmar_mathematics(self):
        """Verify mathematical consistency: Sortino >= Sharpe for positively skewed returns, and Calmar bounds."""
        res = RatioAnalyticsService.calculate_ratios(
            annual_return_pct=22.50,
            annual_volatility_pct=16.00,
            max_drawdown_pct=-12.50,
            downside_deviation_pct=10.20,
            beta_vs_market=1.05,
            benchmark_key="msci_world"
        )
        port = res["portfolio"]

        # 1. Downside deviation < total volatility -> Sortino > Sharpe
        self.assertGreater(port["sortino_ratio"], port["sharpe_ratio"])

        # 2. Calmar ratio = 22.50 / 12.50 = 1.80
        expected_calmar = 22.50 / 12.50
        self.assertAlmostEqual(port["calmar_ratio"], expected_calmar, places=1)

        # 3. Treynor ratio = (22.50 - 3.25) / 1.05 = 18.33
        expected_treynor = (22.50 - 3.25) / 1.05
        self.assertAlmostEqual(port["treynor_ratio"], expected_treynor, places=1)

    def test_02_omega_ratio_and_pain_index(self):
        """Verify Omega ratio > 1.0 for outperforming assets and non-negative Pain Index."""
        res = RatioAnalyticsService.calculate_ratios(
            annual_return_pct=25.00,
            annual_volatility_pct=18.00,
            max_drawdown_pct=-14.00,
            benchmark_key="sp500"
        )
        port = res["portfolio"]

        # Omega ratio must be > 1.0 when return exceeds risk-free rate
        self.assertGreater(port["omega_ratio"], 1.0)
        self.assertGreater(port["pain_index"], 0.0)
        self.assertGreater(port["pain_ratio"], 0.0)

    def test_03_benchmark_comparison_and_information_ratio(self):
        """Verify multi-benchmark comparison and Information Ratio."""
        for bench in ["msci_world", "sp500", "dax"]:
            res = RatioAnalyticsService.analyze_portfolio_risk_ratios(
                self.sample_holdings,
                total_portfolio_value=self.total_val,
                benchmark_key=bench
            )
            self.assertTrue(res["valid"])
            ratios = res["ratios"]
            self.assertIn("sharpe_ratio", ratios)
            self.assertIn("sortino_ratio", ratios)
            self.assertIn("information_ratio", ratios)
            self.assertIn("rating_badge", ratios)

            holdings = res.get("holdings", [])
            self.assertEqual(len(holdings), len(self.sample_holdings))
            for h in holdings:
                self.assertIn("sortino_ratio", h)
                self.assertIn("sharpe_ratio", h)
                self.assertIn("calmar_ratio", h)

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/risk-ratios and POST /api/portfolio/risk-ratios/analyze."""
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
            create_res = client.post("/api/portfolio/create", json={"name": "Risk Ratios QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 150}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 150}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/risk-ratios
        rr_res = client.get(f"/api/portfolio/{p_id}/risk-ratios?benchmark=msci_world", cookies=cookies)
        self.assertEqual(rr_res.status_code, 200)
        rr_json = rr_res.json()
        self.assertTrue(rr_json.get("valid"))
        self.assertIn("ratios", rr_json)
        self.assertIn("benchmark", rr_json)
        self.assertIn("holdings", rr_json)

        # 3. POST /api/portfolio/risk-ratios/analyze
        custom_res = client.post(
            "/api/portfolio/risk-ratios/analyze",
            json={"tickers": ["AAPL", "MSFT"], "benchmark": "sp500"},
            cookies=cookies
        )
        self.assertEqual(custom_res.status_code, 200)
        custom_json = custom_res.json()
        self.assertTrue(custom_json.get("valid"))
        self.assertEqual(custom_json["benchmark_key"], "sp500")


if __name__ == "__main__":
    unittest.main()
