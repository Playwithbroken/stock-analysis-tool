"""
QA Test Suite: Interactive 2-Way Telegram Bot, Trade Lifecycle Manager & Relative Strength
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from src.relative_strength_service import RelativeStrengthService
from src.trade_lifecycle_service import TradeLifecycleService
from src.telegram_interactive_service import TelegramInteractiveService


class TestRelativeStrengthService(unittest.TestCase):
    def test_rs_card_formatting(self):
        service = RelativeStrengthService()
        sample_leaders = [
            {
                "ticker": "NVDA",
                "mansfield_rs": 14.5,
                "alpha_1m": 6.2,
                "badge": "🔥 Starker Leader",
                "divergent_strength": True,
            },
            {
                "ticker": "PLTR",
                "mansfield_rs": 8.1,
                "alpha_1m": 4.0,
                "badge": "⭐ Outperformer",
                "divergent_strength": False,
            },
        ]
        card = service.format_telegram_rs_card(sample_leaders, benchmark="SPY")
        self.assertIn("RELATIVE STÄRKE VS. SPY", card)
        self.assertIn("NVDA", card)
        self.assertIn("+14.5% RS", card)
        self.assertIn("Stark trotz Markt", card)
        self.assertIn("PLTR", card)


class TestTradeLifecycleService(unittest.TestCase):
    def setUp(self):
        self.mock_pm = MagicMock()
        self.mock_pm.get_app_setting.return_value = ""
        self.service = TradeLifecycleService(self.mock_pm)
        self.mock_alert_svc = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.telegram_enabled = True
        mock_cfg.telegram_bot_token = "mock_token"
        mock_cfg.telegram_chat_id = "12345"
        self.mock_alert_svc.get_config.return_value = mock_cfg

    def test_trade_registration(self):
        ticket = {
            "ticker": "NVDA",
            "setup_name": "VAH Breakout",
            "entry_price": 120.0,
            "invalidation_price": 114.0,
            "target_1": 132.0,  # 2.0R
            "target_2": 141.0,  # 3.5R
            "risk_per_share": 6.0,
            "recommended_shares": 50,
            "confluence_score": 85,
            "grade": "A+",
            "grade_badge": "💎 Grade A+",
        }
        res = self.service.register_trade(ticket)
        self.assertEqual(res["status"], "registered")

        trades = self.service.get_active_trades()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["ticker"], "NVDA")
        self.assertEqual(trades[0]["status"], "OPEN")
        self.assertEqual(trades[0]["trailing_stop"], 114.0)

    def test_target_1_and_breakeven_trailing_stop(self):
        ticket = {
            "ticker": "NVDA",
            "entry_price": 120.0,
            "invalidation_price": 114.0,
            "target_1": 132.0,
            "target_2": 141.0,
            "risk_per_share": 6.0,
            "recommended_shares": 50,
            "confluence_score": 85,
        }
        self.service.register_trade(ticket)

        # Mock price crossing Target 1 (133.0 >= 132.0)
        with patch.object(self.service, "_fetch_current_price", return_value=133.0):
            eval_res = self.service.evaluate_active_trades(self.mock_alert_svc)
            self.assertEqual(len(eval_res["actions"]), 1)
            self.assertEqual(eval_res["actions"][0]["action"], "TARGET_1_HIT")

            # Verify trade state
            trade = self.service.get_active_trades()[0]
            self.assertEqual(trade["status"], "TARGET_1_HIT")
            # Trailing stop must have moved up to Breakeven (120.0)
            self.assertEqual(trade["trailing_stop"], 120.0)
            self.assertIn("TARGET_1_HIT", trade["events_fired"])

            # Verify Telegram notification was dispatched
            self.mock_alert_svc._send_notifications.assert_called_once()
            call_args = self.mock_alert_svc._send_notifications.call_args[0]
            events = call_args[1]
            self.assertIn("TARGET 1 ERREICHT: NVDA", events[0]["line"])
            self.assertIn("50% der Position schließen", events[0]["line"])
            self.assertIn("Stop-Loss auf Breakeven ($120.00)", events[0]["line"])

    def test_target_2_runner_completion(self):
        ticket = {
            "ticker": "NVDA",
            "entry_price": 120.0,
            "invalidation_price": 114.0,
            "target_1": 132.0,
            "target_2": 141.0,
            "risk_per_share": 6.0,
        }
        self.service.register_trade(ticket)

        # Step 1: Hit T1
        with patch.object(self.service, "_fetch_current_price", return_value=133.0):
            self.service.evaluate_active_trades(self.mock_alert_svc)

        self.mock_alert_svc._send_notifications.reset_mock()

        # Step 2: Hit T2 (142.0 >= 141.0)
        with patch.object(self.service, "_fetch_current_price", return_value=142.0):
            eval_res = self.service.evaluate_active_trades(self.mock_alert_svc)
            self.assertEqual(eval_res["actions"][0]["action"], "TARGET_2_HIT")
            trade = self.service.get_active_trades()[0]
            self.assertEqual(trade["status"], "TARGET_2_HIT")

            call_args = self.mock_alert_svc._send_notifications.call_args[0]
            events = call_args[1]
            self.assertIn("TARGET 2 ERREICHT: NVDA", events[0]["line"])
            self.assertIn("Maximales Kursziel", events[0]["line"])

    def test_stop_loss_invalidation(self):
        ticket = {
            "ticker": "TSLA",
            "entry_price": 200.0,
            "invalidation_price": 190.0,
            "target_1": 220.0,
            "target_2": 235.0,
            "risk_per_share": 10.0,
        }
        self.service.register_trade(ticket)

        # Mock price dropping below stop loss (188.0 <= 190.0)
        with patch.object(self.service, "_fetch_current_price", return_value=188.0):
            eval_res = self.service.evaluate_active_trades(self.mock_alert_svc)
            self.assertEqual(eval_res["actions"][0]["action"], "STOPPED_OUT")
            trade = self.service.get_active_trades()[0]
            self.assertEqual(trade["status"], "STOPPED_OUT")

            call_args = self.mock_alert_svc._send_notifications.call_args[0]
            events = call_args[1]
            self.assertIn("STOP-LOSS ERREICHT: TSLA", events[0]["line"])


class TestTelegramInteractiveService(unittest.TestCase):
    def setUp(self):
        self.mock_asymmetric = MagicMock()
        self.mock_options = MagicMock()
        self.mock_volume = MagicMock()
        self.mock_regime = MagicMock()
        self.mock_rs = MagicMock()
        self.mock_lifecycle = MagicMock()
        self.mock_signals = MagicMock()
        self.mock_alert = MagicMock()
        self.mock_pm = MagicMock()

        self.service = TelegramInteractiveService(
            bot_token="test_bot_token",
            allowed_chat_ids="999888,12345",
            asymmetric_trade_service=self.mock_asymmetric,
            options_edge_service=self.mock_options,
            volume_profile_service=self.mock_volume,
            market_regime_service=self.mock_regime,
            relative_strength_service=self.mock_rs,
            trade_lifecycle_service=self.mock_lifecycle,
            trading_signals_service=self.mock_signals,
            alert_service=self.mock_alert,
            portfolio_manager=self.mock_pm,
        )

    def test_authorization_security(self):
        # Unauthorized chat ID
        res = self.service.handle_command("666666", "/edge")
        self.assertIn("Zugriff verweigert", res)

        # Authorized chat ID
        self.assertTrue(self.service.is_authorized("999888"))
        self.assertTrue(self.service.is_authorized("12345"))
        self.assertFalse(self.service.is_authorized("11111"))

    def test_cmd_help(self):
        res = self.service.handle_command("999888", "/help")
        self.assertIn("Broker Freund – Interaktiver Trading Edge Bot", res)
        self.assertIn("/edge", res)
        self.assertIn("/gex", res)
        self.assertIn("/levels", res)
        self.assertIn("/regime", res)
        self.assertIn("/rs", res)
        self.assertIn("/track", res)

    def test_cmd_gex(self):
        self.mock_options.analyze_gex.return_value = {
            "spot_price": 130.0,
            "call_wall": 140.0,
            "put_wall": 120.0,
            "zero_gamma": 128.0,
            "net_gex": 450000000.0,
            "regime": "positive_gamma",
            "regime_label": "Positives Gamma (Mean Reversion)",
        }
        res = self.service.handle_command("999888", "/gex NVDA")
        self.assertIn("GAMMA EXPOSURE (GEX): NVDA", res)
        self.assertIn("Positives Gamma", res)
        self.assertIn("Call Wall", res)
        self.assertIn("$140.00", res)
        self.assertIn("$120.00", res)

    def test_cmd_levels(self):
        self.mock_volume.compute_volume_profile.return_value = {
            "spot_price": 220.0,
            "poc_price": 218.0,
            "vah_price": 225.0,
            "val_price": 212.0,
            "location_label": "Im fairen Wertbereich",
            "bias": "Range Trading zwischen VAL und VAH",
        }
        res = self.service.handle_command("999888", "/levels AAPL")
        self.assertIn("VOLUME PROFILE (AMT): AAPL", res)
        self.assertIn("Point of Control (POC)", res)
        self.assertIn("$218.00", res)
        self.assertIn("Value Area High (VAH)", res)
        self.assertIn("$225.00", res)

    def test_cmd_regime(self):
        self.mock_regime.get_market_regime.return_value = {
            "stance": "RISK_ON",
            "vix": {"value": 15.2, "regime": "normal"},
            "spy": {"trend": "bullish", "above_ema20": True},
            "qqq": {"trend": "bullish", "above_ema20": True},
        }
        res = self.service.handle_command("999888", "/regime")
        self.assertIn("MAKRO MARKT-REGIME", res)
        self.assertIn("RISK_ON", res)
        self.assertIn("15.20", res)

    def test_cmd_edge_single_ticker(self):
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "ticker": "NVDA",
            "confluence_score": 88,
            "grade": "A+",
            "telegram_html": "🎯 <b>TRADING EDGE SETUP: NVDA</b> (💎 Grade A+)\nEinstieg: $120.00",
        }
        res = self.service.handle_command("999888", "/edge NVDA")
        self.assertIn("TRADING EDGE SETUP: NVDA", res)
        self.mock_lifecycle.register_trade.assert_called_once()

    def test_cmd_rs(self):
        self.mock_pm.get_signal_watch_items.return_value = [{"kind": "ticker", "value": "NVDA"}]
        self.mock_rs.scan_relative_strength.return_value = [
            {"ticker": "NVDA", "mansfield_rs": 12.0, "alpha_1m": 5.0, "badge": "🔥 Leader", "divergent_strength": True}
        ]
        self.mock_rs.format_telegram_rs_card.return_value = "💪 <b>RELATIVE STÄRKE VS. SPY</b>\n1. NVDA: +12.0% RS"
        res = self.service.handle_command("999888", "/rs")
        self.assertIn("RELATIVE STÄRKE VS. SPY", res)
        self.assertIn("NVDA", res)


if __name__ == "__main__":
    unittest.main()
