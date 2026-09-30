import unittest
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.institutional_reporting_service import InstitutionalReportingService


class TestInstitutionalReportingService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Sample portfolio with 8 holdings
        cls.sample_portfolio = {
            "id": "PORT-INST-001",
            "name": "Global Wealth Preservation & Alpha Mandate",
            "currency": "EUR",
            "holdings": [
                {"ticker": "AAPL", "name": "Apple Inc.", "shares": 100, "current_price": 220.0, "buy_price": 180.0, "asset_type": "equity"},
                {"ticker": "MSFT", "name": "Microsoft Corp", "shares": 50, "current_price": 420.0, "buy_price": 380.0, "asset_type": "equity"},
                {"ticker": "NVDA", "name": "NVIDIA Corp", "shares": 80, "current_price": 120.0, "buy_price": 95.0, "asset_type": "equity"},
                {"ticker": "JNJ", "name": "Johnson & Johnson", "shares": 60, "current_price": 160.0, "buy_price": 150.0, "asset_type": "equity"},
                {"ticker": "XOM", "name": "Exxon Mobil", "shares": 50, "current_price": 115.0, "buy_price": 105.0, "asset_type": "equity"},
                {"ticker": "JPM", "name": "JPMorgan Chase", "shares": 40, "current_price": 200.0, "buy_price": 180.0, "asset_type": "equity"},
                {"ticker": "GLD", "name": "SPDR Gold Trust", "shares": 30, "current_price": 230.0, "buy_price": 200.0, "asset_type": "gold"},
                {"ticker": "BND", "name": "Vanguard Total Bond", "shares": 100, "current_price": 75.0, "buy_price": 74.0, "asset_type": "bond"},
            ]
        }

    def test_factsheet_data_completeness(self):
        """Verifies that all sections of the institutional factsheet are populated."""
        data = InstitutionalReportingService.generate_factsheet_data(self.sample_portfolio)
        self.assertTrue(data["valid"])
        self.assertIn("portfolio", data)
        self.assertIn("regulatory", data)
        self.assertIn("ratios", data)
        self.assertIn("attribution", data)
        self.assertIn("crisis_stress_tests", data)
        self.assertIn("allocations", data)
        self.assertIn("top_holdings", data)
        self.assertIn("committee_memo", data)

        # Portfolio metrics
        pf = data["portfolio"]
        self.assertGreater(pf["total_aum"], 10000.0)
        self.assertEqual(pf["positions_count"], 8)
        self.assertEqual(pf["base_currency"], "EUR")

        # Top holdings
        top_h = data["top_holdings"]
        self.assertEqual(len(top_h), 8)
        self.assertGreater(top_h[0]["weight_pct"], top_h[-1]["weight_pct"])

    def test_ucits_5_10_40_compliance_logic(self):
        """Tests UCITS 5/10/40 concentration limits."""
        # 1. Compliant portfolio (well diversified, max holding <= 10%)
        equal_portfolio = {
            "id": "UCITS-COMPLIANT",
            "name": "Diversified UCITS Fund",
            "currency": "EUR",
            "holdings": [{"ticker": f"STK_{i}", "name": f"Stock {i}", "shares": 10, "current_price": 100.0} for i in range(20)]
        }
        res_comp = InstitutionalReportingService.generate_factsheet_data(equal_portfolio)
        ucits_comp = res_comp["regulatory"]["ucits"]
        self.assertTrue(ucits_comp["compliant"])
        self.assertEqual(ucits_comp["status"], "COMPLIANT")
        self.assertEqual(len(ucits_comp["violations"]), 0)

        # 2. Breach single issuer > 10%
        breach_portfolio = {
            "id": "UCITS-BREACH-1",
            "name": "Concentrated Portfolio",
            "currency": "EUR",
            "holdings": [
                {"ticker": "BIG_POS", "name": "Dominant Corp", "shares": 500, "current_price": 100.0},
                {"ticker": "SMALL_1", "name": "Small 1", "shares": 20, "current_price": 100.0},
                {"ticker": "SMALL_2", "name": "Small 2", "shares": 20, "current_price": 100.0},
            ]
        }
        res_breach = InstitutionalReportingService.generate_factsheet_data(breach_portfolio)
        ucits_breach = res_breach["regulatory"]["ucits"]
        self.assertFalse(ucits_breach["compliant"])
        self.assertEqual(ucits_breach["status"], "BREACH")
        self.assertGreater(len(ucits_breach["issuers_over_10_pct"]), 0)

    def test_mifid_and_esg_scoring(self):
        """Verifies MiFID II SRI (1-7) and SFDR Article 8/9 classification."""
        data = InstitutionalReportingService.generate_factsheet_data(self.sample_portfolio)
        mifid = data["regulatory"]["mifid"]
        self.assertIn(mifid["sri"], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(mifid["investment_horizon_years"], 5)

        esg = data["regulatory"]["esg"]
        self.assertIn("sfdr_classification", esg)
        self.assertGreaterEqual(esg["portfolio_esg_score"], 0)
        self.assertLessEqual(esg["portfolio_esg_score"], 100)

    def test_api_endpoint_integration(self):
        """Tests GET /api/portfolio/{p_id}/institutional-report via TestClient."""
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

        # Get portfolios
        p_res = client.get("/api/portfolios", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        pfs = p_res.json()
        if not pfs:
            create_res = client.post("/api/portfolio/create", json={"name": "Reporting QA Test"}, cookies=cookies)
            p_id = create_res.json()["id"]
            client.post(f"/api/portfolio/{p_id}/holdings", json={"ticker": "AAPL", "shares": 25, "buyPrice": 160}, cookies=cookies)
        else:
            p_id = pfs[0]["id"]

        # Call endpoint
        report_res = client.get(f"/api/portfolio/{p_id}/institutional-report?benchmark=msci_world", cookies=cookies)
        self.assertEqual(report_res.status_code, 200)
        rep_data = report_res.json()
        self.assertTrue(rep_data.get("valid"))
        self.assertIn("regulatory", rep_data)
        self.assertIn("ratios", rep_data)
        self.assertIn("committee_memo", rep_data)
        self.assertIn("top_holdings", rep_data)


if __name__ == "__main__":
    unittest.main()
