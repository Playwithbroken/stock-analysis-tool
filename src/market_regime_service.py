"""
Market Regime Service — Macro Breadth & Volatility Environment Filter

Provides institutional macro context:
  1. SPY (S&P 500) & QQQ (Nasdaq 100) trend health (price vs 20 EMA, 50 SMA).
  2. VIX (CBOE Volatility Index) regime (Risk-On < 18, Normal 18-24, Risk-Off > 24).
  3. Combined Market Stance:
       - RISK_ON: Favorable for directional equity swing longs.
       - CAUTIOUS: Selective environment, prioritize Grade A+ setups.
       - RISK_OFF: High volatility / downtrend, half size or cash preservation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


@dataclass
class _RegimeCache:
    timestamp: float
    data: Dict[str, Any]


class MarketRegimeService:
    _cache: Optional[_RegimeCache] = None
    TTL_SECONDS = 900  # 15 minutes cache

    def get_market_regime(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Returns the current macro regime combining SPY, QQQ and VIX."""
        now = time.time()
        if not force_refresh and self._cache and (now - self._cache.timestamp) < self.TTL_SECONDS:
            return self._cache.data

        data = self._compute_market_regime()
        self._cache = _RegimeCache(timestamp=now, data=data)
        return data

    def _compute_market_regime(self) -> Dict[str, Any]:
        spy_info = self._fetch_asset_trend("SPY", default_price=550.0)
        qqq_info = self._fetch_asset_trend("QQQ", default_price=480.0)
        vix_info = self._fetch_vix(default_val=16.5)

        vix_val = vix_info.get("value", 16.5)

        # Determine overall trend from SPY & QQQ
        bullish_count = sum(1 for x in [spy_info, qqq_info] if x.get("trend") == "bullish")
        bearish_count = sum(1 for x in [spy_info, qqq_info] if x.get("trend") == "bearish")

        if vix_val >= 26.0 or bearish_count >= 2:
            stance = "RISK_OFF"
            stance_color = "red"
            recommendation = "Erhöhtes Marktrisiko (VIX hoch / Abwärtstrend). Reduziere Positionsgrößen auf max. 50% und meide Breakouts."
        elif vix_val >= 21.0 or bearish_count == 1:
            stance = "CAUTIOUS"
            stance_color = "yellow"
            recommendation = "Selektiver Markt. Nur Setups mit starker Konfluenz (Grade A+) handeln."
        else:
            stance = "RISK_ON"
            stance_color = "green"
            recommendation = "Ideales Umfeld für Long-Swings. Geringe Volatilität und stabiler Markttrend unterstützen asymmetrische Trades."

        result = {
            "stance": stance,
            "stance_color": stance_color,
            "recommendation": recommendation,
            "vix": vix_info,
            "spy": spy_info,
            "qqq": qqq_info,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    def _fetch_asset_trend(self, ticker: str, default_price: float = 100.0) -> Dict[str, Any]:
        if yf is None:
            return {
                "symbol": ticker,
                "price": default_price,
                "trend": "bullish",
                "sma20": default_price * 0.98,
                "sma50": default_price * 0.95,
                "change_pct_1d": 0.5,
            }

        try:
            tk = yf.Ticker(ticker)
            df = tk.history(period="3mo", interval="1d")
            if df is None or len(df) < 20:
                return {
                    "symbol": ticker,
                    "price": default_price,
                    "trend": "bullish",
                    "sma20": default_price * 0.98,
                    "sma50": default_price * 0.95,
                    "change_pct_1d": 0.0,
                }

            close = df["Close"]
            current_price = float(close.iloc[-1])
            prev_price = float(close.iloc[-2]) if len(close) > 1 else current_price
            change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)

            sma20 = float(close.tail(20).mean())
            sma50 = float(close.tail(min(50, len(close))).mean())

            if current_price >= sma20 and current_price >= sma50:
                trend = "bullish"
            elif current_price < sma20 and current_price < sma50:
                trend = "bearish"
            else:
                trend = "neutral"

            return {
                "symbol": ticker,
                "price": round(current_price, 2),
                "trend": trend,
                "sma20": round(sma20, 2),
                "sma50": round(sma50, 2),
                "change_pct_1d": change_pct,
            }
        except Exception as e:
            logger.warning("Failed fetching trend for %s: %s", ticker, e)
            return {
                "symbol": ticker,
                "price": default_price,
                "trend": "bullish",
                "sma20": default_price * 0.98,
                "sma50": default_price * 0.95,
                "change_pct_1d": 0.0,
            }

    def _fetch_vix(self, default_val: float = 16.5) -> Dict[str, Any]:
        if yf is None:
            return {"value": default_val, "regime": "risk_on", "label": "Niedrig (Risk-On)", "color": "green"}

        try:
            tk = yf.Ticker("^VIX")
            df = tk.history(period="5d", interval="1d")
            if df is None or len(df) == 0:
                val = default_val
            else:
                val = float(df["Close"].iloc[-1])
        except Exception as e:
            logger.warning("Failed fetching ^VIX: %s", e)
            val = default_val

        val = round(val, 2)
        if val < 18.0:
            regime = "risk_on"
            label = "Niedrige Volatilität (Risk-On)"
            color = "green"
        elif val < 24.0:
            regime = "normal"
            label = "Moderate Volatilität (Normal)"
            color = "yellow"
        elif val < 32.0:
            regime = "risk_off"
            label = "Erhöhte Volatilität (Risk-Off)"
            color = "orange"
        else:
            regime = "extreme_panic"
            label = "Extreme Panik / Volatilitätsexplosion"
            color = "red"

        return {
            "value": val,
            "regime": regime,
            "label": label,
            "color": color,
        }
