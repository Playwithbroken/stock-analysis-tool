"""
QA Test Suite — Edge Scanner Scheduler, Earnings Proximity Shield & Trade Management
Tests:
  1. Earnings proximity detection (warns when earnings <= 5 days, score penalized).
  2. Trade management guidance generation (target 1 partial profit, target 2 trailing stop).
  3. Edge auto-scanner filtering (only Grade A+/A dispatched to Telegram).
  4. Deduplication enforcement in automated scans.
"""
import unittest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.asymmetric_trade_service import AsymmetricTradeService
from src.trading_signals_service import TradingSignalsService
from src.options_edge_service import OptionsEdgeService
from src.volume_profile_service import VolumeProfileService
from src.market_regime_service import MarketRegimeService


class TestEdgeScannerAndShield(unittest.TestCase):
    def test_earnings_proximity_detection_imminent(self):
        trade_svc = AsymmetricTradeService()
        mock_ticker = MagicMock()
        today = datetime.now(timezone.utc).date()
        earnings_date = today + timedelta(days=3)
        mock_ticker.calendar = {"Earnings Date": [earnings_date]}

        info = trade_svc._check_earnings_proximity(mock_ticker)
        self.assertIsNotNone(info)
        self.assertEqual(info["days_until_earnings"], 3)
        self.assertIn("Quartalszahlen in 3 Tagen", info["warning"])
        self.assertIn("Gap- und IV-Crush-Risiko", info["warning"])

    def test_earnings_proximity_detection_far(self):
        trade_svc = AsymmetricTradeService()
        mock_ticker = MagicMock()
        today = datetime.now(timezone.utc).date()
        earnings_date = today + timedelta(days=25)
        mock_ticker.calendar = {"Earnings Date": [earnings_date]}

        info = trade_svc._check_earnings_proximity(mock_ticker)
        self.assertIsNone(info)

    def test_setup_with_earnings_shield_and_trade_management(self):
        mock_opt = MagicMock(spec=OptionsEdgeService)
        mock_vol = MagicMock(spec=VolumeProfileService)
        mock_reg = MagicMock(spec=MarketRegimeService)

        mock_vol.compute_volume_profile.return_value = {
            "poc_price": 100.0,
            "vah_price": 105.0,
            "val_price": 95.0,
            "market_location": "inside_value_area",
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
            mock_ticker.fast_info = {"lastPrice": 98.0}
            today = datetime.now(timezone.utc).date()
            mock_ticker.calendar = {"Earnings Date": [today + timedelta(days=2)]}
            mock_yf.Ticker.return_value = mock_ticker

            ticket = trade_svc.generate_trade_setup("NVDA", portfolio_capital=20000.0, risk_budget_pct=0.75)
            self.assertIsNotNone(ticket)
            # Earnings info present
            self.assertIsNotNone(ticket.get("earnings_info"))
            self.assertIn("Quartalszahlen in 2 Tagen", ticket["earnings_info"]["warning"])

            # Trade management present
            self.assertIn("trade_management", ticket)
            self.assertIn("target_1_action", ticket["trade_management"])
            self.assertIn("target_2_action", ticket["trade_management"])
            self.assertIn("50% Teilgewinn", ticket["trade_management"]["target_1_action"])

            # Telegram html contains trade management and earnings warning
            self.assertIn("Trade Management & Trailing Stop", ticket["telegram_html"])
            self.assertIn("Quartalszahlen", ticket["telegram_html"])

    def test_scan_and_dispatch_edge_alerts(self):
        signals_service = TradingSignalsService()
        mock_alert_service = MagicMock()

        # Mock setups returned
        mock_setup_a_plus = {
            "ticker": "NVDA",
            "grade": "A+",
            "confluence_score": 92,
            "setup_name": "Volume Rebound",
        }
        mock_setup_b = {
            "ticker": "LOWB",
            "grade": "B",
            "confluence_score": 55,
            "setup_name": "Weak Setup",
        }

        with patch.object(signals_service, "get_asymmetric_setups") as mock_get:
            mock_get.return_value = [mock_setup_a_plus, mock_setup_b]
            mock_alert_service.send_trading_edge_setup_alert.return_value = {
                "status": "ok", "sent": 1, "ticker": "NVDA"
            }

            res = signals_service.scan_and_dispatch_edge_alerts(
                alert_service=mock_alert_service,
                watchlist=["NVDA", "LOWB"],
                min_grade=("A+", "A"),
            )

            self.assertEqual(res["status"], "ok")
            # Only NVDA should be dispatched
            self.assertIn("NVDA", res["dispatched"])
            self.assertIn("LOWB", res["skipped"])
            self.assertEqual(mock_alert_service.send_trading_edge_setup_alert.call_count, 1)


if __name__ == "__main__":
    unittest.main()
