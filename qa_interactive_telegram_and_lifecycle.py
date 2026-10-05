"""
QA Test Suite: Interactive 2-Way Telegram Bot, Trade Lifecycle Manager & Relative Strength
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from src.relative_strength_service import RelativeStrengthService
from src.trade_lifecycle_service import TradeLifecycleService
from src.telegram_interactive_service import TelegramInteractiveService
from src.opening_range_breakout_service import OpeningRangeBreakoutService
from src.position_sizing_service import PositionSizingService
from src.market_breadth_service import MarketBreadthService
from src.performance_metrics import calculate_trading_journal_metrics
from src.storage import PortfolioManager
from src.macro_shield_service import MacroShieldService
from src.audio_briefing_service import AudioBriefingService


class TestOpeningRangeBreakoutService(unittest.TestCase):
    def test_compute_orb_breakout(self):
        svc = OpeningRangeBreakoutService()
        with patch("src.opening_range_breakout_service.yf.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker_cls.return_value = mock_ticker
            import pandas as pd
            dates = pd.date_range("2026-10-02 09:30", periods=10, freq="5min")
            df = pd.DataFrame({
                "Open": [100.0, 101.0, 102.0, 101.5, 102.5, 103.0, 104.0, 105.0, 106.0, 107.0],
                "High": [101.0, 102.0, 103.0, 102.5, 103.0, 104.0, 105.0, 106.0, 107.5, 108.0],
                "Low": [99.5, 100.5, 101.0, 100.8, 102.0, 102.5, 103.5, 104.5, 105.5, 106.5],
                "Close": [101.0, 102.0, 102.5, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 107.5],
                "Volume": [10000] * 10
            }, index=dates)
            mock_ticker.history.return_value = df
            res = svc.analyze_orb("NVDA", or_minutes=15)
            self.assertIsNotNone(res)
            self.assertEqual(res["ticker"], "NVDA")
            self.assertEqual(res["state"], "BULLISH_BREAKOUT")
            self.assertGreater(res["spot_price"], res["orb_high"])

    def test_format_telegram_orb_card(self):
        svc = OpeningRangeBreakoutService()
        sample_orb = {
            "ticker": "NVDA",
            "session": "US",
            "or_minutes": 30,
            "currency_symbol": "$",
            "orb_high": 122.50,
            "orb_low": 118.00,
            "orb_mid": 120.25,
            "orb_range": 4.50,
            "orb_range_pct": 3.75,
            "spot_price": 124.00,
            "state": "BULLISH_BREAKOUT",
            "badge": "🚀 BULLISH BREAKOUT",
            "target_1": 127.00,
            "target_2": 131.50,
            "invalidation_stop": 120.25,
            "relative_volume": 1.5,
            "volume_confirmed": True,
        }
        card = svc.format_telegram_orb_card(sample_orb)
        self.assertIn("OPENING RANGE BREAKOUT (ORB): NVDA", card)
        self.assertIn("122.50", card)
        self.assertIn("127.00", card)
        self.assertIn("1.5x", card)


class TestPositionSizingService(unittest.TestCase):
    def test_calculate_sizing_and_kelly(self):
        svc = PositionSizingService()
        res = svc.calculate_sizing(
            ticker="SAP.DE",
            entry_price=200.0,
            stop_price=190.0,
            target_1=220.0,
            target_2=235.0,
            capital=50000.0,
            risk_pct=1.0,
            win_rate=0.55,
        )
        self.assertEqual(res["ticker"], "SAP.DE")
        self.assertEqual(res["recommended_shares"], 50)  # €500 / €10
        self.assertEqual(res["max_risk_amount"], 500.0)
        self.assertEqual(res["currency_symbol"], "€")
        self.assertGreater(res["kelly_analysis"]["half_kelly_pct"], 0)
        self.assertIn("friction_breakdown", res)
        self.assertGreater(res["friction_cost_est"], 0)
        self.assertGreater(res["target_1_profit_net"], 0)


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
        self.patcher = patch("src.trade_lifecycle_service.requests.post")
        self.mock_post = self.patcher.start()
        self.mock_post.return_value.ok = True

    def tearDown(self):
        self.patcher.stop()

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

    def test_stop_proximity_warning(self):
        ticket = {
            "ticker": "TSLA",
            "entry_price": 200.0,
            "invalidation_price": 190.0,
            "target_1": 220.0,
            "target_2": 235.0,
            "risk_per_share": 10.0,
        }
        self.service.register_trade(ticket)

        # Price drops to 191.0 (only 0.52% above stop 190.0)
        with patch.object(self.service, "_fetch_current_price", return_value=191.0):
            eval_res = self.service.evaluate_active_trades(self.mock_alert_svc)
            self.assertEqual(len(eval_res["actions"]), 1)
            self.assertEqual(eval_res["actions"][0]["action"], "STOP_PROXIMITY")

            call_args = self.mock_alert_svc._send_notifications.call_args[0]
            events = call_args[1]
            self.assertIn("STOP-LOSS WARNUNG: TSLA", events[0]["line"])
            self.assertIn("$190.00", events[0]["line"])

    def test_target_1_proximity_alert(self):
        ticket = {
            "ticker": "SAP.DE",
            "entry_price": 210.0,
            "invalidation_price": 202.0,
            "target_1": 225.0,
            "target_2": 235.0,
            "risk_per_share": 8.0,
        }
        self.service.register_trade(ticket)

        # Price rises to 224.0 (only 0.45% below target_1 225.0)
        with patch.object(self.service, "_fetch_current_price", return_value=224.0):
            eval_res = self.service.evaluate_active_trades(self.mock_alert_svc)
            self.assertEqual(len(eval_res["actions"]), 1)
            self.assertEqual(eval_res["actions"][0]["action"], "TARGET_1_PROXIMITY")

            call_args = self.mock_alert_svc._send_notifications.call_args[0]
            events = call_args[1]
            self.assertIn("ZIEL 1 IN REICHWEITE: SAP.DE", events[0]["line"])
            self.assertIn("€225.00", events[0]["line"])


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
        self.mock_heat = MagicMock()
        self.mock_orb = MagicMock()
        self.mock_sizing = MagicMock()
        self.mock_breadth = MagicMock()
        self.mock_macro = MagicMock()
        self.mock_macro.evaluate_macro_shield.return_value = {
            "risk_level": "GREEN_CLEAR",
            "trading_halted": False,
            "badge": "🟢 CLEAR",
            "warning": None,
            "next_catalyst": None,
            "upcoming_catalysts": [],
        }
        self.mock_audio = MagicMock()

        self.service = TelegramInteractiveService(
            bot_token="test_bot_token",
            allowed_chat_ids="999888,12345",
            asymmetric_trade_service=self.mock_asymmetric,
            options_edge_service=self.mock_options,
            volume_profile_service=self.mock_volume,
            market_regime_service=self.mock_regime,
            relative_strength_service=self.mock_rs,
            trade_lifecycle_service=self.mock_lifecycle,
            portfolio_heat_service=self.mock_heat,
            trading_signals_service=self.mock_signals,
            alert_service=self.mock_alert,
            portfolio_manager=self.mock_pm,
            opening_range_breakout_service=self.mock_orb,
            position_sizing_service=self.mock_sizing,
            market_breadth_service=self.mock_breadth,
            macro_shield_service=self.mock_macro,
            audio_briefing_service=self.mock_audio,
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
        self.assertIn("<code>", res)
        self.assertIn("VAH : $ 225.00", res)

    def test_cmd_levels_european_ticker(self):
        self.mock_volume.compute_volume_profile.return_value = {
            "spot_price": 222.50,
            "poc_price": 220.00,
            "vah_price": 225.00,
            "val_price": 215.00,
            "location_label": "Im fairen Wertbereich",
            "bias": "Befestigung",
        }
        res = self.service.handle_command("999888", "/levels SAP.DE")
        self.assertIn("VOLUME PROFILE (AMT): SAP.DE", res)
        self.assertIn("€220.00", res)
        self.assertIn("€225.00", res)
        self.assertIn("<code>", res)
        self.assertIn("VAH : € 225.00", res)

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

    def test_cmd_paper_execution(self):
        self.mock_pm.list_paper_trades.return_value = []
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "ticker": "NVDA",
            "setup_name": "VAH Breakout",
            "entry_price": 120.0,
            "invalidation_price": 114.0,
            "target_1": 132.0,
            "target_2": 141.0,
            "risk_per_share": 6.0,
            "recommended_shares": 25,
            "confluence_score": 85,
            "grade_badge": "💎 Grade A+",
            "risk_reward_ratio": 2.8,
            "total_position_capital": 3000.0,
            "confluence_factors": ["POC Support", "Positives Gamma"],
        }
        res = self.service.handle_command("999888", "/paper NVDA")
        self.assertIn("PAPER TRADE GEBUCHT: NVDA", res)
        self.assertIn("25 Stück", res)
        self.assertIn("$120.00", res)
        self.assertIn("$114.00", res)
        self.assertIn("$132.00", res)
        # Verify trade was created via portfolio_manager
        self.mock_pm.create_paper_trade.assert_called_once()
        # Verify lifecycle registration
        self.mock_lifecycle.register_trade.assert_called()

    def test_inline_keyboard_has_paper_button(self):
        kb = self.service._build_inline_keyboard("NVDA")
        all_buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        paper_btn = next((b for b in all_buttons if b.get("callback_data") == "paper:NVDA"), None)
        self.assertIsNotNone(paper_btn)
        self.assertIn("In Paper Trader buchen", paper_btn["text"])

    def test_paper_callback_query(self):
        self.mock_pm.list_paper_trades.return_value = []
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "ticker": "AAPL",
            "setup_name": "Support Bounce",
            "entry_price": 220.0,
            "invalidation_price": 210.0,
            "target_1": 240.0,
            "target_2": 255.0,
            "risk_per_share": 10.0,
            "recommended_shares": 15,
            "confluence_score": 80,
            "grade_badge": "⭐ Grade A",
            "risk_reward_ratio": 2.5,
            "total_position_capital": 3300.0,
            "confluence_factors": ["VAL Retest"],
        }
        with patch.object(self.service, "send_message") as mock_send, \
             patch.object(self.service, "answer_callback_query") as mock_ans:
            self.service.handle_callback_query("999888", "paper:AAPL", "cq_123")
            mock_ans.assert_called_once()
            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][1]
            self.assertIn("PAPER TRADE GEBUCHT: AAPL", sent_text)

    def test_inline_keyboard_has_be_and_close_buttons(self):
        kb = self.service._build_inline_keyboard("NVDA")
        all_buttons = [btn for row in kb["inline_keyboard"] for btn in row]
        be_btn = next((b for b in all_buttons if b.get("callback_data") == "be:NVDA"), None)
        close_btn = next((b for b in all_buttons if b.get("callback_data") == "close:NVDA"), None)
        scale_btn = next((b for b in all_buttons if b.get("callback_data") == "scale:NVDA:50"), None)
        macro_btn = next((b for b in all_buttons if b.get("callback_data") == "macro:NVDA"), None)
        self.assertIsNotNone(be_btn)
        self.assertIn("Breakeven", be_btn["text"])
        self.assertIsNotNone(close_btn)
        self.assertIn("Schließen", close_btn["text"])
        self.assertIsNotNone(scale_btn)
        self.assertIn("Teilverkauf", scale_btn["text"])
        self.assertIsNotNone(macro_btn)
        self.assertIn("Makro- & FOMC-Shield", macro_btn["text"])

    def test_cmd_macro(self):
        self.mock_macro.evaluate_macro_shield.return_value = {
            "risk_level": "RED_ALERT",
            "trading_halted": True,
            "badge": "🛑 TRADING HALTED",
            "warning": "FOMC Zinsentscheid in 15 Min",
            "next_catalyst": {
                "title": "FOMC Rate Decision",
                "proximity_minutes": 15,
                "date_formatted": "Heute",
                "time_str": "20:00",
            },
            "upcoming_catalysts": [],
        }
        self.mock_macro.format_telegram_macro_card.return_value = "🏛️ <b>HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD</b>"
        res = self.service.handle_command("999888", "/macro NVDA")
        self.assertIn("HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD", res)
        self.mock_macro.evaluate_macro_shield.assert_called_with("NVDA")
        self.mock_macro.format_telegram_macro_card.assert_called_once()

    def test_callback_macro(self):
        self.mock_macro.evaluate_macro_shield.return_value = {
            "risk_level": "GREEN_CLEAR",
            "trading_halted": False,
        }
        self.mock_macro.format_telegram_macro_card.return_value = "🏛️ <b>HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD: AAPL</b>"
        with patch.object(self.service, "send_message") as mock_send, \
             patch.object(self.service, "answer_callback_query") as mock_ans:
            self.service.handle_callback_query("999888", "macro:AAPL", "cq_macro_123")
            mock_ans.assert_called_once()
            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][1]
            self.assertIn("HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD: AAPL", sent_text)

    def test_cmd_macro_alert(self):
        self.mock_macro.check_macro_pre_alerts.return_value = [
            {"text": "🛑 <b>MAKRO-ALARM: TRADING-BLACKOUT IN 15 MINUTEN!</b>", "window": "15m"}
        ]
        res = self.service.handle_command("999888", "/macro alert")
        self.assertIn("MAKRO-ALARM: TRADING-BLACKOUT", res)
        self.mock_macro.check_macro_pre_alerts.assert_called_once()

    def test_cmd_voice(self):
        self.mock_audio.generate_daily_briefing_audio.return_value = (
            b"fake_mp3_bytes",
            "Guten Morgen! Hier ist dein institutionelles Audio-Briefing."
        )
        with patch.object(self.service, "send_voice", return_value=True) as mock_send_v:
            res = self.service.handle_command("999888", "/voice")
            self.assertIn("Audio-Briefing als Sprachnachricht gesendet", res)
            mock_send_v.assert_called_once()
            call_args = mock_send_v.call_args[0]
            self.assertEqual(call_args[0], "999888")
            self.assertEqual(call_args[1], b"fake_mp3_bytes")

    def test_callback_voice(self):
        self.mock_audio.generate_daily_briefing_audio.return_value = (
            b"fake_mp3_bytes",
            "Guten Morgen! Hier ist dein institutionelles Audio-Briefing."
        )
        with patch.object(self.service, "send_voice", return_value=True) as mock_send_v, \
             patch.object(self.service, "send_message") as mock_send_m, \
             patch.object(self.service, "answer_callback_query") as mock_ans:
            self.service.handle_callback_query("999888", "voice:today", "cq_v123")
            mock_ans.assert_called_once()
            mock_send_v.assert_called_once()
            mock_send_m.assert_called_once()
            self.assertIn("Audio-Briefing als Sprachnachricht gesendet", mock_send_m.call_args[0][1])

    def test_cmd_watch_and_unwatch(self):
        res_watch = self.service.handle_command("999888", "/watch SAP.DE")
        self.assertIn("Watchlist aktualisiert", res_watch)
        self.assertIn("SAP.DE", res_watch)
        self.mock_pm.add_signal_watch_item.assert_called_with("ticker", "SAP.DE")

        res_unwatch = self.service.handle_command("999888", "/unwatch SAP.DE")
        self.assertIn("Watchlist aktualisiert", res_unwatch)
        self.assertIn("SAP.DE", res_unwatch)
        self.mock_pm.remove_signal_watch_item.assert_called_with("ticker", "SAP.DE")

    def test_cmd_watchlist_categorization(self):
        self.mock_pm.get_signal_watch_items.return_value = [
            {"kind": "ticker", "value": "SAP.DE"},
            {"kind": "ticker", "value": "RHM.DE"},
            {"kind": "ticker", "value": "NVDA"},
        ]
        res = self.service.handle_command("999888", "/watchlist")
        self.assertIn("SIGNAL-WATCHLIST (3 Titel)", res)
        self.assertIn("Europa / DAX Leaders:", res)
        self.assertIn("SAP.DE", res)
        self.assertIn("RHM.DE", res)
        self.assertIn("US & International Leaders:", res)
        self.assertIn("NVDA", res)

    def test_cmd_close_paper_trade(self):
        self.mock_pm.list_paper_trades.return_value = [
            {
                "id": "trade_xyz",
                "ticker": "NVDA",
                "status": "open",
                "entry_price": 120.0,
                "current_price": 130.0,
                "quantity": 10,
            }
        ]
        self.mock_lifecycle._fetch_current_price.return_value = 130.0
        self.mock_lifecycle.get_active_trades.return_value = [
            {"ticker": "NVDA", "status": "OPEN", "entry_price": 120.0}
        ]

        res = self.service.handle_command("999888", "/close NVDA")
        self.assertIn("POSITION GESCHLOSSEN: NVDA", res)
        self.assertIn("+$100.00", res)
        self.assertIn("Reibung (Spread &amp; Slippage)", res)
        self.assertIn("+$99.00", res)

    def test_cmd_be_stop(self):
        self.mock_lifecycle.get_active_trades.return_value = [
            {"ticker": "NVDA", "status": "OPEN", "entry_price": 120.0, "trailing_stop": 114.0}
        ]
        res = self.service.handle_command("999888", "/be NVDA")
        self.assertIn("STOP-LOSS AUF BREAKEVEN: NVDA", res)
        self.assertIn("$120.00", res)
        self.assertIn("Risikofreier Trade", res)

    def test_cmd_brief_on_demand(self):
        self.mock_alert.send_session_brief_now.return_value = {"status": "ok"}
        res = self.service.handle_command("999888", "/brief europe")
        self.assertIn("Europa / DAX Open Briefing", res)
        self.assertIn("erfolgreich generiert", res)
        self.mock_alert.send_session_brief_now.assert_called_with("europe")

    def test_cmd_depot_status(self):
        self.mock_pm.list_paper_trades.return_value = [
            {"ticker": "NVDA", "status": "open", "entry_price": 120.0, "quantity": 10},
            {"ticker": "SAP.DE", "status": "closed", "entry_price": 180.0, "realized_pnl": 250.0},
        ]
        mock_paper = MagicMock()
        mock_paper.build_demo_account_snapshot.return_value = {
            "equity": 52500.0,
            "cash": 45000.0,
            "starting_capital": 50000.0,
        }
        self.service.paper_service = mock_paper
        res = self.service.handle_command("999888", "/depot")
        self.assertIn("PAPER DEPOT STATUS", res)
        self.assertIn("52,500.00 EUR", res)
        self.assertIn("+2,500.00 EUR", res)
        self.assertIn("NVDA", res)

    def test_cmd_calendar(self):
        mock_brief_svc = MagicMock()
        mock_brief_svc.get_brief_fast.return_value = {
            "economic_calendar": [
                {"time": "14:30", "title": "US Non-Farm Payrolls", "importance": "high"}
            ],
            "earnings_calendar": [
                {"ticker": "NVDA", "company": "NVIDIA Corp", "date": "2026-11-20", "days_until": 20, "session": "after-hours"}
            ],
        }
        self.service.morning_brief_service = mock_brief_svc
        res = self.service.handle_command("999888", "/calendar")
        self.assertIn("WIRTSCHAFTS- & EARNINGS-KALENDER", res)
        self.assertIn("US Non-Farm Payrolls", res)
        self.assertIn("NVDA", res)
        self.assertIn("Earnings Shield", res)

    def test_cmd_news(self):
        mock_brief_svc = MagicMock()
        mock_social = MagicMock()
        mock_social.get_google_news.return_value = [
            {"title": "SAP kündigt neues KI-Produkt an", "source": "Handelsblatt", "age_hours": 2}
        ]
        mock_brief_svc._social_service = mock_social
        self.service.morning_brief_service = mock_brief_svc
        res = self.service.handle_command("999888", "/news SAP.DE")
        self.assertIn("TOP-NEWS: SAP.DE", res)
        self.assertIn("SAP kündigt neues KI-Produkt an", res)
        self.assertIn("Handelsblatt", res)

    def test_cmd_journal(self):
        self.mock_pm.list_paper_trades.return_value = [
            {
                "ticker": "SAP.DE",
                "entry_price": 200.0,
                "closed_price": 220.0,
                "quantity": 10,
                "status": "closed",
                "closed_at": "2026-10-01T15:30:00",
                "exit_reason": "Target 1 Hit",
            },
            {
                "ticker": "NVDA",
                "entry_price": 120.0,
                "closed_price": 115.0,
                "quantity": 20,
                "status": "closed",
                "closed_at": "2026-10-01T16:00:00",
                "exit_reason": "Stop Loss Hit",
            },
        ]
        res = self.service.handle_command("999888", "/journal")
        self.assertIn("TRADING JOURNAL", res)
        self.assertIn("SAP.DE", res)
        self.assertIn("+€200.00", res)
        self.assertIn("NVDA", res)
        self.assertIn("-$100.00", res)
        self.assertIn("Win-Rate: <b>50%</b>", res)

    def test_cmd_sizing(self):
        self.service.sizing_service = None
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "entry_price": 200.0,
            "invalidation_price": 190.0,
            "target_1": 220.0,
            "target_2": 235.0,
            "risk_per_share": 10.0,
        }
        res = self.service.handle_command("999888", "/sizing SAP.DE 50000")
        self.assertIn("POSITION SIZING RECHNER: SAP.DE", res)
        self.assertIn("50,000 €", res)
        self.assertIn("€200.00", res)
        self.assertIn("€190.00", res)
        self.assertIn("Konservativ (1.0% Risiko = -500 €)", res)
        self.assertIn("50 Aktien", res)
        self.assertIn("Standard (1.5% Risiko = -750 €)", res)
        self.assertIn("75 Aktien", res)

    def test_cmd_sizing_with_service(self):
        self.service.sizing_service = self.mock_sizing
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "entry_price": 200.0,
            "invalidation_price": 190.0,
            "target_1": 220.0,
            "target_2": 235.0,
            "risk_per_share": 10.0,
        }
        self.mock_sizing.format_telegram_sizing_card.return_value = "⚖️ <b>POSITION SIZING &amp; KELLY-RECHNER: SAP.DE</b>"
        res = self.service.handle_command("999888", "/sizing SAP.DE 50000")
        self.assertIn("POSITION SIZING &amp; KELLY-RECHNER: SAP.DE", res)
        self.mock_sizing.calculate_sizing.assert_called_once()

    def test_cmd_recap(self):
        self.mock_regime.get_market_regime.return_value = {
            "stance": "RISK_ON",
            "vix": {"value": 14.8},
        }
        res = self.service.handle_command("999888", "/recap")
        self.assertIn("SESSION-RECAP", res)
        self.assertIn("RISK_ON", res)
        self.assertIn("14.80", res)
        self.assertIn("Schnellzugriff", res)

    def test_cmd_check(self):
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "entry_price": 215.0,
            "invalidation_price": 208.0,
            "target_1": 229.0,
            "target_2": 242.0,
            "confluence_score": 82,
            "grade_badge": "⭐ Grade A",
            "volume_profile": {"market_location": "inside_value_area"},
            "relative_strength": {"mansfield_rs": 4.5},
            "options_gex": {"regime": "positive_gamma"},
        }
        res = self.service.handle_command("999888", "/check SAP.DE")
        self.assertIn("360° INSTITUTIONAL CHECK: SAP.DE", res)
        self.assertIn("€215.00", res)
        self.assertIn("82/100", res)
        self.assertIn("Positives Gamma", res)
        self.assertIn("Stärker als SPY", res)

    def test_cmd_check_with_macro_shield(self):
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "entry_price": 215.0,
            "invalidation_price": 208.0,
            "target_1": 229.0,
            "target_2": 242.0,
            "confluence_score": 82,
            "grade_badge": "⭐ Grade A",
            "volume_profile": {"market_location": "inside_value_area"},
            "relative_strength": {"mansfield_rs": 4.5},
            "options_gex": {"regime": "positive_gamma"},
        }
        self.mock_macro.evaluate_macro_shield.return_value = {
            "risk_level": "RED_ALERT",
            "trading_halted": True,
            "badge": "🛑 TRADING HALTED",
            "warning": "FOMC Zinsentscheid in 20m!",
            "next_catalyst": {"title": "FOMC Rate Decision", "proximity_minutes": 20},
        }
        res = self.service.handle_command("999888", "/check SAP.DE")
        self.assertIn("360° INSTITUTIONAL CHECK: SAP.DE", res)
        self.assertIn("Makro- &amp; FOMC-Shield:", res)
        self.assertIn("🛑 TRADING HALTED", res)
        self.assertIn("FOMC Zinsentscheid in 20m!", res)

    def test_cmd_stop(self):
        self.mock_asymmetric.generate_trade_setup.return_value = {
            "entry_price": 120.0,
            "invalidation_price": 114.0,
            "volume_profile": {"val": 115.0},
            "options_gex": {"put_wall": 110.0},
        }
        res = self.service.handle_command("999888", "/stop NVDA")
        self.assertIn("STRUKTURELLE STOP-LOSS LEVEL: NVDA", res)
        self.assertIn("$120.00", res)
        self.assertIn("$114.00", res)
        self.assertIn("$115.00", res)
        self.assertIn("$110.00", res)

    def test_cmd_scan_combined_radar(self):
        self.mock_pm.get_signal_watch_items.return_value = [
            {"kind": "ticker", "value": "NVDA"},
            {"kind": "ticker", "value": "SAP.DE"},
        ]
        self.mock_signals.scan_and_dispatch_edge_alerts.return_value = {
            "scanned_count": 2,
            "dispatched": ["NVDA"],
            "deduplicated": ["SAP.DE"],
        }
        self.mock_signals.scan_combined_fvg_and_volume_retests.return_value = {
            "scanned_count": 2,
            "confluence_matches": [
                {
                    "ticker": "NVDA",
                    "vp": {"description": "Testet Point of Control ($118.50)"},
                    "fvg": {"description": "Demand-Zone $118.00–$119.50 (UNMITIGATED)"},
                    "spot": 118.80,
                }
            ],
            "volume_profile_matches": [
                {
                    "ticker": "SAP.DE",
                    "type": "POC Retest",
                    "description": "Testet Point of Control (€214.20)",
                    "dist_pct": 0.4,
                }
            ],
            "fvg_matches": [
                {
                    "ticker": "NVDA",
                    "type": "Bullish FVG (Demand Support)",
                    "description": "Demand-Zone $118.00–$119.50 (UNMITIGATED)",
                }
            ],
        }

        res = self.service.handle_command("999888", "/scan")
        self.assertIn("KOMBINIERTER MULTI-ASSET RADAR", res)
        self.assertIn("DOPPEL-KONFLUENZ", res)
        self.assertIn("NVDA", res)
        self.assertIn("SAP.DE", res)
        self.assertIn("POC Retest", res)
        self.assertIn("Demand-Zone", res)
        self.assertIn("Neu gepusht:</b> NVDA", res)

    def test_cmd_preflight_clear(self):
        self.mock_lifecycle.get_active_trades.return_value = []
        self.mock_heat.evaluate_portfolio_heat.return_value = {
            "portfolio_heat_pct": 0.5,
            "max_portfolio_heat_pct": 2.5,
        }
        res = self.service.handle_command("999888", "/preflight NVDA")
        self.assertIn("PRE-FLIGHT RISIKO-CHECK: NVDA", res)
        self.assertIn("FREIGABE ERTEILT (CLEAR)", res)
        self.assertIn("Aktuelle Heat: <b>0.50%</b>", res)
        self.assertIn("Trade-Risiko: <b>+0.75%</b>", res)

    def test_cmd_preflight_cluster_risk(self):
        self.mock_lifecycle.get_active_trades.return_value = [
            {"ticker": "MSFT", "status": "OPEN"}
        ]
        self.mock_heat.evaluate_portfolio_heat.return_value = {
            "portfolio_heat_pct": 1.2,
            "max_portfolio_heat_pct": 2.5,
        }
        self.mock_heat.compute_correlation_matrix.return_value = {
            "matrix": {
                "NVDA": {"MSFT": 0.82},
                "MSFT": {"NVDA": 0.82},
            }
        }
        res = self.service.handle_command("999888", "/preflight NVDA")
        self.assertIn("PRE-FLIGHT RISIKO-CHECK: NVDA", res)
        self.assertIn("ERHÖHTES CLUSTER-RISIKO", res)
        self.assertIn("Korrelation r=0.82 mit offener Position <b>MSFT</b>", res)

    def test_cmd_orb_single_ticker(self):
        self.mock_orb.analyze_orb.return_value = {
            "ticker": "NVDA",
            "session": "US",
            "or_minutes": 30,
            "currency_symbol": "$",
            "orb_high": 122.50,
            "orb_low": 118.00,
            "orb_mid": 120.25,
            "orb_range": 4.50,
            "orb_range_pct": 3.75,
            "spot_price": 124.00,
            "state": "BULLISH_BREAKOUT",
            "badge": "🚀 BULLISH BREAKOUT",
            "target_1": 127.00,
            "target_2": 131.50,
            "invalidation_stop": 120.25,
            "relative_volume": 1.5,
            "volume_confirmed": True,
        }
        self.mock_orb.format_telegram_orb_card.return_value = "⚡ <b>OPENING RANGE BREAKOUT (ORB): NVDA</b>\nStatus: BULLISH BREAKOUT"
        res = self.service.handle_command("999888", "/orb NVDA 30")
        self.assertIn("OPENING RANGE BREAKOUT (ORB): NVDA", res)
        self.mock_orb.analyze_orb.assert_called_with("NVDA", or_minutes=30)

    def test_cmd_orb_scan(self):
        self.mock_pm.get_signal_watch_items.return_value = [
            {"kind": "ticker", "value": "NVDA"},
            {"kind": "ticker", "value": "SAP.DE"},
        ]
        self.mock_orb.scan_watchlist_orb.return_value = {
            "scanned_count": 2,
            "or_minutes": 30,
            "breakouts_count": 1,
            "breakdowns_count": 0,
            "breakouts": [
                {
                    "ticker": "NVDA",
                    "state": "BULLISH_BREAKOUT",
                    "spot_price": 124.0,
                    "orb_high": 122.5,
                    "orb_low": 118.0,
                    "target_1": 127.0,
                    "relative_volume": 1.6,
                    "currency_symbol": "$",
                }
            ],
            "breakdowns": [],
            "inside_range_count": 1,
        }
        self.mock_orb.format_telegram_orb_scan_summary.return_value = "⚡ <b>ORB SCANNER REPORT (30M)</b>\nBreakouts gefunden:\n1. NVDA"
        res = self.service.handle_command("999888", "/orb")
        self.assertIn("ORB SCANNER REPORT (30M)", res)

    def test_cmd_recap_sessions(self):
        self.mock_regime.get_market_regime.return_value = {
            "stance": "RISK_ON",
            "vix": {"value": 14.5},
        }
        res_xetra = self.service.handle_command("999888", "/recap xetra")
        self.assertIn("XETRA SESSION CLOSE RECAP", res_xetra)

        res_us = self.service.handle_command("999888", "/recap us")
        self.assertIn("WALL STREET SESSION CLOSE RECAP", res_us)

    def test_callback_orb(self):
        self.mock_orb.analyze_orb.return_value = {
            "ticker": "NVDA",
            "state": "INSIDE_RANGE",
        }
        self.mock_orb.format_telegram_orb_card.return_value = "⚡ <b>OPENING RANGE BREAKOUT: NVDA</b>"
        with patch.object(self.service, "send_message") as mock_send, \
             patch.object(self.service, "answer_callback_query") as mock_ans:
            self.service.handle_callback_query("999888", "orb:NVDA", "cq_orb_1")
            mock_ans.assert_called_once()
            mock_send.assert_called_once()
            self.assertIn("OPENING RANGE BREAKOUT: NVDA", mock_send.call_args[0][1])

    def test_cmd_scale(self):
        self.mock_pm.list_paper_trades.return_value = [
            {"id": "trade_scale_1", "ticker": "NVDA", "status": "open", "quantity": 10, "entry_price": 120.0}
        ]
        self.mock_pm.partial_close_paper_trade.return_value = {
            "id": "trade_scale_1",
            "ticker": "NVDA",
            "status": "open",
            "quantity": 5,
            "closed_quantity": 5,
            "closed_slice_pnl": 50.0,
            "trailing_stop": 120.0,
            "entry_price": 120.0,
        }
        self.mock_lifecycle._fetch_current_price.return_value = 130.0
        self.mock_lifecycle.get_active_trades.return_value = [
            {"ticker": "NVDA", "entry_price": 120.0, "status": "OPEN", "trailing_stop": 115.0}
        ]

        res = self.service.handle_command("999888", "/scale NVDA 50")
        self.assertIn("TEILVERKAUF (50% SCALE-OUT): NVDA", res)
        self.assertIn("+$50.00", res)
        self.assertIn("Risikofreier Free-Trade", res)
        self.mock_pm.partial_close_paper_trade.assert_called_once()
        self.mock_lifecycle._save_trades.assert_called_once()
        self.assertEqual(self.mock_lifecycle.get_active_trades.return_value[0]["trailing_stop"], 120.0)

    def test_callback_scale(self):
        self.mock_pm.list_paper_trades.return_value = [
            {"id": "trade_scale_1", "ticker": "NVDA", "status": "open", "quantity": 10, "entry_price": 120.0}
        ]
        self.mock_pm.partial_close_paper_trade.return_value = {
            "id": "trade_scale_1",
            "ticker": "NVDA",
            "status": "open",
            "quantity": 5,
            "closed_quantity": 5,
            "closed_slice_pnl": 50.0,
            "trailing_stop": 120.0,
            "entry_price": 120.0,
        }
        self.mock_lifecycle._fetch_current_price.return_value = 130.0
        with patch.object(self.service, "send_message") as mock_send, \
             patch.object(self.service, "answer_callback_query") as mock_ans:
            self.service.handle_callback_query("999888", "scale:NVDA:50", "cq_scale_1")
            mock_ans.assert_called_once()
            mock_send.assert_called_once()
            self.assertIn("TEILVERKAUF (50% SCALE-OUT)", mock_send.call_args[0][1])

    def test_cmd_breadth(self):
        self.mock_breadth.compute_market_breadth.return_value = {
            "scanned_count": 18,
            "advancing_count": 12,
            "declining_count": 6,
            "ad_ratio": 2.0,
            "pct_above_20_ema": 66.7,
            "pct_above_50_sma": 72.2,
            "pct_above_200_sma": 83.3,
            "composite_score": 75,
            "regime": "BULLISH_EXPANSION",
            "status_badge": "🟢 Marktbreite Bullish (Score: 75/100)",
        }
        self.mock_breadth.format_telegram_breadth_card.return_value = "📊 <b>INSTITUTIONELLE MARKTBREITE &amp; INTERNALS</b>\nScore: 75/100"
        res = self.service.handle_command("999888", "/breadth")
        self.assertIn("INSTITUTIONELLE MARKTBREITE", res)
        self.mock_breadth.compute_market_breadth.assert_called_once()

    def test_callback_breadth(self):
        self.mock_breadth.compute_market_breadth.return_value = {"composite_score": 75}
        self.mock_breadth.format_telegram_breadth_card.return_value = "📊 <b>MARKTBREITE REPORT</b>"
        with patch.object(self.service, "send_message") as mock_send, \
             patch.object(self.service, "answer_callback_query") as mock_ans:
            self.service.handle_callback_query("999888", "breadth", "cq_breadth_1")
            mock_ans.assert_called_once()
            mock_send.assert_called_once()
            self.assertIn("MARKTBREITE REPORT", mock_send.call_args[0][1])


class TestMarketBreadthService(unittest.TestCase):
    def test_format_telegram_breadth_card(self):
        svc = MarketBreadthService()
        sample = {
            "scanned_count": 18,
            "advancing_count": 12,
            "declining_count": 6,
            "ad_ratio": 2.0,
            "pct_above_20_ema": 66.7,
            "pct_above_50_sma": 72.2,
            "pct_above_200_sma": 83.3,
            "avg_distance_to_52w_high_pct": -4.2,
            "avg_distance_to_52w_low_pct": 28.5,
            "composite_score": 75,
            "regime": "BULLISH_EXPANSION",
            "status_badge": "🟢 Marktbreite Bullish (Score: 75/100)",
            "constituents": [
                {"ticker": "NVDA", "change_pct": 2.5, "above_20_ema": True, "above_50_sma": True, "above_200_sma": True},
                {"ticker": "SAP.DE", "change_pct": 1.2, "above_20_ema": True, "above_50_sma": True, "above_200_sma": True},
            ]
        }
        card = svc.format_telegram_breadth_card(sample)
        self.assertIn("MARKTBREITE &amp; INTERNALS", card)
        self.assertIn("BULLISH_EXPANSION", card)
        self.assertIn("66.7%", card)
        self.assertIn("72.2%", card)
        self.assertIn("83.3%", card)


class TestTradingJournalMetrics(unittest.TestCase):
    def test_calculate_trading_journal_metrics(self):
        sample_trades = [
            {
                "id": "t1",
                "ticker": "NVDA",
                "status": "closed",
                "entry_price": 100.0,
                "closed_price": 120.0,
                "quantity": 10,
                "closed_at": "2026-10-01T12:00:00Z",
            },
            {
                "id": "t2",
                "ticker": "SAP.DE",
                "status": "closed",
                "entry_price": 200.0,
                "closed_price": 190.0,
                "quantity": 10,
                "closed_at": "2026-10-02T12:00:00Z",
            },
        ]
        metrics = calculate_trading_journal_metrics(sample_trades, starting_capital=50000.0)
        self.assertEqual(metrics["total_closed_trades"], 2)
        self.assertEqual(metrics["wins"], 1)
        self.assertEqual(metrics["losses"], 1)
        self.assertEqual(metrics["win_rate"], 50.0)
        self.assertGreater(metrics["expectancy_eur"], 0)
        self.assertGreater(metrics["profit_factor"], 1.0)
        self.assertEqual(len(metrics["equity_curve"]), 3)


class TestPortfolioManagerScaleOut(unittest.TestCase):
    def test_partial_close_paper_trade(self):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with patch("src.storage.DB_PATH", tmp_path):
                from src.storage import init_db
                init_db()
                pm = PortfolioManager()
                trade = pm.create_paper_trade({
                    "ticker": "NVDA",
                    "entry_price": 100.0,
                    "stop_price": 90.0,
                    "target_price": 120.0,
                    "quantity": 10,
                    "setup_type": "Test Setup",
                    "status": "open",
                })
                self.assertIsNotNone(trade)

                # Scale out 50%
                scaled = pm.partial_close_paper_trade(
                    trade_id_or_ticker="NVDA",
                    closed_price=110.0,
                    fraction=0.50,
                    notes="50% Scale-Out Test",
                )
                self.assertIsNotNone(scaled)
                self.assertEqual(scaled["quantity"], 5)
                self.assertEqual(scaled["trailing_stop"], 100.0)
                self.assertEqual(scaled["closed_quantity"], 5)

                # Check that a closed trade record was inserted
                all_trades = pm.list_paper_trades(limit=10)
                closed_trades = [t for t in all_trades if t.get("status") == "closed"]
                self.assertEqual(len(closed_trades), 1)
                self.assertEqual(closed_trades[0]["quantity"], 5)
                self.assertEqual(closed_trades[0]["closed_price"], 110.0)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass



class TestMacroShieldService(unittest.TestCase):
    def setUp(self):
        self.svc = MacroShieldService()

    def test_get_upcoming_catalysts(self):
        cats = self.svc.get_upcoming_catalysts(days_ahead=30)
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0)
        first = cats[0]
        self.assertIn("title", first)
        self.assertIn("category", first)
        self.assertIn("proximity_minutes", first)
        self.assertIn("affected_assets", first)
        self.assertIsInstance(first["proximity_minutes"], int)

    def test_evaluate_macro_shield_structure(self):
        res = self.svc.evaluate_macro_shield("NVDA")
        self.assertIn("risk_level", res)
        self.assertIn("trading_halted", res)
        self.assertIn("badge", res)
        self.assertIn("safe", res)
        self.assertIn("upcoming_catalysts", res)

    def test_evaluate_macro_shield_red_alert_window(self):
        from datetime import datetime, timezone, timedelta
        now_utc = datetime.now(timezone.utc)
        # Mock catalyst 15 minutes ahead
        fake_cat = {
            "title": "FOMC Rate Decision",
            "category": "CENTRAL_BANK",
            "region": "US",
            "impact": "HIGH",
            "datetime_utc": now_utc + timedelta(minutes=15),
            "affected_assets": ["NVDA", "SPY"],
            "minutes_until": 15,
            "proximity_minutes": 15,
        }
        with patch.object(self.svc, "get_upcoming_catalysts", return_value=[
            {
                **fake_cat,
                "date_formatted": "Heute",
                "time_str": "20:00",
            }
        ]):
            res = self.svc.evaluate_macro_shield("NVDA")
            self.assertEqual(res["risk_level"], "RED_ALERT")
            self.assertTrue(res["trading_halted"])
            self.assertFalse(res["safe"])
            self.assertIn("🔴", res["badge"])
            self.assertIn("FOMC Rate Decision", res["warning"])

    def test_evaluate_macro_shield_yellow_caution_window(self):
        from datetime import datetime, timezone, timedelta
        now_utc = datetime.now(timezone.utc)
        fake_cat = {
            "title": "US CPI Inflation",
            "category": "INFLATION",
            "region": "US",
            "impact": "HIGH",
            "datetime_utc": now_utc + timedelta(minutes=75),
            "affected_assets": ["NVDA", "SPY"],
            "minutes_until": 75,
            "proximity_minutes": 75,
        }
        with patch.object(self.svc, "get_upcoming_catalysts", return_value=[
            {
                **fake_cat,
                "date_formatted": "Heute",
                "time_str": "14:30",
            }
        ]):
            res = self.svc.evaluate_macro_shield("NVDA")
            self.assertEqual(res["risk_level"], "YELLOW_CAUTION")
            self.assertFalse(res["trading_halted"])
            self.assertFalse(res["safe"])
            self.assertIn("⚠️", res["badge"])

    def test_format_telegram_macro_card(self):
        sample_report = {
            "ticker": "SAP.DE",
            "risk_level": "RED_ALERT",
            "trading_halted": True,
            "badge": "🛑 TRADING HALTED",
            "warning": "EZB Zinsentscheid in 25 Min!",
            "next_catalyst": {
                "title": "EZB Zinsentscheid",
                "proximity_minutes": 25,
                "date_formatted": "Heute",
                "time_str": "14:15",
                "region": "EU",
                "category": "CENTRAL_BANK",
            },
            "upcoming_catalysts": [
                {
                    "title": "EZB Zinsentscheid",
                    "proximity_minutes": 25,
                    "date_formatted": "Heute",
                    "time_str": "14:15",
                    "region": "EU",
                    "category": "CENTRAL_BANK",
                    "affected_assets": ["SAP.DE", "DAX"],
                }
            ],
        }
        card = self.svc.format_telegram_macro_card(sample_report)
        self.assertIn("HIGH-IMPACT MAKRO- &amp; NOTENBANK-SHIELD: SAP.DE", card)
        self.assertIn("TRADING HALTED", card)
        self.assertIn("EZB Zinsentscheid", card)
        self.assertIn("in 25 Min", card)

    def test_check_macro_pre_alerts(self):
        with patch.object(self.svc, "get_upcoming_catalysts", return_value=[
            {
                "id": "fomc_decision",
                "title": "FOMC Rate Decision",
                "category": "CENTRAL_BANK",
                "region": "US",
                "impact": "CRITICAL",
                "time_str": "20:00",
                "minutes_until": 12,
                "affected_assets": ["SPY", "NVDA"],
                "flag": "🏛️",
            },
            {
                "id": "us_cpi",
                "title": "US CPI Inflation",
                "category": "INFLATION",
                "region": "US",
                "impact": "HIGH",
                "time_str": "14:30",
                "minutes_until": 55,
                "affected_assets": ["SPY"],
                "flag": "📈",
            }
        ]):
            open_trades = [{"ticker": "NVDA", "status": "open"}]
            alerts = self.svc.check_macro_pre_alerts(open_trades=open_trades)
            self.assertEqual(len(alerts), 2)

            al_15 = next(a for a in alerts if a["window"] == "15m")
            self.assertTrue(al_15["trading_halted"])
            self.assertIn("TRADING-BLACKOUT IN 12 MINUTEN", al_15["text"])
            self.assertIn("NVDA", al_15["affected_tickers"])

            al_60 = next(a for a in alerts if a["window"] == "60m")
            self.assertFalse(al_60["trading_halted"])
            self.assertIn("MAKRO-VORWARNUNG", al_60["text"])


class TestAudioBriefingService(unittest.TestCase):
    def setUp(self):
        self.svc = AudioBriefingService()

    def test_clean_for_speech(self):
        raw = "<b>SAP.DE</b> &amp; NVDA +12% mit R:R 3:1"
        cleaned = self.svc._clean_for_speech(raw)
        self.assertIn("S A P", cleaned)
        self.assertIn("Nvidia", cleaned)
        self.assertIn("Chance-Risiko-Verhältnis", cleaned)
        self.assertNotIn("<b>", cleaned)
        self.assertNotIn("&amp;", cleaned)

    def test_build_spoken_script(self):
        brief_data = {
            "market_regime": {"stance": "RISK_ON", "vix": {"value": 15.2}},
            "economic_calendar": [{"title": "FOMC Rate Decision", "time": "20:00"}],
            "trade_ideas": [{"ticker": "NVDA", "setup_name": "VAH Breakout"}],
        }
        script = self.svc.build_spoken_script(brief_data)
        self.assertIn("Guten Morgen!", script)
        self.assertIn("Risk-On", script)
        self.assertIn("15.2", script)
        self.assertIn("Nvidia", script)
        self.assertIn("F O M C", script)

    def test_generate_audio_mp3(self):
        audio_bytes = self.svc.generate_audio_mp3("Test Audio Briefing.")
        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 1000)

    def test_telegram_preformatted_html_not_escaped(self):
        from src.email_alert_service import EmailAlertService
        alert_svc = EmailAlertService(MagicMock(), MagicMock())
        cfg = MagicMock()
        cfg.telegram_enabled = True
        cfg.telegram_bot_token = "123:ABC"
        cfg.telegram_chat_id = "999"
        sent_messages = []
        alert_svc._tg_post = lambda token, chat, text: sent_messages.append(text)

        event = {"category": "session_recap", "line": "🇪🇺 <b>XETRA CLOSE RECAP</b>\n• <code>/movers</code>"}
        alert_svc._send_telegram(cfg, [event], "Recap")

        self.assertEqual(len(sent_messages), 1)
        self.assertIn("<b>XETRA CLOSE RECAP</b>", sent_messages[0])
        self.assertNotIn("&lt;b&gt;", sent_messages[0])
        self.assertIn("<code>/movers</code>", sent_messages[0])


class TestQualityCompounderService(unittest.TestCase):
    def setUp(self):
        from src.quality_compounder_service import QualityCompounderService
        self.service = QualityCompounderService()

    def test_calculate_piotroski_score(self):
        res = self.service.calculate_piotroski_score("NVDA")
        self.assertIn("score", res)
        self.assertGreaterEqual(res["score"], 7)
        self.assertEqual(res["max_score"], 9)
        self.assertIn("checks", res)

    def test_calculate_roic_metrics(self):
        res = self.service.calculate_roic_metrics("NVDA")
        self.assertGreater(res["roic_pct"], 20.0)
        self.assertTrue(res["is_value_creator"])
        self.assertIn("MOAT", res["moat_rating"])

    def test_calculate_altman_z_score(self):
        res = self.service.calculate_altman_z_score("NVDA")
        self.assertGreater(res["z_score"], 2.99)
        self.assertTrue(res["is_safe"])

    def test_analyze_compounder(self):
        analysis = self.service.analyze_compounder("MSFT")
        self.assertEqual(analysis["ticker"], "MSFT")
        self.assertGreaterEqual(analysis["compounder_score"], 75.0)
        self.assertIn("classification", analysis)

    def test_telegram_compounder_commands(self):
        from src.telegram_interactive_service import TelegramInteractiveService
        bot = TelegramInteractiveService(
            bot_token="fake_token",
            allowed_chat_ids="12345",
            quality_compounder_service=self.service,
        )
        res_top = bot.handle_command("12345", "/compounder top")
        self.assertIn("INSTITUTIONAL COMPOUNDER SCREENER", res_top)
        self.assertIn("NVDA", res_top)

        res_single = bot.handle_command("12345", "/compounder NVDA")
        self.assertIn("COMPOUNDER RADAR: NVDA", res_single)
        self.assertIn("Piotroski F-Score", res_single)
        self.assertIn("ROIC vs. WACC", res_single)

    def test_telegram_superinvestor_and_psychology_commands(self):
        from src.telegram_interactive_service import TelegramInteractiveService
        bot = TelegramInteractiveService(
            bot_token="fake_token",
            allowed_chat_ids="12345",
            quality_compounder_service=self.service,
        )
        # Test /13f general overview
        res_13f = bot.handle_command("12345", "/13f")
        self.assertIn("13F SUPERINVESTOR PORTFOLIO RADAR", res_13f)
        self.assertIn("Warren Buffett", res_13f)

        # Test /13f specific ticker
        res_ticker = bot.handle_command("12345", "/13f NVDA")
        self.assertIn("13F SUPERINVESTOR BACKING: NVDA", res_ticker)
        self.assertIn("Stanley Druckenmiller", res_ticker)

        # Test /psychology tilt shield
        res_psy = bot.handle_command("12345", "/psychology")
        self.assertIn("TRADING PSYCHOLOGY &amp; TILT SHIELD", res_psy)
        self.assertIn("Mentaler Status", res_psy)
        self.assertIn("Die 4 Goldenen Psychologie-Gesetze", res_psy)

        # Test /routine executive pre-market checklist
        res_routine = bot.handle_command("12345", "/routine")
        self.assertIn("DAILY EXECUTIVE TRADING ROUTINE", res_routine)
        self.assertIn("Makro-Shield Check", res_routine)
        self.assertIn("Eisernes Risikobudget heute", res_routine)

        # Test /leaps calculation
        res_leaps = bot.handle_command("12345", "/leaps NVDA")
        self.assertIn("LEAPS ASYMMETRIE-RECHNER: NVDA", res_leaps)
        self.assertIn("Empfohlener Strike", res_leaps)
        self.assertIn("Effektiver Hebel", res_leaps)


class TestAsymmetricOptionsLeapsService(unittest.TestCase):
    def setUp(self):
        from src.asymmetric_options_leaps_service import AsymmetricOptionsLeapsService
        self.service = AsymmetricOptionsLeapsService()

    def test_calculate_leaps_strategy(self):
        res = self.service.calculate_leaps_strategy("NVDA", spot_price=135.0)
        self.assertEqual(res["ticker"], "NVDA")
        self.assertGreater(res["delta"], 0.70)
        self.assertGreater(res["effective_leverage"], 2.0)
        self.assertGreater(res["capital_saved_pct"], 50.0)
        self.assertEqual(len(res["scenarios"]), 4)

    def test_format_telegram_leaps_card(self):
        res = self.service.calculate_leaps_strategy("SAP.DE", spot_price=215.0)
        card = self.service.format_telegram_leaps_card(res)
        self.assertIn("LEAPS ASYMMETRIE-RECHNER: SAP.DE", card)
        self.assertIn("Stock Replacement Strategy", card)
        self.assertIn("€", card)


if __name__ == "__main__":
    unittest.main()




