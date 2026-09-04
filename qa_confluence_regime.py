"""
QA Test Suite — Confluence Scoring & Market Regime Engine
Tests:
  1. VIX thresholds and Market Stance (RISK_ON, CAUTIOUS, RISK_OFF).
  2. SPY/QQQ trend analysis.
  3. Confluence Score calculation & Grading (A+, A, B).
  4. Chart overlay levels presence in trade setup tickets.
  5. Telegram message formatting with grade badges and confluence factors.
"""
import unittest
from unittest.mock import MagicMock, patch

from src.market_regime_service import MarketRegimeService
from src.asymmetric_trade_service import AsymmetricTradeService
from src.options_edge_service import OptionsEdgeService
from src.volume_profile_service import VolumeProfileService


class TestConfluenceAndRegime(unittest.TestCase):
    def test_market_regime_risk_on(self):
        service = MarketRegimeService()
        with patch.object(service, "_fetch_asset_trend") as mock_trend, \
             patch.object(service, "_fetch_vix") as mock_vix:
            mock_trend.return_value = {"symbol": "SPY", "trend": "bullish", "price": 550.0}
            mock_vix.return_value = {"value": 15.2, "regime": "risk_on", "label": "Niedrig"}

            regime = service._compute_market_regime()
            self.assertEqual(regime["stance"], "RISK_ON")
            self.assertEqual(regime["stance_color"], "green")

    def test_market_regime_risk_off_high_vix(self):
        service = MarketRegimeService()
        with patch.object(service, "_fetch_asset_trend") as mock_trend, \
             patch.object(service, "_fetch_vix") as mock_vix:
            mock_trend.return_value = {"symbol": "SPY", "trend": "bullish", "price": 550.0}
            mock_vix.return_value = {"value": 28.5, "regime": "risk_off", "label": "Hoch"}

            regime = service._compute_market_regime()
            self.assertEqual(regime["stance"], "RISK_OFF")
            self.assertEqual(regime["stance_color"], "red")

    def test_market_regime_cautious(self):
        service = MarketRegimeService()
        with patch.object(service, "_fetch_asset_trend") as mock_trend, \
             patch.object(service, "_fetch_vix") as mock_vix:
            # One bullish, one bearish
            mock_trend.side_effect = [
                {"symbol": "SPY", "trend": "bullish", "price": 550.0},
                {"symbol": "QQQ", "trend": "bearish", "price": 480.0},
            ]
            mock_vix.return_value = {"value": 17.0, "regime": "risk_on", "label": "Niedrig"}

            regime = service._compute_market_regime()
            self.assertEqual(regime["stance"], "CAUTIOUS")
            self.assertEqual(regime["stance_color"], "yellow")

    def test_asymmetric_confluence_scoring_and_overlay(self):
        mock_opt = MagicMock(spec=OptionsEdgeService)
        mock_vol = MagicMock(spec=VolumeProfileService)
        mock_reg = MagicMock(spec=MarketRegimeService)

        mock_vol.compute_volume_profile.return_value = {
            "poc_price": 100.0,
            "vah_price": 105.0,
            "val_price": 95.0,
            "market_location": "inside_value_area",
            "location_label": "Inside Value",
        }
        mock_opt.analyze_gex.return_value = {
            "regime": "positive_gamma",
            "regime_label": "Positiv (Dämpfend)",
            "call_wall": 115.0,
            "put_wall": 95.0,
        }
        mock_reg.get_market_regime.return_value = {
            "stance": "RISK_ON",
            "vix": {"value": 15.0},
        }

        trade_svc = AsymmetricTradeService(
            options_service=mock_opt,
            volume_service=mock_vol,
            regime_service=mock_reg,
        )

        with patch("src.asymmetric_trade_service.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.fast_info = {"lastPrice": 96.0}
            mock_yf.Ticker.return_value = mock_ticker

            ticket = trade_svc.generate_trade_setup("TEST", portfolio_capital=10000.0, risk_budget_pct=1.0)
            self.assertIsNotNone(ticket)
            self.assertIn("grade", ticket)
            self.assertIn(ticket["grade"], ["A+", "A", "B"])
            self.assertGreaterEqual(ticket["confluence_score"], 70)
            self.assertIn("chart_overlay_levels", ticket)

            overlay = ticket["chart_overlay_levels"]
            self.assertIn("poc", overlay)
            self.assertIn("vah", overlay)
            self.assertIn("val", overlay)
            self.assertIn("call_wall", overlay)
            self.assertIn("put_wall", overlay)
            self.assertIn("entry", overlay)
            self.assertIn("invalidation", overlay)
            self.assertIn("target_1", overlay)
            self.assertIn("target_2", overlay)

            # Invalidation must be strictly below entry
            self.assertLess(overlay["invalidation"], overlay["entry"])
            # Targets must be above entry
            self.assertGreater(overlay["target_1"], overlay["entry"])
            self.assertGreater(overlay["target_2"], overlay["target_1"])

            # Telegram html must contain grade and score
            self.assertIn(ticket["grade"], ticket["telegram_html"])
            self.assertIn(str(ticket["confluence_score"]), ticket["telegram_html"])


if __name__ == "__main__":
    unittest.main()
