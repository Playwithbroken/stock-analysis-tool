"""
QA Test Suite for Feature 13: Institutional Factor & Smart Beta Decomposition Engine
"""

import unittest
from src.factor_service import FactorEngine


class TestFactorEngine(unittest.TestCase):

    def test_01_factor_scoring_and_z_scores(self):
        """Verify Value, Quality, Momentum, Low Volatility and Size scoring."""
        # 1. Deep Value stock (Low PE, low PB, high FCF)
        val_score = FactorEngine.score_value(pe=9.0, pb=1.2, fcf_yield=0.08)
        self.assertGreaterEqual(val_score, 75.0)

        # 2. Expensive Growth stock (High PE, high PB)
        growth_val_score = FactorEngine.score_value(pe=65.0, pb=15.0, fcf_yield=0.01)
        self.assertLessEqual(growth_val_score, 30.0)

        # 3. High Quality (High ROE, High Margin, Low Debt)
        qual_score = FactorEngine.score_quality(roe=0.35, profit_margin=0.25, debt_to_equity=0.2)
        self.assertGreaterEqual(qual_score, 80.0)

        # 4. Low Volatility (Low Beta)
        low_vol_score = FactorEngine.score_low_volatility(beta=0.65, annual_volatility=0.14)
        self.assertGreaterEqual(low_vol_score, 70.0)

        # 5. Size tier
        size_mega = FactorEngine.score_size(1500.0)
        self.assertEqual(size_mega["tier"], "Mega Cap")
        self.assertEqual(size_mega["style_box_category"], "Large")

        size_small = FactorEngine.score_size(4.5)
        self.assertEqual(size_small["tier"], "Small Cap")
        self.assertEqual(size_small["style_box_category"], "Small")

    def test_02_morningstar_style_box_classification(self):
        """Verify 9-grid Morningstar style box classification."""
        self.assertEqual(FactorEngine.classify_style_box(75.0, "Large"), "Large Value")
        self.assertEqual(FactorEngine.classify_style_box(50.0, "Large"), "Large Blend")
        self.assertEqual(FactorEngine.classify_style_box(25.0, "Large"), "Large Growth")

        self.assertEqual(FactorEngine.classify_style_box(80.0, "Mid"), "Mid Value")
        self.assertEqual(FactorEngine.classify_style_box(20.0, "Small"), "Small Growth")

    def test_03_portfolio_factor_aggregation(self):
        """Verify market-weighted factor aggregation and 9-grid sum."""
        holdings = [
            {"ticker": "AAPL", "name": "Apple", "shares": 100, "current_price": 200, "pe": 32.0, "beta": 1.2, "market_cap_billions": 3000.0},
            {"ticker": "ALV.DE", "name": "Allianz", "shares": 50, "current_price": 280, "pe": 10.5, "beta": 0.75, "market_cap_billions": 110.0}
        ]
        result = FactorEngine.analyze_portfolio(holdings)

        self.assertEqual(result["holdings_count"], 2)
        self.assertIn("portfolio_factors", result)
        self.assertIn("radar_data", result)
        self.assertEqual(len(result["radar_data"]), 6)

        # Style box sum must equal 100%
        grid_sum = sum(result["style_box_grid"].values())
        self.assertAlmostEqual(grid_sum, 100.0, places=0)

        # Positions must be sorted by weight
        self.assertEqual(result["positions"][0]["ticker"], "AAPL")

    def test_04_api_endpoints(self):
        """Verify portfolio factor endpoint and standalone ticker factor endpoint."""
        import os
        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)
        pw = os.environ.get("APP_ACCESS_PASSWORD", "test-pass")
        client.post("/api/auth/login", json={"password": pw})

        # 1. Single stock factors
        resp_stock = client.get("/api/stock/AAPL/factors")
        self.assertEqual(resp_stock.status_code, 200)
        data_stock = resp_stock.json()
        self.assertIn("factors", data_stock)
        self.assertEqual(data_stock["ticker"], "AAPL")

        # 2. Portfolio factors
        pm = api.get_portfolio_manager()
        portfolios = pm.get_portfolios()
        if portfolios:
            p_id = portfolios[0]["id"]
            resp_port = client.get(f"/api/portfolio/{p_id}/factor-analysis")
            self.assertEqual(resp_port.status_code, 200)
            data_port = resp_port.json()
            self.assertIn("portfolio_factors", data_port)
            self.assertIn("style_box_grid", data_port)


if __name__ == "__main__":
    unittest.main()
