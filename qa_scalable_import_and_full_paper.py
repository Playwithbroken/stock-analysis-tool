import os
import unittest
from src.scalable_integration_service import ScalableIntegrationService, SAMPLE_SCALABLE_POSITIONS
from src.paper_trading_service import PaperTradingService
from src.storage import PortfolioManager

class TestScalableImportAndFullPaper(unittest.TestCase):
    def setUp(self):
        self.scalable_service = ScalableIntegrationService()
        self.paper_service = PaperTradingService(PortfolioManager())

    def test_scalable_sample_import_and_analysis(self):
        # 1. Reset
        reset_res = self.scalable_service.reset_positions()
        self.assertTrue(reset_res.get("success"))

        # 2. Import sample positions
        import_res = self.scalable_service.import_positions(SAMPLE_SCALABLE_POSITIONS, source_label="Test Sample")
        self.assertTrue(import_res.get("success"))
        self.assertGreaterEqual(import_res.get("imported_count", 0), 5)

        # 3. Check portfolio analysis without network overhead
        analysis = self.scalable_service.portfolio_analysis(enrich_market_data=False)
        self.assertTrue(analysis.get("configured"))
        self.assertGreaterEqual(len(analysis.get("holdings", [])), 5)
        self.assertGreater(analysis.get("total_value", 0), 10000)

        # 4. Check status
        status = self.scalable_service.status()
        self.assertEqual(status.get("status"), "ok")
        self.assertGreaterEqual(status.get("position_count", 0), 5)

    def test_csv_parser(self):
        csv_data = "Ticker;Stuecke;Kaufkurs;Name\nSAP.DE;50;185.50;SAP SE\nNVDA;100;120.00;NVIDIA Corp\n"
        parsed = self.scalable_service.parse_holdings_csv(csv_data)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["symbol"], "SAP.DE")
        self.assertEqual(parsed[0]["shares"], 50.0)
        self.assertEqual(parsed[0]["avg_buy_price"], 185.50)

    def test_full_portfolio_paper_trading_config(self):
        cfg = self.paper_service._demo_account_config("full_portfolio")
        self.assertEqual(cfg["capital_profile"], "full_portfolio")
        self.assertEqual(cfg["starting_capital"], 500_000.0)
        self.assertEqual(cfg["risk_per_trade_pct"], 2.0)
        self.assertEqual(cfg["max_position_pct"], 25.0)
        self.assertEqual(cfg["target_gross_exposure_pct"], 90.0)
        self.assertEqual(cfg["max_gross_exposure_pct"], 96.0)
        self.assertEqual(cfg["max_equity_exposure_pct"], 95.0)
        self.assertEqual(cfg["max_open_trades"], 16)

        old_env = os.environ.get("PAPER_CAPITAL_PROFILE")
        try:
            os.environ["PAPER_CAPITAL_PROFILE"] = "full_portfolio"
            account = self.paper_service._build_demo_account([], [])
            self.assertEqual(account["capital_profile"], "full_portfolio")
            self.assertEqual(account["risk_budget_per_trade_value"], 10_000.0)
            self.assertEqual(account["max_position_value"], 125_000.0)
            self.assertEqual(account["max_gross_exposure_value"], 480_000.0)
            self.assertEqual(account["capital_deployment"]["target_gross_exposure_value"], 450_000.0)
            self.assertEqual(account["open_trade_slots"], 16)
        finally:
            if old_env is not None:
                os.environ["PAPER_CAPITAL_PROFILE"] = old_env
            else:
                os.environ.pop("PAPER_CAPITAL_PROFILE", None)

if __name__ == "__main__":
    unittest.main()
