"""
QA Test Suite: Portfolio Heat Shield & Telegram Inline Keyboard Callbacks
"""
import unittest
from unittest.mock import MagicMock, patch

from src.portfolio_heat_service import PortfolioHeatService
from src.telegram_interactive_service import TelegramInteractiveService


class TestPortfolioHeatService(unittest.TestCase):
    def setUp(self):
        self.service = PortfolioHeatService(max_portfolio_heat_pct=2.5, max_cluster_risk_pct=1.8)

    def test_pearson_calculation(self):
        x = [0.01, 0.02, -0.01, 0.03, -0.02]
        y = [0.02, 0.04, -0.02, 0.06, -0.04]  # Perfectly correlated
        corr = self.service._pearson(x, y)
        self.assertAlmostEqual(corr, 1.0, places=2)

        # Inversely correlated
        z = [-0.01, -0.02, 0.01, -0.03, 0.02]
        corr_inv = self.service._pearson(x, z)
        self.assertAlmostEqual(corr_inv, -1.0, places=2)

    def test_portfolio_heat_evaluation(self):
        # Trade 1: 50 shares, entry 100, stop 94 -> risk 300 EUR (0.6% on 50k)
        # Trade 2: 40 shares, entry 150, stop 140 -> risk 400 EUR (0.8% on 50k)
        active_trades = [
            {
                "ticker": "NVDA",
                "entry_price": 100.0,
                "trailing_stop": 94.0,
                "recommended_shares": 50,
                "status": "OPEN",
            },
            {
                "ticker": "AMD",
                "entry_price": 150.0,
                "trailing_stop": 140.0,
                "recommended_shares": 40,
                "status": "OPEN",
            },
        ]

        # Mock correlation of NVDA and AMD to 0.85
        with patch.object(self.service, "compute_correlation_matrix", return_value={
            "tickers": ["NVDA", "AMD"],
            "matrix": {"NVDA": {"AMD": 0.85}, "AMD": {"NVDA": 0.85}},
            "high_correlation_pairs": [
                {"ticker_a": "NVDA", "ticker_b": "AMD", "correlation": 0.85, "cluster_level": "CRITICAL"}
            ],
        }):
            heat = self.service.evaluate_portfolio_heat(active_trades, portfolio_capital=50000.0)

            # Total risk = 300 + 400 = 700 EUR -> 1.4%
            self.assertEqual(heat["total_risk_amount"], 700.0)
            self.assertEqual(heat["portfolio_heat_pct"], 1.4)
            self.assertFalse(heat["is_overheated"])

            card = self.service.format_telegram_heat_card(heat)
            self.assertIn("PORTFOLIO HEAT & RISIKO-SHIELD", card)
            self.assertIn("1.40%", card)
            self.assertIn("700.00 EUR", card)

    def test_target_1_hit_zero_risk(self):
        # Trade where Target 1 was reached: stop moved to Breakeven (100.0)
        active_trades = [
            {
                "ticker": "NVDA",
                "entry_price": 100.0,
                "trailing_stop": 100.0,
                "recommended_shares": 50,
                "status": "TARGET_1_HIT",
            },
        ]
        with patch.object(self.service, "compute_correlation_matrix", return_value={"high_correlation_pairs": []}):
            heat = self.service.evaluate_portfolio_heat(active_trades, portfolio_capital=50000.0)
            # Risk should be 0 (house money)
            self.assertEqual(heat["total_risk_amount"], 0.0)
            self.assertEqual(heat["portfolio_heat_pct"], 0.0)


class TestTelegramCallbacks(unittest.TestCase):
    def setUp(self):
        self.mock_asymmetric = MagicMock()
        self.mock_options = MagicMock()
        self.mock_volume = MagicMock()
        self.mock_lifecycle = MagicMock()
        self.mock_heat = MagicMock()

        self.service = TelegramInteractiveService(
            bot_token="test_token",
            allowed_chat_ids="999888",
            asymmetric_trade_service=self.mock_asymmetric,
            options_edge_service=self.mock_options,
            volume_profile_service=self.mock_volume,
            trade_lifecycle_service=self.mock_lifecycle,
            portfolio_heat_service=self.mock_heat,
        )

    @patch.object(TelegramInteractiveService, "answer_callback_query")
    @patch.object(TelegramInteractiveService, "send_message")
    def test_callback_gex(self, mock_send, mock_answer):
        self.mock_options.analyze_gex.return_value = {
            "spot_price": 120.0,
            "call_wall": 130.0,
            "put_wall": 110.0,
            "zero_gamma": 118.0,
            "net_gex": 100000.0,
            "regime": "positive_gamma",
            "regime_label": "Positives Gamma",
        }
        self.service.handle_callback_query("999888", "gex:NVDA", "query_123")
        mock_answer.assert_called_once_with("query_123", "GEX für NVDA wird geladen...")
        mock_send.assert_called_once()
        self.assertIn("GAMMA EXPOSURE (GEX): NVDA", mock_send.call_args[0][1])

    @patch.object(TelegramInteractiveService, "answer_callback_query")
    @patch.object(TelegramInteractiveService, "send_message")
    def test_callback_track(self, mock_send, mock_answer):
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "ticker": "TSLA",
            "target_1": 220.0,
            "invalidation_price": 190.0,
        }
        self.service.handle_callback_query("999888", "track:TSLA", "query_456")
        mock_answer.assert_called_once_with("query_456", "✅ TSLA wird jetzt live überwacht!", show_alert=True)
        self.mock_lifecycle.register_trade.assert_called_once()
        mock_send.assert_called_once()
        self.assertIn("LIVE-TRACKING AKTIVIERT: TSLA", mock_send.call_args[0][1])

    @patch.object(TelegramInteractiveService, "answer_callback_query")
    def test_unauthorized_callback(self, mock_answer):
        self.service.handle_callback_query("111111", "gex:NVDA", "query_789")
        mock_answer.assert_called_once_with("query_789", "⛔ Nicht autorisiert.", show_alert=True)


if __name__ == "__main__":
    unittest.main()
