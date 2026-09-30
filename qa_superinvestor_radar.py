"""QA test suite for Feature 8: Insider & Superinvestor Radar."""

import os
import sys
import unittest
import pandas as pd
from datetime import datetime
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from src.superinvestor_service import SuperinvestorService, SUPERINVESTORS
from src.data_fetcher import DataFetcher
import api

class TestSuperinvestorRadar(unittest.TestCase):
    def test_superinvestors_ticker_lookup(self):
        # 1. AAPL should be held by Warren Buffett (highest conviction) and Li Lu
        aapl_investors = SuperinvestorService.get_superinvestors_for_ticker("AAPL")
        self.assertGreater(len(aapl_investors), 0)
        investor_names = [inv["investor_name"] for inv in aapl_investors]
        self.assertIn("Warren Buffett", investor_names)
        self.assertIn("Li Lu", investor_names)
        buffett = next(i for i in aapl_investors if i["investor_name"] == "Warren Buffett")
        self.assertEqual(buffett["firm"], "Berkshire Hathaway")
        self.assertGreater(buffett["weight_pct"], 20.0)

        # 2. BABA should be held by Michael Burry
        baba_investors = SuperinvestorService.get_superinvestors_for_ticker("BABA")
        baba_names = [inv["investor_name"] for inv in baba_investors]
        self.assertIn("Michael Burry", baba_names)

        # 3. GOOGL should be held by Bill Ackman, Li Lu, and Terry Smith
        googl_investors = SuperinvestorService.get_superinvestors_for_ticker("GOOGL")
        googl_names = [inv["investor_name"] for inv in googl_investors]
        self.assertIn("Bill Ackman", googl_names)
        self.assertIn("Li Lu", googl_names)
        self.assertIn("Terry Smith", googl_names)

        # 4. Unknown ticker returns empty list
        unknown = SuperinvestorService.get_superinvestors_for_ticker("XYZ999UNKNOWN")
        self.assertEqual(unknown, [])

    def test_parse_insider_transactions(self):
        # Create mock DataFrame matching yfinance structure
        mock_df = pd.DataFrame([
            {
                "Shares": 5000,
                "Value": 750000.0,
                "Text": "Purchase at price 150.00 per share.",
                "Insider": "SMITH JOHN",
                "Position": "Chief Executive Officer",
                "Transaction": "Purchase",
                "Start Date": pd.Timestamp("2026-08-15"),
                "Ownership": "D",
            },
            {
                "Shares": 2000,
                "Value": 320000.0,
                "Text": "Sale at price 160.00 per share.",
                "Insider": "DOE JANE",
                "Position": "Chief Financial Officer",
                "Transaction": "Sale",
                "Start Date": pd.Timestamp("2026-08-10"),
                "Ownership": "D",
            },
            {
                "Shares": 10000,
                "Value": 0.0,
                "Text": "Stock Award(Grant) at price 0.00 per share.",
                "Insider": "BROWN BOB",
                "Position": "Director",
                "Transaction": "",
                "Start Date": pd.Timestamp("2026-07-20"),
                "Ownership": "D",
            }
        ])

        parsed = SuperinvestorService.parse_insider_transactions(mock_df)
        self.assertEqual(len(parsed), 3)

        # First row: Purchase
        self.assertEqual(parsed[0]["insider"], "SMITH JOHN")
        self.assertEqual(parsed[0]["transaction_type"], "Kauf")
        self.assertTrue(parsed[0]["is_purchase"])
        self.assertEqual(parsed[0]["price_per_share"], 150.0)
        self.assertEqual(parsed[0]["badge_color"], "emerald")

        # Second row: Sale
        self.assertEqual(parsed[1]["insider"], "DOE JANE")
        self.assertEqual(parsed[1]["transaction_type"], "Verkauf")
        self.assertFalse(parsed[1]["is_purchase"])
        self.assertEqual(parsed[1]["badge_color"], "rose")

        # Third row: Grant
        self.assertEqual(parsed[2]["transaction_type"], "Vergütung (Grant)")
        self.assertEqual(parsed[2]["badge_color"], "slate")

    def test_parse_insider_summary(self):
        # Bullish scenario (purchases exceed sales)
        tx_bullish = [
            {"is_purchase": True, "transaction_type": "Kauf", "value": 500000.0},
            {"is_purchase": True, "transaction_type": "Kauf", "value": 400000.0},
            {"is_purchase": False, "transaction_type": "Verkauf", "value": 100000.0},
        ]
        summary_bull = SuperinvestorService.parse_insider_summary(None, tx_bullish)
        self.assertEqual(summary_bull["sentiment"], "BULLISH")
        self.assertEqual(summary_bull["buy_count"], 2)
        self.assertEqual(summary_bull["sell_count"], 1)

        # Bearish scenario
        tx_bearish = [
            {"is_purchase": False, "transaction_type": "Verkauf", "value": 1000000.0},
            {"is_purchase": False, "transaction_type": "Verkauf", "value": 800000.0},
            {"is_purchase": False, "transaction_type": "Verkauf", "value": 500000.0},
        ]
        summary_bear = SuperinvestorService.parse_insider_summary(None, tx_bearish)
        self.assertEqual(summary_bear["sentiment"], "BEARISH")

    def test_portfolio_superinvestors(self):
        # Portfolio with AAPL, GOOGL, and an unheld stock
        mock_holdings = [
            {"ticker": "AAPL", "name": "Apple Inc.", "shares": 10, "current_price": 200.0, "value": 2000.0},
            {"ticker": "GOOGL", "name": "Alphabet Inc.", "shares": 10, "current_price": 170.0, "value": 1700.0},
            {"ticker": "UNKNOWNCO", "name": "Unknown Co.", "shares": 10, "current_price": 50.0, "value": 500.0},
        ]
        res = SuperinvestorService.get_portfolio_superinvestors(mock_holdings)
        self.assertEqual(res["total_holdings"], 3)
        self.assertEqual(res["endorsed_holdings_count"], 2)
        # Endorsed value: 2000 + 1700 = 3700 out of 4200 => ~88.1%
        self.assertAlmostEqual(res["smart_money_percentage"], 88.1, delta=0.5)
        self.assertIn("Warren Buffett", res["superinvestors_involved"])
        self.assertIn("Bill Ackman", res["superinvestors_involved"])
        self.assertIn("Li Lu", res["superinvestors_involved"])
        self.assertEqual(len(res["endorsed_holdings"]), 2)

    def test_api_stock_and_portfolio_endpoints(self):
        client = TestClient(api.app)
        pw = os.environ.get("APP_ACCESS_PASSWORD")
        if pw:
            client.post("/api/auth/login", json={"password": pw})

        # 1. Test GET /api/analyze/AAPL/insiders
        res = client.get("/api/analyze/AAPL/insiders")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["ticker"], "AAPL")
        self.assertIn("superinvestors", data)
        self.assertIn("summary", data)
        self.assertIn("institutional_holders", data)
        self.assertGreater(data["superinvestors_count"], 0)

        # 2. Create portfolio and test GET /api/portfolio/{p_id}/superinvestors
        create_res = client.post("/api/portfolios", json={"name": "Superinvestor Test Portfolio"})
        self.assertEqual(create_res.status_code, 200)
        p_id = create_res.json()["id"]

        # Add AAPL and GOOGL
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "AAPL", "shares": 10, "buyPrice": 180.0})
        client.post(f"/api/portfolios/{p_id}/holdings", json={"ticker": "GOOGL", "shares": 5, "buyPrice": 160.0})

        # Query endpoint with singular and plural aliases
        res_sing = client.get(f"/api/portfolio/{p_id}/superinvestors")
        res_plur = client.get(f"/api/portfolios/{p_id}/superinvestors")
        self.assertEqual(res_sing.status_code, 200)
        self.assertEqual(res_plur.status_code, 200)

        p_data = res_sing.json()
        self.assertEqual(p_data["total_holdings"], 2)
        self.assertEqual(p_data["endorsed_holdings_count"], 2)
        self.assertEqual(p_data["smart_money_percentage"], 100.0)
        self.assertIn("Warren Buffett", p_data["superinvestors_involved"])


if __name__ == "__main__":
    unittest.main()
