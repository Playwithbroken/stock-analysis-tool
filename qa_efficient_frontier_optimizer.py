"""
Automated QA Test Suite for Feature 15:
Institutional Modern Portfolio Theory, Efficient Frontier & Black-Litterman Optimization Suite.
"""

import unittest
import os
import numpy as np
from fastapi.testclient import TestClient
from src.optimization_service import OptimizationService


class TestEfficientFrontierOptimizer(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 15, "current_price": 185.0},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "shares": 8, "current_price": 420.0},
            {"ticker": "GOOGL", "name": "Alphabet Inc.", "shares": 12, "current_price": 160.0},
            {"ticker": "JNJ", "name": "Johnson & Johnson", "shares": 10, "current_price": 155.0},
        ]

    def test_01_simplex_projection_and_qp(self):
        """Verify simplex projection mathematical correctness and QP solver stability."""
        # 1. Random vector projection
        v = np.array([0.8, -0.4, 1.2, -0.1])
        proj = OptimizationService.project_onto_simplex(v, s=1.0)
        self.assertAlmostEqual(float(np.sum(proj)), 1.0, places=5)
        self.assertTrue(bool(np.all(proj >= 0.0)))

        # 2. QP Solver
        cov = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.015],
            [0.02, 0.015, 0.06]
        ])
        q = np.zeros(3)
        w_opt = OptimizationService.solve_constrained_qp(cov, q)
        self.assertAlmostEqual(float(np.sum(w_opt)), 1.0, places=4)
        self.assertTrue(bool(np.all(w_opt >= -1e-7)))

    def test_02_efficient_frontier_mathematics(self):
        """Verify GMV, Max Sharpe, and Efficient Frontier curve properties."""
        res = OptimizationService.run_optimization(
            holdings=self.sample_holdings,
            timeframe="1y",
            risk_free_rate=0.035
        )

        self.assertTrue(res.get("valid"))
        gmv = res["min_volatility_portfolio"]
        msr = res["max_sharpe_portfolio"]
        eq = res["equal_weight_portfolio"]
        curr = res["current_portfolio"]

        # GMV volatility should be less than or equal to Equal Weight volatility
        self.assertLessEqual(gmv["volatility_pct"], eq["volatility_pct"] + 0.1)

        # Max Sharpe ratio should be >= GMV Sharpe ratio
        self.assertGreaterEqual(msr["sharpe_ratio"], gmv["sharpe_ratio"] - 0.05)

        # Efficient frontier points should exist
        frontier = res.get("efficient_frontier", [])
        self.assertGreater(len(frontier), 3)

        # Verify allocations table
        allocs = res.get("allocations", [])
        self.assertEqual(len(allocs), len(res["tickers"]))
        total_msr_w = sum(a["max_sharpe_weight_pct"] for a in allocs)
        self.assertAlmostEqual(total_msr_w, 100.0, delta=1.5)

    def test_03_black_litterman_tactical_views(self):
        """Verify that a strong bullish view tilts the portfolio weight toward that asset."""
        # Run neutral first
        res_neutral = OptimizationService.run_optimization(
            holdings=self.sample_holdings,
            views=[]
        )
        neutral_alloc = {a["ticker"]: a["black_litterman_weight_pct"] for a in res_neutral["allocations"]}

        # Add strongly bullish view on AAPL
        bullish_views = [
            {"ticker": "AAPL", "expected_excess_return_pct": 25.0, "confidence": 0.85}
        ]
        res_bullish = OptimizationService.run_optimization(
            holdings=self.sample_holdings,
            views=bullish_views
        )
        bullish_alloc = {a["ticker"]: a["black_litterman_weight_pct"] for a in res_bullish["allocations"]}

        # Bullish AAPL weight should be >= neutral AAPL weight
        self.assertGreaterEqual(bullish_alloc.get("AAPL", 0), neutral_alloc.get("AAPL", 0))

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/efficient-frontier and POST endpoints."""
        import api
        client = TestClient(api.app)

        # Authentication cookie
        pw = os.environ.get("APP_ACCESS_PASSWORD", "testpass123")
        login_res = client.post("/api/auth/login", json={"password": pw})
        session_cookie = login_res.cookies.get("session_id")
        cookies = {"session_id": session_cookie} if session_cookie else {}

        # Create or fetch portfolio
        pf_list_res = client.get("/api/portfolios", cookies=cookies)
        self.assertEqual(pf_list_res.status_code, 200)
        pfs = pf_list_res.json()
        if not pfs:
            create_res = client.post("/api/portfolio/create", json={"name": "MPT QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150}, cookies=cookies)
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "MSFT", "shares": 5, "buyPrice": 350}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            # Ensure at least 2 holdings
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 150}, cookies=cookies)
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "MSFT", "shares": 5, "buyPrice": 350}, cookies=cookies)

        # 1. GET /api/portfolio/{p_id}/efficient-frontier
        ef_res = client.get(f"/api/portfolio/{p_id}/efficient-frontier?timeframe=1y", cookies=cookies)
        self.assertEqual(ef_res.status_code, 200)
        ef_json = ef_res.json()
        self.assertTrue(ef_json.get("valid"))
        self.assertIn("efficient_frontier", ef_json)
        self.assertIn("max_sharpe_portfolio", ef_json)

        # 2. POST /api/portfolio/{p_id}/optimize/black-litterman
        bl_res = client.post(
            f"/api/portfolio/{p_id}/optimize/black-litterman",
            json={
                "timeframe": "1y",
                "risk_free_rate": 0.035,
                "views": [
                    {"ticker": "MSFT", "expected_excess_return_pct": 12.0, "confidence": 0.80}
                ]
            },
            cookies=cookies
        )
        self.assertEqual(bl_res.status_code, 200)
        bl_json = bl_res.json()
        self.assertTrue(bl_json.get("valid"))
        self.assertIn("black_litterman_portfolio", bl_json)

        # 3. POST /api/portfolio/optimize/custom
        custom_res = client.post(
            "/api/portfolio/optimize/custom",
            json={"tickers": ["AAPL", "GOOGL"]},
            cookies=cookies
        )
        self.assertEqual(custom_res.status_code, 200)
        custom_json = custom_res.json()
        self.assertTrue(custom_json.get("valid"))


if __name__ == "__main__":
    unittest.main()
