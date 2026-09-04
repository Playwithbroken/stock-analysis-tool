"""
Multi-Timeframe Trend & Momentum Alignment Service

Evaluates trend and momentum synchronization across multiple horizons:
  - Daily (1D): Macro / Primary Trend
  - 1-Hour (1H): Swing / Intermediate Trend
  - 15-Minute (15M): Tactical Intraday Execution

A 3/3 or 4/4 Bullish Synchronization represents an exceptional high-probability trend day.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class MultiTimeframeService:
    def __init__(self, cache_ttl_seconds: int = 600) -> None:
        self.ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def analyze_mtf_alignment(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes 1D, 1H, and 15m trends for a ticker.
        """
        symbol = ticker.strip().upper()
        cached = self._cache.get(symbol)
        if cached and (time.time() - cached[0]) < self.ttl:
            return cached[1]

        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            # 1D bars
            hist_1d = t.history(period="6mo", interval="1d")
            # 1H bars
            hist_1h = t.history(period="1mo", interval="1h")
            # 15m bars
            hist_15m = t.history(period="5d", interval="15m")

            if hist_1d.empty or len(hist_1d) < 20:
                return None

            tf_1d = self._analyze_timeframe("1D", hist_1d)
            tf_1h = self._analyze_timeframe("1H", hist_1h) if not hist_1h.empty and len(hist_1h) >= 20 else None
            tf_15m = self._analyze_timeframe("15M", hist_15m) if not hist_15m.empty and len(hist_15m) >= 20 else None

            timeframes = [tf for tf in [tf_1d, tf_1h, tf_15m] if tf is not None]
            if not timeframes:
                return None

            bullish_count = sum(1 for tf in timeframes if "BULLISH" in tf["bias"])
            bearish_count = sum(1 for tf in timeframes if "BEARISH" in tf["bias"])
            total_tfs = len(timeframes)

            # Alignment status
            if bullish_count == total_tfs:
                alignment = "FULL_BULLISH_SYNC"
                badge = f"🟢 100% Bullish ({bullish_count}/{total_tfs} Zeitebenen)"
                confluence_bonus = 12
            elif bullish_count >= 2 and bearish_count == 0:
                alignment = "BULLISH_BIAS"
                badge = f"🟢 Bullischer Bias ({bullish_count}/{total_tfs} Zeitebenen)"
                confluence_bonus = 8
            elif bearish_count == total_tfs:
                alignment = "FULL_BEARISH_SYNC"
                badge = f"🔴 100% Bärisch ({bearish_count}/{total_tfs} Zeitebenen)"
                confluence_bonus = -10
            elif bearish_count >= 2:
                alignment = "BEARISH_BIAS"
                badge = f"🔴 Bärischer Gegenwind ({bearish_count}/{total_tfs} Zeitebenen)"
                confluence_bonus = -5
            else:
                alignment = "MIXED_CHOP"
                badge = f"🟡 Gemischte Zeitebenen ({bullish_count} Bull / {bearish_count} Bär)"
                confluence_bonus = 0

            spot = float(hist_1d["Close"].iloc[-1])

            result = {
                "ticker": symbol,
                "spot_price": round(spot, 2),
                "alignment": alignment,
                "badge": badge,
                "confluence_bonus": confluence_bonus,
                "bullish_count": bullish_count,
                "total_timeframes": total_tfs,
                "timeframes": {
                    "1D": tf_1d,
                    "1H": tf_1h,
                    "15M": tf_15m,
                },
            }

            self._cache[symbol] = (time.time(), result)
            return result

        except Exception as exc:
            logger.debug("MTF alignment error for %s: %s", symbol, exc)
            return None

    def _analyze_timeframe(self, tf_label: str, df: Any) -> Dict[str, Any]:
        """Analyzes a single timeframe for EMA trend and RSI momentum."""
        closes = df["Close"].tolist()
        n = len(closes)

        # EMA 20 & EMA 50
        ema20 = self._calc_ema(closes, 20)
        ema50 = self._calc_ema(closes, 50) if n >= 50 else ema20 * 0.98

        # RSI 14
        rsi14 = self._calc_rsi(closes, 14)

        spot = closes[-1]
        above_ema20 = spot >= ema20
        above_ema50 = spot >= ema50
        ema_bullish = ema20 >= ema50

        # Classification
        if above_ema20 and above_ema50 and rsi14 >= 50.0:
            bias = "BULLISH"
            bias_label = "🟢 Bullish Trend & Momentum"
        elif not above_ema20 and not above_ema50 and rsi14 < 50.0:
            bias = "BEARISH"
            bias_label = "🔴 Bärischer Abwärtstrend"
        elif above_ema20 and rsi14 >= 48.0:
            bias = "NEUTRAL_BULLISH"
            bias_label = "🟡 Moderat Bullish"
        else:
            bias = "NEUTRAL_BEARISH"
            bias_label = "🟡 Seitwärts / Schwach"

        return {
            "tf": tf_label,
            "bias": bias,
            "bias_label": bias_label,
            "ema20": round(ema20, 2),
            "ema50": round(ema50, 2),
            "rsi14": round(rsi14, 1),
            "price_above_ema20": above_ema20,
            "ema_cross_bullish": ema_bullish,
        }

    @staticmethod
    def _calc_ema(data: List[float], period: int) -> float:
        if not data:
            return 0.0
        if len(data) < period:
            return sum(data) / len(data)
        k = 2.0 / (period + 1.0)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price * k) + (ema * (1.0 - k))
        return ema

    @staticmethod
    def _calc_rsi(data: List[float], period: int = 14) -> float:
        if len(data) < period + 1:
            return 50.0
        deltas = [data[i] - data[i - 1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def format_telegram_mtf_card(self, data: Dict[str, Any]) -> str:
        """Formats the multi-timeframe alignment grid for Telegram."""
        sym = data.get("ticker", "TICKER")
        spot = data.get("spot_price", 0.0)
        badge = data.get("badge", "Neutral")
        tfs = data.get("timeframes", {})

        lines = [
            f"🧭 <b>MULTI-TIMEFRAME ALIGNMENT: {sym}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Aktueller Kurs:</b> ${spot:.2f}",
            f"• <b>Gesamt-Synchronisation:</b> {badge}\n",
        ]

        for tf_key, tf_name in [("1D", "Tageschart (1D)"), ("1H", "Stundenchart (1H)"), ("15M", "15-Minuten (15M)")]:
            tf = tfs.get(tf_key)
            if tf:
                lines.append(f"• <b>{tf_name}:</b> {tf['bias_label']}")
                lines.append(f"  EMA20: ${tf['ema20']:.2f} &middot; RSI14: {tf['rsi14']:.1f}")
            else:
                lines.append(f"• <b>{tf_name}:</b> <i>Daten nicht verfügbar</i>")

        lines.append("\n💡 <i>Handelsregel: Trades haben die höchste Erfolgsquote, wenn 1D, 1H und 15M synchron grün sind (Trend-All-Clear). Vermeide Longs bei bärischem 1H-Gegenwind!</i>")

        return "\n".join(lines)
