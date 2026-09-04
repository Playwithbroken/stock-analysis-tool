"""
QA Test Suite: Smart Money Fair Value Gaps (FVG) & Multi-Timeframe Alignment
"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pandas as pd

from src.liquidity_zone_service import LiquidityZoneService
from src.multi_timeframe_service import MultiTimeframeService
from src.asymmetric_trade_service import AsymmetricTradeService
from src.telegram_interactive_service import TelegramInteractiveService


def make_mock_df(days: int = 50, base_price: float = 100.0):
    start = datetime.now(timezone.utc) - timedelta(days=days)
    dates = [start + timedelta(days=i) for i in range(days)]
    
    highs = []
    lows = []
    closes = []
    vols = []
    opens = []
    
    price = base_price
    for i in range(days):
        opens.append(price)
        high = price + 1.0
        low = price - 1.0
        close = price + 0.2
        highs.append(high)
        lows.append(low)
        closes.append(close)
        vols.append(1_000_000)
        price += 0.3

    df = pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": vols,
    }, index=pd.DatetimeIndex(dates))
    return df


class TestLiquidityZoneService(unittest.TestCase):
    def setUp(self):
        self.service = LiquidityZoneService()

    def test_bullish_fvg_detection(self):
        df = make_mock_df(days=30, base_price=100.0)
        # Keep all lows above 108 after bar 12 so the gap stays unmitigated
        df.iloc[10, df.columns.get_loc("High")] = 105.0
        df.iloc[11, df.columns.get_loc("Open")] = 105.5
        df.iloc[11, df.columns.get_loc("Close")] = 112.0
        df.iloc[11, df.columns.get_loc("High")] = 113.0
        df.iloc[12, df.columns.get_loc("Low")] = 108.0
        df.iloc[12, df.columns.get_loc("Close")] = 111.0
        for k in range(13, len(df)):
            df.iloc[k, df.columns.get_loc("Low")] = 109.0
            df.iloc[k, df.columns.get_loc("Close")] = 110.0
            df.iloc[k, df.columns.get_loc("High")] = 112.0

        res = self.service._detect_zones_from_df("NVDA", df)
        self.assertIsNotNone(res)
        self.assertTrue(res["total_active_bullish_fvgs"] > 0)
        matching = [f for f in res["active_bullish_fvgs"] if f["gap_low"] == 105.0 and f["gap_high"] == 108.0]
        self.assertTrue(len(matching) > 0)
        self.assertEqual(matching[0]["midpoint"], 106.5)

    def test_order_block_detection(self):
        df = make_mock_df(days=35, base_price=100.0)
        # Candle 15: Down candle (Close < Open)
        df.iloc[15, df.columns.get_loc("Open")] = 102.0
        df.iloc[15, df.columns.get_loc("Close")] = 99.0
        df.iloc[15, df.columns.get_loc("Low")] = 98.5
        df.iloc[15, df.columns.get_loc("High")] = 102.5
        # Candle 16: Massive impulsive breakout candle breaking structure
        df.iloc[16, df.columns.get_loc("Open")] = 100.0
        df.iloc[16, df.columns.get_loc("Close")] = 115.0
        df.iloc[16, df.columns.get_loc("High")] = 116.0
        df.iloc[16, df.columns.get_loc("Low")] = 99.5

        res = self.service._detect_zones_from_df("TSLA", df)
        self.assertIsNotNone(res)
        self.assertIsNotNone(res["nearest_order_block"])
        self.assertEqual(res["nearest_order_block"]["ob_low"], 98.5)

    def test_format_telegram_fvg_card(self):
        mock_data = {
            "ticker": "AAPL",
            "spot_price": 210.50,
            "zone_label": "🎯 Im Fair Value Gap Support ($205.00 - $208.00)",
            "nearest_bullish_fvg": {
                "gap_low": 205.00,
                "gap_high": 208.00,
                "midpoint": 206.50,
                "status": "UNMITIGATED",
                "date": "2026-08-15",
            },
            "nearest_order_block": {
                "ob_low": 200.00,
                "ob_high": 203.00,
                "status": "UNMITIGATED",
                "date": "2026-08-10",
            },
        }
        card = self.service.format_telegram_fvg_card(mock_data)
        self.assertIn("AAPL", card)
        self.assertIn("Fair Value Gap Support", card)
        self.assertIn("Order Block", card)


class TestMultiTimeframeService(unittest.TestCase):
    def setUp(self):
        self.service = MultiTimeframeService()

    def test_ema_and_rsi_math(self):
        prices = [100.0 + i for i in range(30)]
        ema = self.service._calc_ema(prices, 20)
        self.assertTrue(ema > 100.0)

        # Monotonically increasing prices should give high RSI (> 80)
        rsi = self.service._calc_rsi(prices, 14)
        self.assertTrue(rsi >= 70.0)

    def test_timeframe_analysis_bullish(self):
        df = make_mock_df(days=60, base_price=100.0)
        tf = self.service._analyze_timeframe("1D", df)
        self.assertIn("bias", tf)
        self.assertIn("BULLISH", tf["bias"])
        self.assertTrue(tf["price_above_ema20"])

    def test_format_telegram_mtf_card(self):
        mock_data = {
            "ticker": "MSFT",
            "spot_price": 430.00,
            "badge": "🟢 100% Bullish (3/3 Zeitebenen)",
            "timeframes": {
                "1D": {"bias_label": "🟢 Bullish Trend & Momentum", "ema20": 420.0, "rsi14": 62.5},
                "1H": {"bias_label": "🟢 Bullish Trend & Momentum", "ema20": 428.0, "rsi14": 58.0},
                "15M": {"bias_label": "🟢 Moderat Bullish", "ema20": 429.5, "rsi14": 54.0},
            }
        }
        card = self.service.format_telegram_mtf_card(mock_data)
        self.assertIn("MSFT", card)
        self.assertIn("100% Bullish", card)
        self.assertIn("Tageschart", card)


class TestTelegramInteractiveFVGAndMTF(unittest.TestCase):
    def setUp(self):
        self.fvg_service = LiquidityZoneService()
        self.mtf_service = MultiTimeframeService()
        self.interactive = TelegramInteractiveService(
            bot_token="test_token",
            allowed_chat_ids="12345",
            liquidity_zone_service=self.fvg_service,
            multi_timeframe_service=self.mtf_service,
        )

    def test_fvg_command_fallback(self):
        res = self.interactive._cmd_fvg([])
        self.assertIn("Bitte einen Ticker angeben", res)

    def test_mtf_command_fallback(self):
        res = self.interactive._cmd_mtf([])
        self.assertIn("Bitte einen Ticker angeben", res)

    def test_inline_keyboard_has_fvg_and_mtf(self):
        markup = self.interactive._build_inline_keyboard("NVDA")
        buttons = [btn.get("text", "") for row in markup.get("inline_keyboard", []) for btn in row]
        self.assertTrue(any("FVG" in b for b in buttons))
        self.assertTrue(any("MTF" in b for b in buttons))


if __name__ == "__main__":
    unittest.main()
