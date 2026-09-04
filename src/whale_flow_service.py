"""
Whale Flow & Unusual Volume Spike Detector (Institutional Footprint)

Detects block-trade activity, dark-pool volume absorption, and institutional expansion:
  1. Volume Spike Ratio: Current bar volume vs. 20-day SMA (>2.2x threshold).
  2. Spread / Range Compression (Absorption):
     - Massive volume with narrow candle spread (Range/ATR < 0.85):
       Institutions absorbing all floating supply at key support without letting price fall.
  3. Institutional Expansion:
     - Massive volume with wide candle spread and close near high: Aggressive institutional impulse.
  4. Distribution Exhaustion:
     - Massive volume with long upper wick and weak close: Smart money selling into retail hype.
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


class WhaleFlowService:
    def __init__(self, volume_spike_threshold: float = 2.2, cache_ttl_seconds: int = 900) -> None:
        self.spike_threshold = volume_spike_threshold
        self.ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def analyze_whale_flow(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes recent price and volume action for unusual whale/institutional footprints.
        """
        symbol = ticker.strip().upper()
        cached = self._cache.get(symbol)
        if cached and (time.time() - cached[0]) < self.ttl:
            return cached[1]

        if not yf:
            return None

        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2mo", interval="1d")
            if hist.empty or len(hist) < 22:
                return None

            hist = hist.dropna(subset=["Close", "Volume"])
            if len(hist) < 22:
                return None

            closes = hist["Close"].tolist()
            highs = hist["High"].tolist()
            lows = hist["Low"].tolist()
            opens = hist["Open"].tolist()
            volumes = hist["Volume"].tolist()

            # 20-day average volume prior to current bar
            vol_sma20 = sum(volumes[-21:-1]) / 20.0
            last_vol = volumes[-1]
            vol_ratio = round(last_vol / vol_sma20, 2) if vol_sma20 > 0 else 1.0

            # 14-day Average True Range (ATR)
            tr_list = []
            for i in range(len(closes) - 15, len(closes)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                tr_list.append(tr)
            atr14 = sum(tr_list) / len(tr_list) if tr_list else (highs[-1] - lows[-1])

            last_range = highs[-1] - lows[-1]
            spread_ratio = round(last_range / atr14, 2) if atr14 > 0 else 1.0

            # Position of close within the daily bar: 0 (at low) to 1 (at high)
            close_position = (
                (closes[-1] - lows[-1]) / last_range if last_range > 0 else 0.5
            )

            is_whale_activity = vol_ratio >= self.spike_threshold
            pattern = "NORMAL"
            badge = "⚪ Normales Handelsvolumen"
            description = "Keine abnormalen institutionellen Orderblöcke erkannt."

            if is_whale_activity:
                # Case 1: Absorption (High volume, narrow spread, firm close)
                if spread_ratio <= 0.85 and close_position >= 0.40:
                    pattern = "ACCUMULATION_ABSORPTION"
                    badge = "🐋 Institutionelle Absorption (Kaufdruck)"
                    description = (
                        f"Abnormales Volumen ({vol_ratio:.1f}x) bei sehr enger Kursspanne ({spread_ratio:.2f} ATR). "
                        "Institutionelle Käufer absorbieren stillschweigend das Angebot."
                    )
                # Case 2: Institutional Breakout (High volume, wide spread, strong close)
                elif spread_ratio >= 1.25 and close_position >= 0.70:
                    pattern = "INSTITUTIONAL_EXPANSION"
                    badge = "🚀 Institutioneller Volumenausbruch"
                    description = (
                        f"Aggressive Volumenausdehnung ({vol_ratio:.1f}x) mit Schluss nahe Tageshoch. "
                        "Klares Smart-Money Momentum."
                    )
                # Case 3: Distribution / Climax (High volume, weak close or long upper wick)
                elif close_position <= 0.35:
                    pattern = "DISTRIBUTION_EXHAUSTION"
                    badge = "⚠️ Institutionelle Distribution (Abverkauf)"
                    description = (
                        f"Sehr hohes Volumen ({vol_ratio:.1f}x) mit schwachem Schlusskurs. "
                        "Großanleger verkaufen in die Liquidität hinein."
                    )
                else:
                    pattern = "HIGH_VOLUME_CHOP"
                    badge = "⚡ Hohes Handelsvolumen"
                    description = f"Ungewöhnlich hoher Umsatz ({vol_ratio:.1f}x 20-Tage-Schnitt) im Bereich der Liquidität."

            result = {
                "ticker": symbol,
                "spot_price": round(closes[-1], 2),
                "last_volume": int(last_vol),
                "avg_volume_20d": int(vol_sma20),
                "volume_ratio": vol_ratio,
                "spread_ratio": spread_ratio,
                "atr14": round(atr14, 2),
                "close_position": round(close_position, 2),
                "is_whale_activity": is_whale_activity,
                "pattern": pattern,
                "badge": badge,
                "description": description,
            }

            self._cache[symbol] = (time.time(), result)
            return result

        except Exception as exc:
            logger.debug("Whale flow analysis error for %s: %s", symbol, exc)
            return None

    def scan_watchlist_whale_flows(self, watchlist: List[str]) -> List[Dict[str, Any]]:
        """Scans a watchlist for active volume anomalies."""
        results: List[Dict[str, Any]] = []
        for symbol in watchlist:
            if not symbol:
                continue
            res = self.analyze_whale_flow(symbol)
            if res and res.get("is_whale_activity"):
                results.append(res)

        results.sort(key=lambda x: x["volume_ratio"], reverse=True)
        return results

    def format_telegram_whale_card(self, data: Dict[str, Any]) -> str:
        """Formats a single ticker whale analysis for Telegram."""
        sym = data.get("ticker", "")
        spot = data.get("spot_price", 0.0)
        vol_ratio = data.get("volume_ratio", 1.0)
        badge = data.get("badge", "")
        desc = data.get("description", "")
        last_vol = data.get("last_volume", 0)
        avg_vol = data.get("avg_volume_20d", 0)

        lines = [
            f"🐋 <b>INSTITUTIONAL FOOTPRINT (WHALE FLOW): {sym}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Status:</b> {badge}",
            f"• <b>Spot-Kurs:</b> ${spot:.2f}",
            f"• <b>Volumen-Spike:</b> <b>{vol_ratio:.1f}x</b> über 20-Tage-Schnitt",
            f"• <b>Umsatz:</b> {last_vol:,} (Schnitt: {avg_vol:,})\n",
            f"💡 <b>Interpretation:</b>\n{desc}\n",
        ]

        pattern = data.get("pattern")
        if pattern == "ACCUMULATION_ABSORPTION":
            lines.append("🎯 <b>Aktion:</b> Exzellentes Zeichen für Support-Stärke. Setups in Trendrichtung bevorzugen.")
        elif pattern == "INSTITUTIONAL_EXPANSION":
            lines.append("🚀 <b>Aktion:</b> Momentum-Bestätigung. Pullbacks an 9 EMA zum Einstieg nutzen.")
        elif pattern == "DISTRIBUTION_EXHAUSTION":
            lines.append("🛑 <b>Aktion:</b> Vorsicht! Keine Breakouts jagen, Stops eng nachziehen.")

        return "\n".join(lines)
