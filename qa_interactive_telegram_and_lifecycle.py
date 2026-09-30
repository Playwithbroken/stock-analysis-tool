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
        self.assertIsNotNone(be_btn)
        self.assertIn("Stop auf Breakeven", be_btn["text"])
        self.assertIsNotNone(close_btn)
        self.assertIn("Position schließen", close_btn["text"])

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
        self.assertIn("+8.33%", res)

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


if __name__ == "__main__":
    unittest.main()
