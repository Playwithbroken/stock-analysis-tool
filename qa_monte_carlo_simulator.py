"""
QA Test Suite for Monte Carlo Portfolio Wealth Simulator & FIRE/Retirement Engine
"""

import unittest
from src.monte_carlo_service import MonteCarloSimulator


class TestMonteCarloSimulator(unittest.TestCase):

    def test_basic_convergence_and_monotonicity(self):
        """Test that percentiles strictly obey p10 <= p25 <= p50 <= p75 <= p90."""
        result = MonteCarloSimulator.simulate(
            initial_wealth=50000.0,
            annual_return=0.08,
            annual_volatility=0.15,
            monthly_savings=500.0,
            monthly_withdrawal=0.0,
            horizon_years=10,
            inflation_rate=0.02,
            target_wealth=200000.0,
            num_simulations=1000,
            seed=42
        )

        summary = result["summary"]
        self.assertLessEqual(summary["p10_final_wealth"], summary["p25_final_wealth"])
        self.assertLessEqual(summary["p25_final_wealth"], summary["median_final_wealth"])
        self.assertLessEqual(summary["median_final_wealth"], summary["p75_final_wealth"])
        self.assertLessEqual(summary["p75_final_wealth"], summary["p90_final_wealth"])

        # Check trajectory length
        trajectories = result["annual_trajectories"]
        self.assertEqual(len(trajectories), 11)  # Year 0 to Year 10
        self.assertEqual(trajectories[0]["year"], 0)
        self.assertEqual(trajectories[10]["year"], 10)

        # In accumulation mode with 0 withdrawals, ruin probability should be 0
        self.assertEqual(summary["ruin_probability"], 0.0)
        self.assertEqual(summary["survival_probability"], 100.0)

    def test_retirement_withdrawal_and_ruin(self):
        """Test that excessive withdrawals lead to measurable ruin probability."""
        result = MonteCarloSimulator.simulate(
            initial_wealth=100000.0,
            annual_return=0.04,
            annual_volatility=0.20,
            monthly_savings=0.0,
            monthly_withdrawal=3000.0,  # 36k/yr on 100k capital -> high ruin risk
            horizon_years=10,
            inflation_rate=0.02,
            target_wealth=200000.0,
            num_simulations=1000,
            seed=42
        )

        summary = result["summary"]
        self.assertGreater(summary["ruin_probability"], 50.0)
        self.assertLess(summary["survival_probability"], 50.0)

    def test_inflation_discounting(self):
        """Verify that real purchasing power is strictly less than nominal when inflation > 0."""
        result = MonteCarloSimulator.simulate(
            initial_wealth=100000.0,
            annual_return=0.07,
            annual_volatility=0.12,
            monthly_savings=200.0,
            monthly_withdrawal=0.0,
            horizon_years=15,
            inflation_rate=0.025,
            target_wealth=500000.0,
            num_simulations=500,
            seed=123
        )

        summary = result["summary"]
        self.assertLess(summary["real_median_final_wealth"], summary["median_final_wealth"])

    def test_infer_portfolio_profile(self):
        """Verify inference of expected return and volatility from holdings."""
        sample_holdings = [
            {"name": "Apple Inc.", "asset_type": "stock", "shares": 50, "current_price": 200, "score": 85},
            {"name": "MSCI World ETF", "asset_type": "etf", "shares": 100, "current_price": 90, "score": 70},
            {"name": "Treasury Bond ETF", "asset_type": "bond", "shares": 50, "current_price": 100, "score": 60}
        ]
        profile = MonteCarloSimulator.infer_portfolio_profile(sample_holdings)
        self.assertGreater(profile["total_value"], 0)
        self.assertGreater(profile["expected_return"], 0.03)
        self.assertLess(profile["expected_return"], 0.15)
        self.assertGreater(profile["volatility"], 0.05)
        self.assertLess(profile["volatility"], 0.35)

    def test_api_endpoints(self):
        """Verify standalone and portfolio Monte Carlo API endpoints."""
        import os
        from fastapi.testclient import TestClient
        import api

        client = TestClient(api.app)

        pw = os.environ.get("APP_ACCESS_PASSWORD", "test-pass")
        # Ensure login
        client.post("/api/auth/login", json={"password": pw})

        # 1. Standalone GET
        resp_get = client.get("/api/monte-carlo/simulate?initial_wealth=50000&horizon_years=10&monthly_savings=500")
        self.assertEqual(resp_get.status_code, 200)
        data_get = resp_get.json()
        self.assertIn("summary", data_get)
        self.assertIn("annual_trajectories", data_get)
        self.assertEqual(len(data_get["annual_trajectories"]), 11)

        # 2. Standalone POST
        resp_post = client.post("/api/monte-carlo/simulate?initial_wealth=80000&horizon_years=15")
        self.assertEqual(resp_post.status_code, 200)

        # 3. Portfolio endpoint
        pm = api.get_portfolio_manager()
        portfolios = pm.get_portfolios()
        if portfolios:
            p_id = portfolios[0]["id"]
            resp_port = client.post(f"/api/portfolio/{p_id}/monte-carlo", json={
                "horizon_years": 15,
                "monthly_savings": 600.0,
                "target_wealth": 1500000.0
            })
            self.assertEqual(resp_port.status_code, 200)
            data_port = resp_port.json()
            self.assertIn("inferred_profile", data_port)
            self.assertIn("summary", data_port)


if __name__ == "__main__":
    unittest.main()
