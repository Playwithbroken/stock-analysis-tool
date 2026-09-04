"""
Liquidity Zone & Smart Money Service — Fair Value Gaps (FVG) & Order Blocks

Identifies institutional market structure footprints:
  1. Fair Value Gaps (FVG): 3-candle price imbalances / liquidity voids.
  2. Order Blocks (OB): Last opposite-color candle before an impulsive break of structure (BOS).
  3. Mitigation Tracking: Distinguishes between fresh (unmitigated), retested, and filled zones.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore


class LiquidityZoneService:
    def __init__(self, cache_ttl_seconds: int = 900) -> None:
        self.ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def analyze_zones(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Calculates Fair Value Gaps and Order Blocks for a ticker.
        """
        symbol = ticker.strip().upper()
        cached = self._cache.get(symbol)
        if cached and (time.time() - cached[0]) < self.ttl:
            return cached[1]

        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="6mo", interval="1d")
            if hist.empty or len(hist) < 20:
                return None

            hist = hist.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            if len(hist) < 20:
                return None

            result = self._detect_zones_from_df(symbol, hist)
            if result:
                self._cache[symbol] = (time.time(), result)
            return result

        except Exception as exc:
            logger.debug("Liquidity zones error for %s: %s", symbol, exc)
            return None

    def _detect_zones_from_df(self, symbol: str, df: Any) -> Optional[Dict[str, Any]]:
        """Detects FVGs and Order Blocks from a history DataFrame."""
        try:
            opens = df["Open"].tolist()
            highs = df["High"].tolist()
            lows = df["Low"].tolist()
            closes = df["Close"].tolist()
            vols = df["Volume"].tolist()
            dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in df.index]

            n = len(closes)
            if n < 10:
                return None

            spot = closes[-1]

            # 1. Fair Value Gaps (FVG)
            bullish_fvgs: List[Dict[str, Any]] = []
            bearish_fvgs: List[Dict[str, Any]] = []

            # Look back over past 60 bars for FVGs
            lookback_start = max(2, n - 60)
            for i in range(lookback_start, n):
                # Bullish FVG: Low of candle i > High of candle i-2
                if lows[i] > highs[i - 2]:
                    gap_low = highs[i - 2]
                    gap_high = lows[i]
                    gap_pct = ((gap_high - gap_low) / gap_low) * 100.0

                    if gap_pct >= 0.3:  # minimum 0.3% gap significance
                        # Check mitigation by subsequent candles
                        subsequent_lows = lows[i + 1:] if i + 1 < n else []
                        is_filled = any(l <= gap_low for l in subsequent_lows)
                        is_retested = any(l <= gap_high and l > gap_low for l in subsequent_lows)

                        status = "FILLED" if is_filled else ("RETESTED" if is_retested else "UNMITIGATED")

                        bullish_fvgs.append({
                            "type": "BULLISH_FVG",
                            "date": dates[i - 1],
                            "gap_low": round(gap_low, 2),
                            "gap_high": round(gap_high, 2),
                            "midpoint": round((gap_low + gap_high) / 2.0, 2),
                            "gap_size_pct": round(gap_pct, 2),
                            "status": status,
                        })

                # Bearish FVG: High of candle i < Low of candle i-2
                elif highs[i] < lows[i - 2]:
                    gap_high = lows[i - 2]
                    gap_low = highs[i]
                    gap_pct = ((gap_high - gap_low) / gap_low) * 100.0

                    if gap_pct >= 0.3:
                        subsequent_highs = highs[i + 1:] if i + 1 < n else []
                        is_filled = any(h >= gap_high for h in subsequent_highs)
                        is_retested = any(h >= gap_low and h < gap_high for h in subsequent_highs)

                        status = "FILLED" if is_filled else ("RETESTED" if is_retested else "UNMITIGATED")

                        bearish_fvgs.append({
                            "type": "BEARISH_FVG",
                            "date": dates[i - 1],
                            "gap_low": round(gap_low, 2),
                            "gap_high": round(gap_high, 2),
                            "midpoint": round((gap_low + gap_high) / 2.0, 2),
                            "gap_size_pct": round(gap_pct, 2),
                            "status": status,
                        })

            # Keep only active (unmitigated or retested) FVGs closest to current spot
            active_bullish_fvgs = [f for f in bullish_fvgs if f["status"] != "FILLED" and f["gap_high"] <= spot * 1.05]
            active_bearish_fvgs = [f for f in bearish_fvgs if f["status"] != "FILLED" and f["gap_low"] >= spot * 0.95]

            # Nearest Bullish FVG (Demand support)
            nearest_bullish_fvg = None
            if active_bullish_fvgs:
                # sorted by closeness to spot (descending gap_high)
                active_bullish_fvgs.sort(key=lambda x: x["gap_high"], reverse=True)
                nearest_bullish_fvg = active_bullish_fvgs[0]

            # 2. Institutional Order Blocks (Bullish Demand Block)
            # Find the last down candle before an impulsive move that broke swing high
            order_blocks: List[Dict[str, Any]] = []
            for i in range(max(3, n - 40), n - 2):
                # Down candle: Close < Open
                if closes[i] < opens[i]:
                    # Impulsive expansion candle right after: large bullish candle
                    next_range = highs[i + 1] - lows[i + 1]
                    avg_range = sum(highs[j] - lows[j] for j in range(max(0, i - 10), i)) / 10.0 if i >= 10 else next_range
                    
                    if next_range > 1.3 * avg_range and closes[i + 1] > highs[i]:
                        ob_low = lows[i]
                        ob_high = highs[i]

                        # Check mitigation
                        subsequent_lows = lows[i + 2:] if i + 2 < n else []
                        is_broken = any(l < ob_low for l in subsequent_lows)
                        is_tested = any(l <= ob_high and l >= ob_low for l in subsequent_lows)

                        if not is_broken:
                            status = "RETESTED" if is_tested else "UNMITIGATED"
                            order_blocks.append({
                                "type": "BULLISH_ORDER_BLOCK",
                                "date": dates[i],
                                "ob_low": round(ob_low, 2),
                                "ob_high": round(ob_high, 2),
                                "status": status,
                            })

            nearest_ob = None
            if order_blocks:
                # Filter for OBs below current spot
                valid_obs = [ob for ob in order_blocks if ob["ob_high"] <= spot * 1.02]
                if valid_obs:
                    valid_obs.sort(key=lambda x: x["ob_high"], reverse=True)
                    nearest_ob = valid_obs[0]

            # Current price reaction check
            in_demand_zone = False
            zone_label = "Neutral"
            if nearest_bullish_fvg and nearest_bullish_fvg["gap_low"] <= spot <= nearest_bullish_fvg["gap_high"] * 1.01:
                in_demand_zone = True
                zone_label = f"🎯 Im Fair Value Gap Support (${nearest_bullish_fvg['gap_low']} - ${nearest_bullish_fvg['gap_high']})"
            elif nearest_ob and nearest_ob["ob_low"] <= spot <= nearest_ob["ob_high"] * 1.015:
                in_demand_zone = True
                zone_label = f"🛡️ Im Institutional Order Block (${nearest_ob['ob_low']} - ${nearest_ob['ob_high']})"

            confluence_bonus = 10 if in_demand_zone else (4 if nearest_bullish_fvg and spot <= nearest_bullish_fvg["gap_high"] * 1.02 else 0)

            return {
                "ticker": symbol,
                "spot_price": round(spot, 2),
                "in_demand_zone": in_demand_zone,
                "zone_label": zone_label,
                "confluence_bonus": confluence_bonus,
                "nearest_bullish_fvg": nearest_bullish_fvg,
                "nearest_order_block": nearest_ob,
                "total_active_bullish_fvgs": len(active_bullish_fvgs),
                "total_active_bearish_fvgs": len(active_bearish_fvgs),
                "active_bullish_fvgs": active_bullish_fvgs[:3],
                "active_bearish_fvgs": active_bearish_fvgs[:3],
            }
        except Exception as e:
            logger.debug("Error computing liquidity zones for %s: %s", symbol, e)
            return None

    def format_telegram_fvg_card(self, data: Dict[str, Any]) -> str:
        """Formats liquidity zones & FVGs into a Telegram alert card."""
        sym = data.get("ticker", "TICKER")
        spot = data.get("spot_price", 0.0)
        zone_label = data.get("zone_label", "Neutral")
        fvg = data.get("nearest_bullish_fvg")
        ob = data.get("nearest_order_block")

        lines = [
            f"🕳️ <b>SMART MONEY ZONES & FVG: {sym}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Aktueller Kurs:</b> ${spot:.2f}",
            f"• <b>Zonen-Status:</b> {zone_label}\n",
        ]

        if fvg:
            dist = round(((spot - fvg["gap_high"]) / spot) * 100.0, 1)
            lines.append("📌 <b>Nächstes Bullisches FVG:</b>")
            lines.append(f"  • Spanne: <code>${fvg['gap_low']:.2f} &ndash; ${fvg['gap_high']:.2f}</code>")
            lines.append(f"  • Mitte: ${fvg['midpoint']:.2f} (Distanz: {dist:+.1f}%)")
            lines.append(f"  • Status: <b>{fvg['status']}</b> (vom {fvg['date']})\n")
        else:
            lines.append("• <i>Kein unmittelbares bullisches FVG in Reichweite.</i>\n")

        if ob:
            lines.append("🏛️ <b>Institutioneller Order Block (Nachfrage):</b>")
            lines.append(f"  • Kaufbereich: <code>${ob['ob_low']:.2f} &ndash; ${ob['ob_high']:.2f}</code>")
            lines.append(f"  • Status: <b>{ob['status']}</b> (Datum: {ob['date']})\n")

        lines.append("💡 <i>Smart Money Tipp: Unmitigierte FVGs und Order Blocks fungieren als Liquiditätsmagnete. Einstiege an der oberen Kante mit engem Stop bieten hohes R:R!</i>")

        return "\n".join(lines)
