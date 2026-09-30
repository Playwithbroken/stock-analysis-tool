"""
Automated QA Test Suite for Feature 19:
Institutional Multi-Currency FX Exposure & Currency Hedging Terminal
(FX Value-at-Risk, Covered Interest Parity Forward Cost, Minimum Variance Hedge Ratio).
"""

import unittest
import os
from fastapi.testclient import TestClient
from src.currency_hedging_service import CurrencyHedgingService


class TestCurrencyHedgingTerminal(unittest.TestCase):

    def setUp(self):
        self.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 50, "current_price": 200.0},     # 10,000 USD
            {"ticker": "SAP", "name": "SAP SE", "shares": 50, "current_price": 180.0},          # 9,000 EUR
            {"ticker": "NESN", "name": "Nestlé S.A.", "shares": 40, "current_price": 100.0},    # 4,000 CHF
            {"ticker": "SHEL", "name": "Shell PLC", "shares": 60, "current_price": 30.0},       # 1,800 GBP
        ]
        self.total_val = 24800.0

    def test_01_currency_detection_and_exposure_aggregation(self):
        """Verify accurate currency mapping, look-through categorization, and 100% weight sum."""
        self.assertEqual(CurrencyHedgingService.detect_currency("AAPL"), "USD")
        self.assertEqual(CurrencyHedgingService.detect_currency("NVDA"), "USD")
        self.assertEqual(CurrencyHedgingService.detect_currency("SAP"), "EUR")
        self.assertEqual(CurrencyHedgingService.detect_currency("NESN"), "CHF")
        self.assertEqual(CurrencyHedgingService.detect_currency("SHEL"), "GBP")

        res = CurrencyHedgingService.analyze_portfolio_currency_risk(self.sample_holdings, self.total_val)
        self.assertTrue(res["valid"])

        summary = res["summary"]
        self.assertAlmostEqual(summary["foreign_currency_pct"] + summary["home_currency_pct"], 100.0, places=1)
        self.assertGreater(summary["foreign_currency_pct"], 50.0)

        breakdown = res["currency_breakdown"]
        currencies = [b["currency"] for b in breakdown]
        self.assertIn("USD", currencies)
        self.assertIn("EUR", currencies)
        self.assertIn("CHF", currencies)
        self.assertIn("GBP", currencies)

        total_weight = sum(b["weight_pct"] for b in breakdown)
        self.assertAlmostEqual(total_weight, 100.0, places=1)

    def test_02_covered_interest_parity_and_forward_cost(self):
        """Verify Covered Interest Parity forward rates and negative/positive carry dynamics."""
        # 1. USD: higher rate than EUR -> positive forward cost (negative carry)
        usd_cip = CurrencyHedgingService.calculate_forward_cost("USD")
        self.assertGreater(usd_cip["forward_rate_1y"], usd_cip["spot_rate"])
        self.assertGreater(usd_cip["annual_hedging_cost_pct"], 0.0)
        self.assertIn("Negativer Carry", usd_cip["carry_status"])

        # 2. CHF: lower rate than EUR -> negative forward cost (positive carry for EUR investor)
        chf_cip = CurrencyHedgingService.calculate_forward_cost("CHF")
        self.assertLess(chf_cip["forward_rate_1y"], chf_cip["spot_rate"])
        self.assertLess(chf_cip["annual_hedging_cost_pct"], 0.0)
        self.assertIn("Positiver Carry", chf_cip["carry_status"])

        # 3. EUR: home currency -> neutral
        eur_cip = CurrencyHedgingService.calculate_forward_cost("EUR")
        self.assertEqual(eur_cip["annual_hedging_cost_pct"], 0.0)

    def test_03_fx_var_and_minimum_variance_hedge_ratio(self):
        """Verify parametric FX VaR monotonic bounds and Minimum Variance Hedge Ratio ranges."""
        res = CurrencyHedgingService.analyze_portfolio_currency_risk(self.sample_holdings, self.total_val)
        fx_var = res["fx_var"]

        # VaR 99% >= VaR 95%
        self.assertGreaterEqual(fx_var["var_99_1y_eur"], fx_var["var_95_1y_eur"])
        self.assertGreaterEqual(fx_var["var_99_1d_eur"], fx_var["var_95_1d_eur"])
        self.assertGreater(fx_var["var_95_1y_eur"], 0.0)

        # Minimum variance hedge ratio should be sensible for foreign currencies
        for b in res["currency_breakdown"]:
            if b["currency"] != "EUR":
                self.assertGreaterEqual(b["optimal_hedge_ratio_pct"], 20.0)
                self.assertLessEqual(b["optimal_hedge_ratio_pct"], 100.0)

        # Macro shock simulation
        shock_res = CurrencyHedgingService.simulate_fx_shock(
            self.sample_holdings,
            {"USD": -10.0, "EUR": 0.0}
        )
        self.assertLess(shock_res["total_delta_eur"], 0.0)
        self.assertAlmostEqual(shock_res["total_delta_eur"], -1000.0, places=1)

    def test_04_api_endpoints(self):
        """Verify GET /api/portfolio/{p_id}/currency-hedging and POST /api/portfolio/currency-hedging/simulate."""
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
            create_res = client.post("/api/portfolio/create", json={"name": "FX QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 180}, cookies=cookies)
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "SAP", "shares": 10, "buyPrice": 170}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 180}, cookies=cookies)

        # 2. GET /api/portfolio/{p_id}/currency-hedging
        fx_res = client.get(f"/api/portfolio/{p_id}/currency-hedging", cookies=cookies)
        self.assertEqual(fx_res.status_code, 200)
        fx_json = fx_res.json()
        self.assertTrue(fx_json.get("valid"))
        self.assertIn("summary", fx_json)
        self.assertIn("fx_var", fx_json)
        self.assertIn("currency_breakdown", fx_json)
        self.assertIn("macro_scenarios", fx_json)

        # 3. POST /api/portfolio/currency-hedging/simulate
        sim_res = client.post(
            "/api/portfolio/currency-hedging/simulate",
            json={
                "portfolio_id": p_id,
                "fx_shocks": {"USD": 5.0, "EUR": 0.0}
            },
            cookies=cookies
        )
        self.assertEqual(sim_res.status_code, 200)
        sim_json = sim_res.json()
        self.assertIn("total_delta_eur", sim_json)
        self.assertIn("simulated_portfolio_value_eur", sim_json)


if __name__ == "__main__":
    unittest.main()
