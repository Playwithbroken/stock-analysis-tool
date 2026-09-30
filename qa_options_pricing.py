"""
QA Test Suite for Feature 11: Options & Stillhalter-Strategie Scanner
Tests Black-Scholes-Merton engine, Put-Call Parity, Greeks (Delta, Theta),
Covered Call & Cash-Secured Put strategy generation, and API endpoints.
"""

import os
import math
import unittest
from starlette.testclient import TestClient

from src.options_service import BlackScholesEngine, OptionsService
from api import app


class TestOptionsService(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        pw = os.environ.get("APP_ACCESS_PASSWORD")
        if pw:
            self.client.post("/api/auth/login", json={"password": pw})

    def test_01_black_scholes_math_and_put_call_parity(self):
        """Verify Black-Scholes pricing and Put-Call parity."""
        S = 100.0
        K = 100.0
        T = 0.25  # 3 months
        r = 0.04  # 4%
        sigma = 0.20  # 20% vol

        call = BlackScholesEngine.call_price(S, K, T, r, sigma)
        put = BlackScholesEngine.put_price(S, K, T, r, sigma)

        # 1. Prices must be positive
        self.assertGreater(call, 0.0)
        self.assertGreater(put, 0.0)

        # 2. Put-Call Parity: C - P = S - K * exp(-r*T)
        pv_k = K * math.exp(-r * T)
        parity_lhs = call - put
        parity_rhs = S - pv_k
        self.assertAlmostEqual(parity_lhs, parity_rhs, places=1)

        # 3. Greeks
        call_delta = BlackScholesEngine.call_delta(S, K, T, r, sigma)
        put_delta = BlackScholesEngine.put_delta(S, K, T, r, sigma)

        # For ATM call, delta ~ 0.50 - 0.55
        self.assertGreater(call_delta, 0.45)
        self.assertLess(call_delta, 0.65)

        # Delta relationship: Call Delta - Put Delta = 1.0
        self.assertAlmostEqual(call_delta - put_delta, 1.0, places=2)

        # Theta is negative (option decay)
        call_theta = BlackScholesEngine.theta(S, K, T, r, sigma, is_call=True)
        self.assertLess(call_theta, 0.0)

        print("[OK] Test 1: Black-Scholes Math & Put-Call Parity Verified")

    def test_02_stock_options_suite_scenarios(self):
        """Verify 3 Covered Call and 3 Cash-Secured Put scenarios."""
        res = OptionsService.get_stock_options_suite(
            ticker="AAPL",
            current_price=200.0,
            shares=200,
            dte=30
        )

        self.assertEqual(res["ticker"], "AAPL")
        self.assertEqual(res["contracts_count"], 2)

        # 1. Check Covered Calls
        ccs = res["covered_calls"]
        self.assertEqual(len(ccs), 3)
        scenarios = [c["scenario"] for c in ccs]
        self.assertEqual(scenarios, ["Konservativ", "Ausgewogen", "Aggressiv"])

        # OTM hierarchy: Konservativ strike > Ausgewogen strike > Aggressiv strike
        self.assertGreater(ccs[0]["strike"], ccs[1]["strike"])
        self.assertGreater(ccs[1]["strike"], ccs[2]["strike"])

        # Yield hierarchy: Aggressiv yield > Ausgewogen yield > Konservativ yield
        self.assertGreater(ccs[2]["annualized_yield_pct"], ccs[1]["annualized_yield_pct"])
        self.assertGreater(ccs[1]["annualized_yield_pct"], ccs[0]["annualized_yield_pct"])

        # POP hierarchy: Konservativ POP > Ausgewogen POP > Aggressiv POP
        self.assertGreater(ccs[0]["pop_pct"], ccs[1]["pop_pct"])
        self.assertGreater(ccs[1]["pop_pct"], ccs[2]["pop_pct"])

        # 2. Check Cash-Secured Puts
        csps = res["cash_secured_puts"]
        self.assertEqual(len(csps), 3)
        for csp in csps:
            self.assertLess(csp["strike"], 200.0)
            self.assertLess(csp["net_entry_price"], csp["strike"])
            self.assertGreater(csp["return_on_capital_pct"], 0.0)

        print("[OK] Test 2: Stock Options Scenarios & Greeks Hierarchy Verified")

    def test_03_portfolio_options_income_scanner(self):
        """Verify portfolio-wide covered call scanning and contract scaling."""
        holdings = [
            {"ticker": "AAPL", "shares": 150, "buyPrice": 180.0, "currentPrice": 200.0},  # 1 full lot
            {"ticker": "MSFT", "shares": 200, "buyPrice": 380.0, "currentPrice": 400.0},  # 2 full lots
            {"ticker": "NVDA", "shares": 50, "buyPrice": 100.0, "currentPrice": 120.0},   # 0 full lots
        ]

        res = OptionsService.analyze_portfolio_options(holdings=holdings, dte=30)
        self.assertEqual(res["full_lots_count"], 2)
        self.assertEqual(len(res["positions"]), 3)
        self.assertGreater(res["total_monthly_cashflow_eur"], 0.0)
        self.assertGreater(res["total_annual_cashflow_eur"], 0.0)

        # Full lot positions must have contracts > 0
        aapl_pos = next(p for p in res["positions"] if p["ticker"] == "AAPL")
        self.assertTrue(aapl_pos["is_full_lot"])
        self.assertEqual(aapl_pos["contracts"], 1)

        msft_pos = next(p for p in res["positions"] if p["ticker"] == "MSFT")
        self.assertTrue(msft_pos["is_full_lot"])
        self.assertEqual(msft_pos["contracts"], 2)

        nvda_pos = next(p for p in res["positions"] if p["ticker"] == "NVDA")
        self.assertFalse(nvda_pos["is_full_lot"])
        self.assertEqual(nvda_pos["contracts"], 0)

        print("[OK] Test 3: Portfolio Income Scanner & Lot Logic Verified")

    def test_04_api_endpoints(self):
        """Verify GET /api/options/{ticker}, POST, and GET /api/portfolio/{p_id}/options-income."""
        # 1. Single stock GET
        resp_get = self.client.get("/api/options/AAPL?dte=45&shares=100")
        self.assertEqual(resp_get.status_code, 200)
        data_get = resp_get.json()
        self.assertEqual(data_get["ticker"], "AAPL")
        self.assertEqual(data_get["dte"], 45)
        self.assertEqual(len(data_get["covered_calls"]), 3)

        # 2. Single stock POST
        resp_post = self.client.post("/api/options/MSFT", json={"dte": 60, "shares": 200})
        self.assertEqual(resp_post.status_code, 200)
        data_post = resp_post.json()
        self.assertEqual(data_post["ticker"], "MSFT")
        self.assertEqual(data_post["dte"], 60)

        # 3. Portfolio Income GET
        port = self.client.post("/api/portfolios", json={"name": "Options QA Portfolio"}).json()
        p_id = port["id"]
        try:
            self.client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 100, "buyPrice": 180.0})
            resp_p = self.client.get(f"/api/portfolio/{p_id}/options-income")
            self.assertEqual(resp_p.status_code, 200)
            data_p = resp_p.json()
            self.assertEqual(data_p["portfolio_id"], p_id)
            self.assertEqual(data_p["full_lots_count"], 1)
            self.assertGreater(data_p["total_monthly_cashflow_eur"], 0.0)

            # 404 test
            resp_404 = self.client.get("/api/portfolio/invalid-999999/options-income")
            self.assertEqual(resp_404.status_code, 404)

            print("[OK] Test 4: All Options API Endpoints Verified")
        finally:
            self.client.delete(f"/api/portfolios/{p_id}")


if __name__ == "__main__":
    unittest.main()
