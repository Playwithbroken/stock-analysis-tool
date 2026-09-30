"""
Automated QA Test Suite for Feature 20:
Institutional Performance Attribution & Brinson-Fachler Decomposition Terminal
(Allocation Effect, Selection Effect, Interaction Effect & Active Share vs. Global Benchmarks).
"""

import unittest
import os
from fastapi.testclient import TestClient
from src.performance_attribution_service import PerformanceAttributionService


class TestBrinsonAttributionTerminal(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 50, "buyPrice": 150.0, "current_price": 220.0, "sector": "Information Technology"},
            {"ticker": "NVDA", "name": "Nvidia Corp.", "shares": 20, "buyPrice": 80.0, "current_price": 120.0, "sector": "Information Technology"},
            {"ticker": "JPM", "name": "JPMorgan Chase", "shares": 30, "buyPrice": 160.0, "current_price": 200.0, "sector": "Financials"},
            {"ticker": "LLY", "name": "Eli Lilly", "shares": 10, "buyPrice": 600.0, "current_price": 850.0, "sector": "Health Care"},
            {"ticker": "XOM", "name": "Exxon Mobil", "shares": 40, "buyPrice": 110.0, "current_price": 115.0, "sector": "Energy"},
        ]

    def test_01_brinson_fachler_mathematical_identity(self):
        """Verify the fundamental Brinson-Fachler invariant: Delta R = Allocation + Selection + Interaction."""
        for bench in ["msci_world", "sp500", "dax", "stoxx600"]:
            res = PerformanceAttributionService.calculate_brinson_attribution(
                self.sample_holdings,
                benchmark_key=bench
            )
            self.assertTrue(res["valid"])
            summary = res["summary"]

            active_ret = summary["active_return_pct"]
            alloc = summary["allocation_effect_pct"]
            select = summary["selection_effect_pct"]
            interact = summary["interaction_effect_pct"]

            # Mathematical invariant: sum of effects must equal active return
            sum_effects = alloc + select + interact
            self.assertAlmostEqual(active_ret, sum_effects, places=1)

    def test_02_active_share_and_sector_weights(self):
        """Verify Active Share bounds [0%, 100%] and sector weight normalization."""
        res = PerformanceAttributionService.calculate_brinson_attribution(
            self.sample_holdings,
            benchmark_key="msci_world"
        )
        summary = res["summary"]
        self.assertGreaterEqual(summary["active_share_pct"], 0.0)
        self.assertLessEqual(summary["active_share_pct"], 100.0)

        # Portfolio sector weights must sum to ~100%
        sectors = res["sectors"]
        port_weight_sum = sum(s["portfolio_weight_pct"] for s in sectors)
        bench_weight_sum = sum(s["benchmark_weight_pct"] for s in sectors)
        self.assertAlmostEqual(port_weight_sum, 100.0, places=1)
        self.assertAlmostEqual(bench_weight_sum, 100.0, places=1)

        # Total effect per sector equals sum of alloc + select + interact
        for s in sectors:
            expected_total = s["allocation_effect_pct"] + s["selection_effect_pct"] + s["interaction_effect_pct"]
            self.assertAlmostEqual(s["total_effect_pct"], expected_total, places=2)

    def test_03_stock_alpha_highlights(self):
        """Verify stock-level alpha contribution calculations."""
        res = PerformanceAttributionService.calculate_brinson_attribution(
            self.sample_holdings,
            benchmark_key="sp500"
        )
        highlights = res.get("stock_highlights", [])
        self.assertGreater(len(highlights), 0)
        for h in highlights:
            self.assertIn("ticker", h)
            self.assertIn("excess_alpha_pct", h)
            self.assertIn("alpha_contribution_pct", h)

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/attribution and POST /api/portfolio/attribution/analyze."""
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
            create_res = client.post("/api/portfolio/create", json={"name": "Brinson QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 150}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 150}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/attribution
        attr_res = client.get(f"/api/portfolio/{p_id}/attribution?benchmark=msci_world", cookies=cookies)
        self.assertEqual(attr_res.status_code, 200)
        attr_json = attr_res.json()
        self.assertTrue(attr_json.get("valid"))
        self.assertIn("summary", attr_json)
        self.assertIn("sectors", attr_json)
        self.assertIn("stock_highlights", attr_json)

        # 3. POST /api/portfolio/attribution/analyze
        custom_res = client.post(
            "/api/portfolio/attribution/analyze",
            json={"tickers": ["AAPL", "MSFT", "NVDA"], "benchmark": "sp500"},
            cookies=cookies
        )
        self.assertEqual(custom_res.status_code, 200)
        custom_json = custom_res.json()
        self.assertTrue(custom_json.get("valid"))
        self.assertEqual(custom_json["benchmark_key"], "sp500")


if __name__ == "__main__":
    unittest.main()
