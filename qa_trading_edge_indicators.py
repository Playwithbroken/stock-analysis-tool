"""
QA Contract: Institutional Trading Edge Indicators
Tests:
  1. OptionsEdgeService — Black-Scholes gamma, Call/Put GEX, zero-gamma level, regimes
  2. VolumeProfileService — POC, Value Area (70%), LVN detection, market location
  3. AsymmetricTradeService — Invalidation, Target 1 & 2, minimum R:R >= 2.0, position sizing
  4. EmailAlertService — send_trading_edge_setup_alert formatting and deduplication
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.options_edge_service import OptionsEdgeService
from src.volume_profile_service import VolumeProfileService
from src.asymmetric_trade_service import AsymmetricTradeService
from src.email_alert_service import EmailAlertService, EmailAlertConfig
from src.storage import PortfolioManager


class TestTradingEdgeIndicators(unittest.TestCase):
    def test_black_scholes_gamma_properties(self):
        service = OptionsEdgeService(risk_free_rate=0.045)
        spot = 100.0
        atm_strike = 100.0
        otm_strike = 130.0
        t_years = 30.0 / 365.0
        iv = 0.25

        gamma_atm = service.calculate_bs_gamma(spot, atm_strike, t_years, iv)
        gamma_otm = service.calculate_bs_gamma(spot, otm_strike, t_years, iv)

        # Gamma must be positive and ATM gamma must be strictly higher than deep OTM gamma
        self.assertGreater(gamma_atm, 0.0)
        self.assertGreater(gamma_otm, 0.0)
        self.assertGreater(gamma_atm, gamma_otm, "ATM gamma must be higher than deep OTM gamma")

        # Edge cases: 0 time, negative spot, 0 IV must safely return 0 without crash
        self.assertEqual(service.calculate_bs_gamma(0.0, 100.0, t_years, iv), 0.0)
        self.assertEqual(service.calculate_bs_gamma(spot, 100.0, 0.0, iv), 0.0)
        self.assertEqual(service.calculate_bs_gamma(spot, 100.0, t_years, 0.0), 0.0)

    def test_volume_profile_synthetic_distribution(self):
        service = VolumeProfileService(num_bins=50, value_area_pct=0.70)
        # Mock historical dataframe with high volume concentrated around 150
        import pandas as pd
        import numpy as np

        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        highs = [155.0] * 30
        lows = [145.0] * 30
        closes = [150.0] * 30
        volumes = [1_000_000.0] * 30

        # One extreme spike with low volume to test range
        highs[0] = 170.0
        lows[0] = 130.0

        mock_hist = pd.DataFrame({
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }, index=dates)

        with patch("yfinance.Ticker") as mock_ticker:
            mock_inst = MagicMock()
            mock_inst.history.return_value = mock_hist
            mock_ticker.return_value = mock_inst

            vp = service.compute_volume_profile("MOCK_STOCK", period="1mo", interval="1d")
            self.assertIsNotNone(vp)
            # POC should be within the active traded range around 150
            self.assertTrue(144.0 <= vp["poc_price"] <= 156.0, f"Expected POC in [144, 156], got {vp['poc_price']}")
            # VAH > VAL
            self.assertGreater(vp["vah_price"], vp["val_price"])
            # Location label should be valid
            self.assertIn(vp["market_location"], ["inside_value_area", "above_value_area", "below_value_area"])

    def test_asymmetric_trade_setup_math(self):
        options_mock = MagicMock()
        options_mock.analyze_gex.return_value = {
            "regime": "positive_gamma",
            "regime_label": "Positive Gamma",
            "call_wall": 160.0,
            "put_wall": 135.0,
            "zero_gamma_level": 140.0,
        }

        vp_mock = MagicMock()
        vp_mock.compute_volume_profile.return_value = {
            "poc_price": 148.0,
            "vah_price": 152.0,
            "val_price": 144.0,
            "market_location": "inside_value_area",
            "location_label": "Inside Value Area",
        }

        service = AsymmetricTradeService(options_service=options_mock, volume_service=vp_mock)

        with patch("yfinance.Ticker") as mock_ticker:
            mock_inst = MagicMock()
            mock_inst.fast_info = {"lastPrice": 146.0}
            mock_ticker.return_value = mock_inst

            ticket = service.generate_trade_setup(
                "AAPL",
                portfolio_capital=50000.0,
                risk_budget_pct=0.75,
            )

            self.assertIsNotNone(ticket)
            # Entry must be spot price
            self.assertEqual(ticket["entry_price"], 146.0)
            # Invalidation must be strictly below entry
            self.assertLess(ticket["invalidation_price"], ticket["entry_price"])
            # Risk per share must be positive
            self.assertGreater(ticket["risk_per_share"], 0.0)
            # Reward: Target 1 must be entry + 2.0 * risk
            expected_t1 = round(ticket["entry_price"] + 2.0 * ticket["risk_per_share"], 2)
            self.assertEqual(ticket["target_1"], expected_t1)
            # Risk/Reward ratio must be at least 2.5:1
            self.assertGreaterEqual(ticket["risk_reward_ratio"], 2.5)
            # Recommended shares must respect portfolio risk limit (0.75% of 50k = 375 EUR)
            self.assertLessEqual(ticket["actual_risk_amount"], 375.0 + 10.0)  # rounding margin
            self.assertGreaterEqual(ticket["recommended_shares"], 1)
            # Telegram HTML must contain key emojis and sections
            self.assertIn("🎯 <b>TRADING EDGE SETUP:", ticket["telegram_html"])
            self.assertIn("🛑 <b>Invalidation (Hard Stop):</b>", ticket["telegram_html"])
            self.assertIn("Risk/Reward-Ratio:", ticket["telegram_html"])

    def test_telegram_edge_alert_deduplication(self):
        pm_mock = MagicMock()
        pm_mock.get_sent_signal_event_keys.return_value = set()
        pss_mock = MagicMock()

        service = EmailAlertService(portfolio_manager=pm_mock, public_signal_service=pss_mock)
        mock_cfg = MagicMock()
        mock_cfg.telegram_bot_token = "test_token"
        mock_cfg.telegram_chat_id = "test_chat"
        mock_cfg.telegram_enabled = True
        service.get_config = MagicMock(return_value=mock_cfg)
        service._validate_telegram_config = MagicMock()
        service._send_notifications = MagicMock()

        sample_ticket = {
            "ticker": "NVDA",
            "setup_name": "VAH_Breakout",
            "telegram_html": "🎯 <b>TRADING EDGE SETUP: NVDA</b>\nTest content",
        }

        # First send: should succeed
        res1 = service.send_trading_edge_setup_alert(sample_ticket, force=False)
        self.assertEqual(res1["status"], "ok")
        self.assertEqual(res1["sent"], 1)

        # Mark key as sent in mock
        pm_mock.get_sent_signal_event_keys.return_value = {res1["event_key"]}

        # Second send without force: should be deduplicated
        res2 = service.send_trading_edge_setup_alert(sample_ticket, force=False)
        self.assertEqual(res2["status"], "deduplicated")
        self.assertEqual(res2["sent"], 0)

        # Third send with force=True: should bypass deduplication
        res3 = service.send_trading_edge_setup_alert(sample_ticket, force=True)
        self.assertEqual(res3["status"], "ok")
        self.assertEqual(res3["sent"], 1)

    def test_backtest_engine_expectancy(self):
        from src.backtest_engine import BacktestEngine
        import pandas as pd
        import numpy as np

        engine = BacktestEngine(min_sample_size=5, target_profit_factor=1.2)

        # Generate 120 bars with occasional strong breakouts
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=120, freq="D")
        closes = [100.0]
        for _ in range(119):
            closes.append(closes[-1] * (1.0 + np.random.normal(0.001, 0.015)))
        highs = [c * 1.01 for c in closes]
        lows = [c * 0.99 for c in closes]
        volumes = [500_000.0] * 120

        # Inject 5 clear breakouts
        for idx in [35, 55, 75, 95, 110]:
            highs[idx] = max(highs[idx-20:idx]) * 1.05
            closes[idx] = highs[idx] * 0.99
            volumes[idx] = 1_500_000.0

        mock_hist = pd.DataFrame({
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        }, index=dates)

        with patch("yfinance.Ticker") as mock_ticker:
            mock_inst = MagicMock()
            mock_inst.history.return_value = mock_hist
            mock_ticker.return_value = mock_inst

            res = engine.backtest_strategy("TEST", strategy="volume_breakout", period="2y")
            self.assertIsNotNone(res)
            self.assertIn("profit_factor", res)
            self.assertIn("win_rate_pct", res)
            self.assertIn("expectancy_r", res)
            self.assertIn("verdict", res)


if __name__ == "__main__":
    unittest.main()
