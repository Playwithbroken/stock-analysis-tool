"""
Automated QA Test Suite for Feature 18:
Institutional Liquidity Risk & Market Impact Simulator (Almgren-Chriss, Days-to-Liquidate, SEC Rule 22e-4).
"""

import unittest
import os
from fastapi.testclient import TestClient
from src.liquidity_service import LiquidityService


class TestLiquidityRiskSimulator(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 500, "current_price": 180.0},
            {"ticker": "MSFT", "name": "Microsoft Corp.", "shares": 300, "current_price": 400.0},
            {"ticker": "SMALLCAP", "name": "Small Micro Ticker", "shares": 10000, "current_price": 15.0},
        ]

    def test_01_almgren_chriss_slippage_and_dtl(self):
        """Verify mathematical properties of Almgren-Chriss slippage and Days-to-Liquidate."""
        profile = LiquidityService.get_stock_liquidity_profile("AAPL", 180.0)
        adv = profile["adv_shares"]
        vol = profile["daily_volatility"]
        spread = profile["bid_ask_spread_pct"]

        # 1. Slippage increases with order size
        slip_small = LiquidityService.calculate_almgren_chriss_slippage(100, adv, vol, spread, execution_days=1.0)
        slip_large = LiquidityService.calculate_almgren_chriss_slippage(500_000, adv, vol, spread, execution_days=1.0)

        self.assertGreater(slip_large["total_slippage_pct"], slip_small["total_slippage_pct"])

        # 2. Fire sale (1 day) induces larger slippage than patient execution (5 days)
        slip_fire = LiquidityService.calculate_almgren_chriss_slippage(200_000, adv, vol, spread, execution_days=1.0)
        slip_normal = LiquidityService.calculate_almgren_chriss_slippage(200_000, adv, vol, spread, execution_days=5.0)
        self.assertGreater(slip_fire["total_slippage_pct"], slip_normal["total_slippage_pct"])

        # 3. Days to Liquidate scales inversely with participation rate
        p10 = LiquidityService.analyze_portfolio_liquidity(self.sample_holdings, participation_rate=0.10)
        p20 = LiquidityService.analyze_portfolio_liquidity(self.sample_holdings, participation_rate=0.20)
        self.assertTrue(p10["valid"])
        self.assertTrue(p20["valid"])
        self.assertGreaterEqual(p10["portfolio_days_to_liquidate"], p20["portfolio_days_to_liquidate"])

    def test_02_sec_22e4_liquidity_tiers_and_health_score(self):
        """Verify SEC 22e-4 tier partition, sums to 100%, and Health Score bounds."""
        res = LiquidityService.analyze_portfolio_liquidity(self.sample_holdings, participation_rate=0.10)
        self.assertTrue(res["valid"])
        
        self.assertGreaterEqual(res["liquidity_health_score"], 0.0)
        self.assertLessEqual(res["liquidity_health_score"], 100.0)

        tiers = res["tier_distribution"]
        total_pct = (
            tiers["tier_1_pct"] +
            tiers["tier_2_pct"] +
            tiers["tier_3_pct"] +
            tiers["tier_4_pct"]
        )
        self.assertAlmostEqual(total_pct, 100.0, places=1)

        # Holdings items
        items = res.get("holdings", [])
        self.assertEqual(len(items), len(self.sample_holdings))
        for item in items:
            self.assertIn("days_to_liquidate", item)
            self.assertIn("normal_slippage_pct", item)
            self.assertIn("fire_sale_slippage_pct", item)
            self.assertIn("recommended_strategy", item)
            self.assertIn("tier", item)

    def test_03_order_impact_simulation(self):
        """Verify single order impact simulation engine."""
        sim = LiquidityService.simulate_order_impact(
            ticker="MSFT",
            order_value_eur=50000,
            current_price=400.0
        )
        self.assertEqual(sim["ticker"], "MSFT")
        self.assertGreater(sim["total_slippage_eur"], 0.0)
        self.assertGreater(sim["total_slippage_pct"], 0.0)
        self.assertIn("order_pct_of_adv", sim)

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/liquidity, GET /api/stock/{ticker}/liquidity, and POST /api/portfolio/liquidity/simulate."""
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
            create_res = client.post("/api/portfolio/create", json={"name": "Liquidity QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 50, "buyPrice": 150}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 50, "buyPrice": 150}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/liquidity
        liq_res = client.get(f"/api/portfolio/{p_id}/liquidity?participation_rate=0.10", cookies=cookies)
        self.assertEqual(liq_res.status_code, 200)
        liq_json = liq_res.json()
        self.assertTrue(liq_json.get("valid"))
        self.assertIn("liquidity_health_score", liq_json)
        self.assertIn("tier_distribution", liq_json)
        self.assertIn("execution_costs", liq_json)
        self.assertIn("holdings", liq_json)

        # 3. GET /api/stock/AAPL/liquidity
        stock_res = client.get("/api/stock/AAPL/liquidity", cookies=cookies)
        self.assertEqual(stock_res.status_code, 200)
        stock_json = stock_res.json()
        self.assertEqual(stock_json["ticker"], "AAPL")
        self.assertGreater(stock_json["adv_shares"], 0)

        # 4. POST /api/portfolio/liquidity/simulate
        sim_res = client.post(
            "/api/portfolio/liquidity/simulate",
            json={"ticker": "AAPL", "order_value_eur": 25000, "current_price": 180.0},
            cookies=cookies
        )
        self.assertEqual(sim_res.status_code, 200)
        sim_json = sim_res.json()
        self.assertEqual(sim_json["ticker"], "AAPL")
        self.assertGreater(sim_json["total_slippage_eur"], 0.0)


if __name__ == "__main__":
    unittest.main()
