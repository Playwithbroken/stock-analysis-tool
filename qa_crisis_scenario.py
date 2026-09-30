import unittest
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.crisis_scenario_service import CrisisScenarioService


class TestCrisisScenarioService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 50, "current_price": 200.0, "beta": 1.15},
            {"ticker": "MSFT", "name": "Microsoft Corp", "shares": 30, "current_price": 400.0, "beta": 1.05},
            {"ticker": "XOM", "name": "Exxon Mobil Corp", "shares": 40, "current_price": 110.0, "beta": 0.85},
            {"ticker": "JNJ", "name": "Johnson & Johnson", "shares": 50, "current_price": 160.0, "beta": 0.55},
            {"ticker": "GLD", "name": "SPDR Gold Trust", "shares": 30, "current_price": 220.0, "beta": 0.10},
        ]
        cls.total_value = sum(h["shares"] * h["current_price"] for h in cls.sample_holdings)

    def test_crisis_scenarios_completeness_and_math(self):
        """Verifies that all 7 historical crisis scenarios are calculated and have mathematically consistent trajectories."""
        res = CrisisScenarioService.analyze_portfolio(self.sample_holdings, self.total_value)

        self.assertIn("scenarios", res)
        scenarios = res["scenarios"]
        self.assertEqual(len(scenarios), 7)

        expected_ids = [
            "black_monday_1987",
            "dotcom_bust_2000",
            "gfc_lehman_2008",
            "euro_debt_2011",
            "covid_crash_2020",
            "stagflation_2022",
            "geopolitical_energy_shock",
        ]
        for cid in expected_ids:
            self.assertIn(cid, scenarios)
            sc = scenarios[cid]
            self.assertLess(sc["benchmark_drawdown"], 0.0, "Benchmark drawdown must be negative")
            self.assertLess(sc["portfolio_drawdown_pct"], 0.0, "Portfolio drawdown must be negative for equity heavy portfolio")
            self.assertGreater(sc["recovery_months"], 0)

            # Check trajectory
            traj = sc["trajectory"]
            self.assertGreaterEqual(len(traj), 4)
            self.assertEqual(traj[0]["portfolio_pct"], 0.0, "Initial trajectory point must be 0%")
            # Trough is negative
            min_pt = min(pt["portfolio_pct"] for pt in traj)
            self.assertLess(min_pt, -5.0)

        # Resilience score between 5 and 95
        self.assertGreaterEqual(res["resilience_score"], 5.0)
        self.assertLessEqual(res["resilience_score"], 95.0)
        self.assertIn("resilience_rating", res)
        self.assertIn("playbook", res)
        self.assertGreaterEqual(len(res["playbook"]), 3)

    def test_asset_class_and_sector_detection(self):
        """Verifies correct sector mapping and safe haven recognition."""
        tech_sector = CrisisScenarioService.detect_sector("AAPL", "Apple Inc.")
        self.assertEqual(tech_sector, "technology")

        energy_sector = CrisisScenarioService.detect_sector("XOM", "Exxon Mobil")
        self.assertEqual(energy_sector, "energy")

        gold_class = CrisisScenarioService.detect_asset_class("GLD", "SPDR Gold Shares")
        self.assertEqual(gold_class, "gold")

        bond_class = CrisisScenarioService.detect_asset_class("BND", "Vanguard Total Bond Market")
        self.assertEqual(bond_class, "fixed_income")

    def test_custom_macro_shock_simulation(self):
        """Verifies custom dynamic macro shock simulator."""
        sim = CrisisScenarioService.simulate_custom_shock(
            holdings=self.sample_holdings,
            total_value=self.total_value,
            equity_shock_pct=-25.0,
            rate_shock_bps=150.0,
            oil_shock_pct=50.0,
            credit_spread_bps=200.0,
            usd_shock_pct=10.0,
        )

        self.assertIn("total_loss_eur", sim)
        self.assertIn("total_loss_pct", sim)
        self.assertLess(sim["total_loss_pct"], 0.0)
        self.assertEqual(sim["resulting_value"], round(self.total_value + sim["total_loss_eur"], 2))
        self.assertEqual(len(sim["holdings"]), len(self.sample_holdings))

    def test_api_endpoints_integration(self):
        """Tests API endpoints GET /api/portfolio/{p_id}/crisis-scenarios and POST /api/portfolio/crisis-scenarios/simulate."""
        try:
            from fastapi.testclient import TestClient
            from api import app
        except ImportError:
            self.skipTest("FastAPI TestClient not available")

        client = TestClient(app)

        pw = os.environ.get("APP_ACCESS_PASSWORD", "testpass123")
        login_res = client.post("/api/auth/login", json={"password": pw})
        session_cookie = login_res.cookies.get("session_id")
        cookies = {"session_id": session_cookie} if session_cookie else {}

        # 2. Get portfolios
        p_res = client.get("/api/portfolios", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        pfs = p_res.json()
        if not pfs:
            create_res = client.post("/api/portfolio/create", json={"name": "Crisis QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 20, "buyPrice": 150}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]

        # Test GET /api/portfolio/{p_id}/crisis-scenarios
        get_res = client.get(f"/api/portfolio/{p_id}/crisis-scenarios", cookies=cookies)
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertIn("scenarios", data)
        self.assertIn("resilience_score", data)

        # 3. Test POST /api/portfolio/crisis-scenarios/simulate
        sim_payload = {
            "tickers": ["AAPL", "MSFT", "GLD"],
            "equity_shock_pct": -20.0,
            "rate_shock_bps": 100.0,
            "oil_shock_pct": 30.0,
            "credit_spread_bps": 150.0,
            "usd_shock_pct": 5.0,
        }
        post_res = client.post("/api/portfolio/crisis-scenarios/simulate", json=sim_payload, cookies=cookies)
        self.assertEqual(post_res.status_code, 200)
        sim_data = post_res.json()
        self.assertIn("total_loss_eur", sim_data)
        self.assertIn("total_loss_pct", sim_data)
        self.assertLess(sim_data["total_loss_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
