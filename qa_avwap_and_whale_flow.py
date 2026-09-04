"""
QA Test Suite: Anchored VWAP (AVWAP) Engine & Whale Flow / Unusual Volume Spike Detector
"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pandas as pd

from src.anchored_vwap_service import AnchoredVWAPService
from src.whale_flow_service import WhaleFlowService
from src.telegram_interactive_service import TelegramInteractiveService


def make_mock_df(days: int = 80, base_price: float = 100.0, base_vol: float = 1_000_000):
    start = datetime.now(timezone.utc) - timedelta(days=days)
    dates = [start + timedelta(days=i) for i in range(days)]
    
    highs = []
    lows = []
    closes = []
    vols = []
    opens = []
    
    price = base_price
    for i in range(days):
        price += (i % 3 - 1) * 0.5
        open_p = price - 0.1
        high = price + 1.5
        low = price - 1.5
        close = price + 0.2
        vol = base_vol + (i * 10_000)
        opens.append(open_p)
        highs.append(high)
        lows.append(low)
        closes.append(close)
        vols.append(vol)

    df = pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": vols,
    }, index=pd.DatetimeIndex(dates))
    return df


class TestAnchoredVWAPService(unittest.TestCase):
    def setUp(self):
        self.service = AnchoredVWAPService()

    def test_calculate_avwap_from_date_math(self):
        df = make_mock_df(days=40, base_price=100.0, base_vol=1_000_000)
        start_date = (datetime.now(timezone.utc) - timedelta(days=10)).date()
        res = self.service._calculate_avwap_from_date(df, start_date, "Test Anchor")
        
        self.assertIsNotNone(res)
        self.assertEqual(res["label"], "Test Anchor")
        self.assertIn("avwap", res)
        self.assertIn("upper_band_1", res)
        self.assertIn("lower_band_1", res)
        self.assertIn("upper_band_2", res)
        self.assertIn("lower_band_2", res)
        self.assertTrue(res["upper_band_1"] > res["avwap"])
        self.assertTrue(res["upper_band_2"] > res["upper_band_1"])
        self.assertTrue(res["lower_band_1"] < res["avwap"])
        self.assertTrue(res["lower_band_2"] < res["lower_band_1"])

    def test_calculate_swing_low_avwap(self):
        df = make_mock_df(days=70, base_price=150.0, base_vol=500_000)
        # Force a distinct lowest low 25 days ago
        df.iloc[-25, df.columns.get_loc("Low")] = 80.0
        df.iloc[-25, df.columns.get_loc("Close")] = 85.0
        
        res = self.service._calculate_swing_low_avwap(df, lookback=60)
        self.assertIsNotNone(res)
        self.assertIn("avwap", res)
        self.assertIn("anchor_date", res)
        self.assertTrue(res["bars_count"] >= 2)

    def test_format_telegram_avwap_card(self):
        mock_data = {
            "ticker": "NVDA",
            "spot_price": 125.50,
            "institutional_bias": "BULLISH_DOMINANCE",
            "bias_label": "🟢 Institutionelle Käufer im Gewinn (Bullenmarkt)",
            "ytd": {"avwap": 115.00, "dist_pct": 9.13, "upper_band_1": 122.0, "lower_band_1": 108.0},
            "earnings": {"avwap": 120.00, "dist_pct": 4.58, "anchor_date": "2026-05-20"},
            "monthly": {"avwap": 124.00, "dist_pct": 1.21},
            "swing_low": {"avwap": 110.00, "dist_pct": 14.09},
            "retests": ["🎯 YTD AVWAP Retest Zone (115.00)"],
        }
        card = self.service.format_telegram_avwap_card(mock_data)
        self.assertIn("NVDA", card)
        self.assertIn("YTD AVWAP", card)
        self.assertIn("Earnings AVWAP", card)
        self.assertIn("Institutionelle", card)


class TestWhaleFlowService(unittest.TestCase):
    def setUp(self):
        self.service = WhaleFlowService(volume_spike_threshold=2.2)

    @patch("yfinance.Ticker")
    def test_whale_flow_normal(self, mock_ticker):
        df = make_mock_df(days=40, base_price=100.0, base_vol=1_000_000)
        mock_t = MagicMock()
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        flow = self.service.analyze_whale_flow("AAPL")
        self.assertIsNotNone(flow)
        self.assertEqual(flow["pattern"], "NORMAL")
        self.assertFalse(flow["is_whale_activity"])

    @patch("yfinance.Ticker")
    def test_whale_flow_absorption(self, mock_ticker):
        df = make_mock_df(days=40, base_price=100.0, base_vol=1_000_000)
        # Inject massive volume spike on last bar with narrow spread (absorption)
        df.iloc[-1, df.columns.get_loc("Volume")] = 4_000_000  # 4x volume spike
        df.iloc[-1, df.columns.get_loc("High")] = 100.20
        df.iloc[-1, df.columns.get_loc("Low")] = 100.00
        df.iloc[-1, df.columns.get_loc("Close")] = 100.15

        mock_t = MagicMock()
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        flow = self.service.analyze_whale_flow("AAPL")
        self.assertIsNotNone(flow)
        self.assertTrue(flow["is_whale_activity"])
        self.assertEqual(flow["pattern"], "ACCUMULATION_ABSORPTION")
        self.assertIn("Absorption", flow["badge"])

    @patch("yfinance.Ticker")
    def test_whale_flow_expansion(self, mock_ticker):
        df = make_mock_df(days=40, base_price=100.0, base_vol=1_000_000)
        # Inject massive volume spike with wide bullish range
        df.iloc[-1, df.columns.get_loc("Volume")] = 3_500_000
        df.iloc[-1, df.columns.get_loc("Open")] = 100.0
        df.iloc[-1, df.columns.get_loc("High")] = 110.0
        df.iloc[-1, df.columns.get_loc("Low")] = 99.5
        df.iloc[-1, df.columns.get_loc("Close")] = 109.5

        mock_t = MagicMock()
        mock_t.history.return_value = df
        mock_ticker.return_value = mock_t

        flow = self.service.analyze_whale_flow("TSLA")
        self.assertIsNotNone(flow)
        self.assertTrue(flow["is_whale_activity"])
        self.assertEqual(flow["pattern"], "INSTITUTIONAL_EXPANSION")

    def test_format_telegram_whale_card(self):
        mock_flow = {
            "ticker": "MSFT",
            "spot_price": 420.0,
            "pattern": "ACCUMULATION_ABSORPTION",
            "badge": "🐋 Institutionelle Absorption (Block-Buying)",
            "description": "Smart Money kauft stillschweigend.",
            "volume_ratio": 3.4,
            "avg_volume_20d": 20_000_000,
            "last_volume": 68_000_000,
            "spread_ratio": 0.65,
        }
        card = self.service.format_telegram_whale_card(mock_flow)
        self.assertIn("MSFT", card)
        self.assertIn("Institutionelle Absorption", card)
        self.assertIn("3.4x", card)


class TestTelegramInteractiveCommands(unittest.TestCase):
    def setUp(self):
        self.avwap_service = AnchoredVWAPService()
        self.whale_service = WhaleFlowService()
        self.interactive = TelegramInteractiveService(
            bot_token="test_token",
            allowed_chat_ids="12345",
            anchored_vwap_service=self.avwap_service,
            whale_flow_service=self.whale_service,
        )

    def test_avwap_command_fallback(self):
        res = self.interactive._cmd_avwap("")
        self.assertIn("Bitte einen Ticker angeben", res)

    def test_whale_command_fallback(self):
        res = self.interactive._cmd_whale("")
        self.assertTrue("Whale" in res or "Watchlist" in res)

    def test_inline_keyboard_has_avwap_and_whale(self):
        markup = self.interactive._build_inline_keyboard("NVDA")
        buttons = [btn.get("text", "") for row in markup.get("inline_keyboard", []) for btn in row]
        self.assertTrue(any("AVWAP" in b for b in buttons))
        self.assertTrue(any("Whale" in b for b in buttons))


if __name__ == "__main__":
    unittest.main()
