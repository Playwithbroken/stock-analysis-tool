# QA Test Suite for Feature 7: DCF Valuation Model & Reverse DCF
import unittest
import os
from unittest.mock import patch
from datetime import datetime
from starlette.testclient import TestClient

from src.analyzer import StockAnalyzer
from src.data_fetcher import DataFetcher
import api

class TestDCFValuation(unittest.TestCase):
    def setUp(self):
        self.mock_stock_data = {
            'ticker': 'MSFT',
            'price_data': {'current_price': 400.0, 'currency': 'USD'},
            'fundamentals': {
                'free_cashflow': 70_000_000_000.0,
                'total_cash': 80_000_000_000.0,
                'total_debt': 60_000_000_000.0,
                'shares_outstanding': 7_400_000_000.0,
                'revenue_growth': 0.15,
                'earnings_growth': 0.18,
            },
            'volatility': {'beta': 1.15}
        }
        self.analyzer = StockAnalyzer(self.mock_stock_data)

    def test_dcf_basic_calculation(self):
        res = self.analyzer.calculate_dcf()
        self.assertEqual(res['ticker'], 'MSFT')
        self.assertEqual(res['currency'], 'USD')
        self.assertEqual(res['current_price'], 400.0)
        self.assertGreater(res['fair_value'], 0.0)
        self.assertGreater(res['target_buy_price'], 0.0)
        self.assertEqual(res['margin_of_safety_pct'], 20.0)
        self.assertIn('evaluation', res)
        self.assertIn('action_badge', res)
        self.assertIn(res['action_badge'], ['BUY', 'HOLD', 'REDUCE'])
        self.assertEqual(len(res['projections']), 5)

    def test_reverse_dcf_implied_growth(self):
        res = self.analyzer.calculate_dcf()
        implied_g = res['implied_growth_rate']
        self.assertIsNotNone(implied_g)
        # Verify that evaluating DCF with this implied growth yields current price within 1.0 USD
        recalc = self.analyzer.calculate_dcf(fcf_growth_rate=implied_g / 100.0)
        self.assertAlmostEqual(recalc['fair_value'], 400.0, delta=1.0)

    def test_scenarios_monotonicity(self):
        res = self.analyzer.calculate_dcf()
        scenarios = res['scenarios']
        bear_fv = scenarios['bear']['fair_value']
        base_fv = scenarios['base']['fair_value']
        bull_fv = scenarios['bull']['fair_value']
        self.assertLess(bear_fv, base_fv)
        self.assertLess(base_fv, bull_fv)

    def test_sensitivity_matrix_properties(self):
        res = self.analyzer.calculate_dcf()
        matrix_data = res['sensitivity_matrix']
        wacc_axis = matrix_data['wacc_axis']
        growth_axis = matrix_data['growth_axis']
        grid = matrix_data['matrix']

        self.assertEqual(len(wacc_axis), 5)
        self.assertEqual(len(growth_axis), 5)
        self.assertEqual(len(grid), 5)

        # In any given row (fixed WACC), higher growth must yield higher fair value
        for row in grid:
            self.assertEqual(len(row), 5)
            for j in range(len(row) - 1):
                self.assertLess(row[j]['fair_value'], row[j + 1]['fair_value'])

        # In any given column (fixed growth), higher WACC must yield lower fair value
        for col_idx in range(5):
            for row_idx in range(4):
                self.assertGreater(grid[row_idx][col_idx]['fair_value'], grid[row_idx + 1][col_idx]['fair_value'])

    def test_custom_parameters(self):
        res = self.analyzer.calculate_dcf(
            fcf_growth_rate=0.12,
            discount_rate=0.08,
            terminal_growth_rate=0.03,
            projection_years=5,
            margin_of_safety=0.30,
            custom_base_fcf=80_000_000_000.0
        )
        self.assertEqual(res['margin_of_safety_pct'], 30.0)
        self.assertEqual(res['inputs']['base_fcf'], 80_000_000_000.0)
        self.assertEqual(res['inputs']['discount_rate'], 0.08)
        self.assertEqual(res['target_buy_price'], round(res['fair_value'] * 0.70, 2))

    def test_api_endpoints_with_mock(self):
        client = TestClient(api.app)
        pw = os.environ.get('APP_ACCESS_PASSWORD')
        if pw:
            client.post('/api/auth/login', json={'password': pw})

        mock_payload = {
            'ticker': 'TESTCO',
            'price_data': {'current_price': 150.0, 'currency': 'USD'},
            'fundamentals': {
                'free_cashflow': 5_000_000_000.0,
                'total_cash': 2_000_000_000.0,
                'total_debt': 4_000_000_000.0,
                'shares_outstanding': 1_000_000_000.0,
                'revenue_growth': 0.10,
                'earnings_growth': 0.12,
            },
            'volatility': {'beta': 1.0},
        }

        with patch.object(DataFetcher, 'get_all_data', return_value=mock_payload):
            # 1. Test GET endpoint
            get_res = client.get('/api/analyze/TESTCO/dcf')
            self.assertEqual(get_res.status_code, 200)
            data = get_res.json()
            self.assertEqual(data['ticker'], 'TESTCO')
            self.assertEqual(data['current_price'], 150.0)
            self.assertIn('fair_value', data)
            self.assertIn('implied_growth_rate', data)

            # 2. Test POST endpoint with custom parameters
            post_res = client.post('/api/analyze/TESTCO/dcf', json={
                'fcf_growth_rate': 0.15,
                'discount_rate': 0.09,
                'terminal_growth_rate': 0.025,
                'margin_of_safety': 0.25
            })
            self.assertEqual(post_res.status_code, 200)
            custom_data = post_res.json()
            self.assertEqual(custom_data['margin_of_safety_pct'], 25.0)
            self.assertEqual(custom_data['inputs']['fcf_growth_rate'], 0.15)
            self.assertEqual(custom_data['inputs']['discount_rate'], 0.09)

if __name__ == '__main__':
    unittest.main()
